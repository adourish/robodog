# file: robodog_terminal/llm_client.py
"""
LLM client abstraction for terminal mode.

the runPixel gateway is prompt-in / text-out with NO
native tool-calling, so the interface is deliberately a single `complete()` call.
Tool-calling is done in the loop via prompting (see loop.py / toolcall.py).

Backends:
  - EchoClient : offline/dev mock (scriptable) — default when no the gateway config.
  - GatewayClient : real runPixel gateway endpoint (Basic auth, form-urlencoded).
  - (OpenAI-compatible backend can be added later by reusing service.client.)
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Union
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


def clean_text(s):
    """
    Strip lone UTF-16 surrogate code points that sneak in from Windows clipboard
    pastes — they can't be UTF-8 encoded and would crash the HTTP request.
    """
    if not s:
        return s
    return "".join(c for c in s if not 0xD800 <= ord(c) <= 0xDFFF)

# Cap concurrent the gateway calls across ALL loops (foreground + background agents).
# Internal gateway with unknown rate limits — stay conservative.
_GATEWAY_SEMAPHORE = threading.Semaphore(2)


@dataclass
class Completion:
    """Result of a single LLM completion."""
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: Optional[dict] = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMClient:
    """Abstract base. Implementations must provide `complete`."""

    name: str = "base"

    def complete(
        self,
        prompt: str,
        context: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.3,
    ) -> Completion:
        raise NotImplementedError


class EchoClient(LLMClient):
    """
    Offline mock backend. Drive it with a `script`:

      - a list of strings  -> returned one per call, in order (last one repeats)
      - a callable(prompt, context) -> str
      - None -> echoes a trivial final answer

    This lets the whole loop + tools + UI be exercised with no network/creds.
    """

    name = "echo"

    def __init__(self, script: Union[List[str], Callable[[str, str], str], None] = None):
        self._script = script
        self._i = 0

    def complete(self, prompt, context="", max_tokens=8192, temperature=0.3) -> Completion:
        prompt, context = clean_text(prompt), clean_text(context)
        if callable(self._script):
            text = self._script(prompt, context)
        elif isinstance(self._script, list) and self._script:
            idx = min(self._i, len(self._script) - 1)
            text = self._script[idx]
            self._i += 1
        else:
            text = f"(echo) I received {len(prompt)} chars of prompt. Done."
        return Completion(
            text=text,
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(text.split()),
        )


class _GatewayHTTPError(Exception):
    """HTTP-level the gateway failure; `retryable` marks 5xx/429 vs. hard 4xx."""

    def __init__(self, msg: str, retryable: bool):
        super().__init__(msg)
        self.retryable = retryable


class GatewayClient(LLMClient):
    """
    SEMOSS-style runPixel gateway backend.

    POST {endpoint}  (e.g. https://<host>/Monolith/api/engine/runPixel)
      Auth:  HTTP Basic (access_key : secret_key)
      Header: Content-Type: application/x-www-form-urlencoded
      Body:  expression=<url-encoded LLM(...) pixel>&tz=America/New_York

    Response text is at pixelReturn[0].output.response.

    Credentials & endpoint are passed in (never hard-coded). Typical wiring:
      keys  from KeePass entry 'Gateway'
      host/engine from config or env vars.
    """

    name = "gateway"

    def __init__(
        self,
        endpoint: str,
        engine_id: str,
        access_key: str,
        secret_key: str,
        tz: str = "America/New_York",
        use_history: bool = False,
        timeout: float = 120.0,
        session=None,
        max_attempts: int = 5,
        on_retry: Optional[Callable[[int, int, float, str], None]] = None,
    ):
        if not endpoint or not engine_id:
            raise ValueError("GatewayClient requires endpoint and engine_id")
        if not access_key or not secret_key:
            raise ValueError("GatewayClient requires access_key and secret_key")
        self.endpoint = endpoint
        self.engine_id = engine_id
        self.access_key = access_key
        self.secret_key = secret_key
        self.tz = tz
        self.use_history = use_history
        self.timeout = timeout
        self.max_attempts = max_attempts
        # on_retry(attempt, max_attempts, delay_seconds, reason) — UI hook for the
        # agentic "API error · Retrying in Ns · attempt n/N" line.
        self.on_retry = on_retry or (
            lambda a, m, d, r: logger.warning("the gateway retry %d/%d in %.0fs: %s", a, m, d, r)
        )
        # requests is a robodog dependency already
        import requests  # noqa: WPS433 (local import keeps module import cheap)
        self._session = session or requests.Session()

    @staticmethod
    def _encode_command(prompt: str) -> str:
        # the gateway wraps the user prompt in <encode>...</encode>; the whole LLM(...)
        # expression is then form-url-encoded as a single `expression` field.
        return prompt

    def _build_expression(self, prompt: str, context: str, max_tokens: int, temperature: float) -> str:
        # Build the SEMOSS pixel. context (system prompt) is optional.
        parts = [f'engine = "{self.engine_id}"']
        parts.append(f'command = "<encode>{prompt}</encode>"')
        if context:
            parts.append(f'context = "<encode>{context}</encode>"')
        parts.append(f"useHistory={'true' if self.use_history else 'false'}")
        parts.append(
            'paramValues = [{"max_completion_tokens": %d, "temperature": %s}]'
            % (int(max_tokens), repr(float(temperature)))
        )
        return "LLM(" + ", ".join(parts) + ")"

    def complete(self, prompt, context="", max_tokens=8192, temperature=0.3) -> Completion:
        """
        One completion with retry + backoff. Retryable: network errors, HTTP 5xx,
        429, and the known the gateway empty-response failure mode. Non-retryable: 4xx
        auth/config errors (fail fast — bad keys won't fix themselves).
        """
        prompt, context = clean_text(prompt), clean_text(context)
        import requests as _rq
        last_err = "unknown"
        for attempt in range(1, self.max_attempts + 1):
            try:
                completion = self._complete_once(prompt, context, max_tokens, temperature)
                if completion.text.strip():
                    return completion
                # Empty response: known the gateway failure mode (token cap / no context).
                last_err = "empty response from the gateway"
            except (_rq.ConnectionError, _rq.Timeout) as exc:
                last_err = f"network: {type(exc).__name__}"
            except _GatewayHTTPError as exc:
                if not exc.retryable:
                    raise RuntimeError(str(exc)) from exc
                last_err = str(exc)[:120]
            if attempt < self.max_attempts:
                delay = min(2 ** (attempt - 1), 30)  # 1,2,4,8,16 (cap 30s)
                self.on_retry(attempt, self.max_attempts, delay, last_err)
                time.sleep(delay)
        raise RuntimeError(
            f"the gateway failed after {self.max_attempts} attempts: {last_err}")

    def _complete_once(self, prompt, context, max_tokens, temperature) -> Completion:
        expression = self._build_expression(prompt, context, max_tokens, temperature)
        body = "expression=" + quote_plus(expression) + "&tz=" + quote_plus(self.tz)
        with _GATEWAY_SEMAPHORE:
            resp = self._session.post(
                self.endpoint,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=body,
                auth=(self.access_key, self.secret_key),
                timeout=self.timeout,
            )
        if resp.status_code != 200:
            retryable = resp.status_code >= 500 or resp.status_code == 429
            raise _GatewayHTTPError(
                f"the gateway HTTP {resp.status_code}: {resp.text[:300]}", retryable)
        data = resp.json()
        return self._parse(data)

    @staticmethod
    def _parse(data: dict) -> Completion:
        try:
            pr = data["pixelReturn"][0]
            output = pr.get("output", {})
            # `output` may itself be the response object or a nested dict.
            if isinstance(output, dict):
                text = output.get("response", "")
                ptok = output.get("numberOfTokensInPrompt", 0) or 0
                ctok = output.get("numberOfTokensInResponse", 0) or 0
            else:
                text, ptok, ctok = str(output), 0, 0
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected the gateway response shape: {exc}: {str(data)[:500]}")
        return Completion(text=text, prompt_tokens=ptok, completion_tokens=ctok, raw=data)


class OpenAICompatClient(LLMClient):
    """
    OpenAI-compatible /chat/completions backend (OpenRouter, OpenAI, LiteLLM…).
    Used for live testing of the agentic loop without the gateway, and as a general
    fallback. Same complete() contract: prompt+context in, text out — the loop's
    prompted tool-calling works identically on any backend.
    """

    name = "openai-compat"

    def __init__(self, base_url: str, api_key: str, model: str,
                 referer: str = "https://adourish.github.io",
                 timeout: float = 120.0, max_attempts: int = 4,
                 on_retry: Optional[Callable[[int, int, float, str], None]] = None,
                 session=None):
        if not base_url or not api_key or not model:
            raise ValueError("OpenAICompatClient requires base_url, api_key, model")
        base = base_url.rstrip("/")
        # Normalize: config URLs often omit /v1 (e.g. "https://api.openai.com",
        # "https://openrouter.ai/api") — the wire path is <base>/v1/chat/completions.
        if not base.endswith("/chat/completions"):
            if not base.endswith("/v1"):
                base += "/v1"
            base += "/chat/completions"
        self.url = base
        self.api_key = api_key
        self.model = model
        self.referer = referer
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.on_retry = on_retry or (
            lambda a, m, d, r: logger.warning("LLM retry %d/%d in %.0fs: %s", a, m, d, r))
        import requests
        self._session = session or requests.Session()

    def complete(self, prompt, context="", max_tokens=8192, temperature=0.3) -> Completion:
        prompt, context = clean_text(prompt), clean_text(context)
        import requests as _rq
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.model, "messages": messages,
                   "max_tokens": max_tokens, "temperature": temperature}
        last_err = "unknown"
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = self._session.post(
                    self.url, json=payload, timeout=self.timeout,
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "HTTP-Referer": self.referer})
                if resp.status_code == 200:
                    data = resp.json()
                    choice = data["choices"][0]
                    text = (choice.get("message") or {}).get("content") or ""
                    usage = data.get("usage") or {}
                    if text.strip():
                        return Completion(
                            text=text,
                            prompt_tokens=usage.get("prompt_tokens", 0),
                            completion_tokens=usage.get("completion_tokens", 0),
                            raw=data)
                    last_err = "empty response"
                elif resp.status_code in (429,) or resp.status_code >= 500:
                    last_err = f"HTTP {resp.status_code}"
                else:
                    raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}")
            except (_rq.ConnectionError, _rq.Timeout) as exc:
                last_err = f"network: {type(exc).__name__}"
            if attempt < self.max_attempts:
                delay = min(2 ** (attempt - 1), 30)
                self.on_retry(attempt, self.max_attempts, delay, last_err)
                time.sleep(delay)
        raise RuntimeError(f"LLM failed after {self.max_attempts} attempts: {last_err}")


def build_client_from_config(cfg: Optional[dict]) -> LLMClient:
    """
    Factory. cfg example:
      {"protocol": "gateway", "endpoint": "...", "engine_id": "...",
       "access_key": "...", "secret_key": "...", "use_history": false}
    Falls back to EchoClient when cfg is missing or protocol == 'echo'.
    """
    if not cfg or cfg.get("protocol") == "echo":
        logger.info("terminal: using EchoClient (offline mock)")
        return EchoClient()
    proto = cfg.get("protocol", "gateway")
    if proto == "gateway":
        return GatewayClient(
            endpoint=cfg["endpoint"],
            engine_id=cfg["engine_id"],
            access_key=cfg["access_key"],
            secret_key=cfg["secret_key"],
            tz=cfg.get("tz", "America/New_York"),
            use_history=bool(cfg.get("use_history", False)),
        )
    raise ValueError(f"Unknown LLM protocol: {proto}")
