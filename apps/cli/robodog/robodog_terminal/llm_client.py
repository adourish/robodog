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
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Union
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

# Cap concurrent OpenAI-compat calls across ALL loops — parallel subagents share
# one client, so without a cap a fan-out fires N simultaneous requests. Fast,
# high-limit providers shrug that off; a custom self-hosted gateway (SEMOSS/ELSA)
# ReadTimeouts under it. So: explicit ROBODOG_LLM_MAX_CONCURRENCY wins; else a
# CUSTOM gateway (a ROBODOG_LLM_URL that isn't a known fast host) gets a
# conservative default so it works out of the box; known providers stay uncapped.
_OPENAI_SEM = None
_OPENAI_SEM_N = None
_OPENAI_SEM_LOCK = threading.Lock()

# Hosts known to handle heavy concurrency — everything else is a "custom gateway".
_FAST_HOSTS = ("openrouter.ai", "api.openai.com", "api.groq.com",
               "api.together.xyz", "api.mistral.ai", "api.anthropic.com",
               "api.deepseek.com", "api.fireworks.ai", "localhost", "127.0.0.1")
_DEFAULT_CUSTOM_CONCURRENCY = 2


_DEFAULT_TIMEOUT = 120.0
_DEFAULT_CUSTOM_TIMEOUT = 300.0   # custom gateways are slower; give big prompts room


def _is_custom_gateway(url: str) -> bool:
    url = (url or "").lower()
    return bool(url) and not any(h in url for h in _FAST_HOSTS)


def _effective_max_concurrency() -> int:
    """Resolve the concurrency cap: explicit env var, else a conservative
    default for a custom gateway (ROBODOG_LLM_URL not a known fast host), else
    0 (unlimited)."""
    raw = os.environ.get("ROBODOG_LLM_MAX_CONCURRENCY")
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            return 0
    if _is_custom_gateway(os.environ.get("ROBODOG_LLM_URL")):
        return _DEFAULT_CUSTOM_CONCURRENCY
    return 0


def _effective_timeout(url: Optional[str] = None) -> float:
    """Resolve the per-request timeout: explicit ROBODOG_LLM_TIMEOUT wins, else
    a longer default for a custom gateway (which tends to be slower on big
    prompts), else 120s."""
    raw = os.environ.get("ROBODOG_LLM_TIMEOUT")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    probe = url if url is not None else os.environ.get("ROBODOG_LLM_URL")
    return _DEFAULT_CUSTOM_TIMEOUT if _is_custom_gateway(probe) else _DEFAULT_TIMEOUT


def _openai_semaphore():
    """Shared BoundedSemaphore sized by the effective cap, or None (no cap)."""
    global _OPENAI_SEM, _OPENAI_SEM_N
    n = _effective_max_concurrency()
    if n <= 0:
        return None
    with _OPENAI_SEM_LOCK:
        if _OPENAI_SEM is None or _OPENAI_SEM_N != n:
            _OPENAI_SEM = threading.BoundedSemaphore(n)
            _OPENAI_SEM_N = n
        return _OPENAI_SEM


def _model_mismatch_hint(url: str, model: str) -> str:
    """
    Point out the common slip: an OpenRouter-style 'provider/model' id sent to
    OpenAI's real API (or vice versa), which surfaces as an opaque HTTP 400.
    """
    host = url.lower()
    if "api.openai.com" in host and "/" in model:
        return (f"\nHint: '{model}' looks like an OpenRouter-style model id "
                f"(provider/model), but this client is pointed at OpenAI's API "
                f"directly. Use --backend openrouter (or --backend auto) instead.")
    if "openrouter.ai" in host and "/" not in model:
        return (f"\nHint: OpenRouter model ids need a provider prefix, e.g. "
                f"'openai/{model}' or 'anthropic/{model}'.")
    return ""


def _http_error_hint(status: int, url: str, model: str, body: str = "") -> str:
    """
    One actionable line for the non-retryable HTTP failures users actually hit,
    appended to the raw error so nobody has to decode a bare status code.
    """
    if status in (401, 403):
        return ("\nHint: the API key was rejected. Check ROBODOG_LLM_KEY (env) "
                "or the KeePass 'OpenRouter'/'OpenAI' entry — the key may be "
                "missing, expired, or for a different provider.")
    if status == 402:
        return ("\nHint: the provider reports insufficient credits/quota for "
                "this key — top up or switch models.")
    if status == 404:
        b = (body or "").lower()
        # A 404 is usually one of two things: a bad MODEL id (the provider
        # served the endpoint but has no such model) or a wrong BASE URL.
        if ("no endpoints found" in b or "model_not_found" in b
                or "does not exist" in b or "not a valid model" in b):
            return (f"\nHint: the model id '{model}' isn't available on this "
                    "provider. Check the exact slug — OpenRouter uses "
                    "'vendor/model' (e.g. 'anthropic/claude-sonnet-4.6'); see "
                    "openrouter.ai/models. (If the model is correct, then verify "
                    "ROBODOG_LLM_URL points at the provider's API base.)")
        return (f"\nHint: nothing is served at {url} — the base URL is likely "
                "wrong. Check ROBODOG_LLM_URL (it should look like "
                "https://openrouter.ai/api/v1).")
    if status == 400:
        return _model_mismatch_hint(url, model)
    return ""


def _parse_retry_after(value) -> Optional[float]:
    """Parse an HTTP `Retry-After` header — either delta-seconds ("5") or an
    HTTP-date. Returns seconds to wait (>=0), or None if unparseable/absent."""
    if not value:
        return None
    try:
        return max(0.0, float(str(value).strip()))
    except (TypeError, ValueError):
        pass
    try:
        from email.utils import parsedate_to_datetime
        from datetime import timezone
        import time as _t
        when = parsedate_to_datetime(str(value))
        if when is not None:
            if when.tzinfo is None:      # non-compliant naive date -> treat as UTC
                when = when.replace(tzinfo=timezone.utc)
            return max(0.0, when.timestamp() - _t.time())
    except Exception:
        pass
    return None


# Approximate USD per 1M tokens (input, output), matched by substring on the
# model id. Rough by design — a ballpark $ figure for /stats, not billing. A
# custom gateway / unknown model returns None (shown as "—").
_PRICE_PER_1M = {
    "gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.0), "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.0, 8.0), "o1-mini": (1.10, 4.40), "o1": (15.0, 60.0),
    "o3-mini": (1.10, 4.40),
    "claude-3-5-haiku": (0.80, 4.0), "claude-3.5-haiku": (0.80, 4.0),
    "claude-3-5-sonnet": (3.0, 15.0), "claude-3.5-sonnet": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0), "claude-3-opus": (15.0, 75.0),
    "claude-opus-4": (15.0, 75.0), "claude-haiku": (0.80, 4.0),
    "gemini-1.5-flash": (0.075, 0.30), "gemini-1.5-pro": (1.25, 5.0),
    "gemini-2.0-flash": (0.10, 0.40), "llama-3": (0.10, 0.30),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int):
    """Ballpark USD cost for a token count, or None for an unknown/gateway model.
    Longest-key match wins so 'claude-3-5-sonnet' beats a 'claude' prefix."""
    m = (model or "").lower()
    best = None
    for key, price in _PRICE_PER_1M.items():
        if key in m and (best is None or len(key) > len(best[0])):
            best = (key, price)
    if best is None:
        return None
    pin, pout = best[1]
    return (prompt_tokens / 1e6) * pin + (completion_tokens / 1e6) * pout


def _backoff_delay(attempt: int, retry_after: Optional[float] = None,
                   cap: float = 60.0) -> float:
    """Jittered backoff for a retry. Honors a server `Retry-After` (waits at
    least that long) and otherwise uses exponential backoff with full jitter so
    concurrent clients don't retry in lockstep and hammer a struggling gateway."""
    import random
    if retry_after is not None:
        return min(cap, max(0.5, retry_after)) + random.uniform(0.0, 0.5)
    exp = min(2.0 ** (attempt - 1), cap)
    return max(0.5, random.uniform(exp * 0.5, exp))   # full-ish jitter


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
    # OpenAI-style stop reason: "stop" | "length" | "tool_calls" | "" (unknown).
    # "length" means the model was CUT OFF at max_tokens — the text may end
    # mid-tool-call and must not be treated as a finished answer.
    finish_reason: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


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
        self.max_tokens_seen: List[int] = []  # records max_tokens on every call, for tests

    def complete(self, prompt, context="", max_tokens=8192, temperature=0.3) -> Completion:
        self.max_tokens_seen.append(max_tokens)
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
                delay = _backoff_delay(attempt)   # jittered exponential backoff
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
                 timeout: Optional[float] = None, max_attempts: int = 4,
                 on_retry: Optional[Callable[[int, int, float, str], None]] = None,
                 session=None):
        if not base_url or not api_key or not model:
            raise ValueError("OpenAICompatClient requires base_url, api_key, model")
        # Per-request timeout: explicit arg, else ROBODOG_LLM_TIMEOUT, else a
        # URL-aware default (custom gateway gets a longer budget). Resolved
        # against the normalized URL below, so compute it after self.url is set.
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
        self.timeout = timeout if timeout is not None else _effective_timeout(self.url)
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
        # Serialize against the shared cap (if set) so a parallel subagent
        # fan-out doesn't overwhelm a slow gateway. Held across retries so a
        # struggling call doesn't multiply concurrent load.
        sem = _openai_semaphore()
        if sem is not None:
            sem.acquire()
        try:
            last_err = "unknown"
            for attempt in range(1, self.max_attempts + 1):
                retry_after = None   # set from a 429/503 Retry-After header
                try:
                    # Split timeout: a short connect budget (a dead/unreachable
                    # host fails fast) + the full read budget (a slow gateway
                    # gets time to respond). This is what tells a "can't reach"
                    # apart from a "reached it but it's slow to answer".
                    resp = self._session.post(
                        self.url, json=payload, timeout=(10, self.timeout),
                        headers={"Authorization": f"Bearer {self.api_key}",
                                 "HTTP-Referer": self.referer})
                    if resp.status_code == 200:
                        # A 200 with a garbled/missing body (proxy hiccup, SSE where
                        # JSON was expected) must be RETRIED, not crash the turn.
                        try:
                            data = resp.json()
                            choice = (data.get("choices") or [{}])[0]
                            msg = choice.get("message") or {}
                            text = msg.get("content") or ""
                            usage = data.get("usage") or {}
                        except (ValueError, TypeError, KeyError, IndexError):
                            last_err = "malformed 200 response (unparseable body)"
                            text = ""
                        if text and text.strip():
                            return Completion(
                                text=text,
                                prompt_tokens=usage.get("prompt_tokens", 0),
                                completion_tokens=usage.get("completion_tokens", 0),
                                raw=data,
                                finish_reason=(choice.get("finish_reason") or ""))
                        if not last_err.startswith("malformed"):
                            last_err = "empty response"
                    elif resp.status_code == 402:
                        # Payment required. OpenRouter says how many tokens the
                        # balance CAN afford ("can only afford 1074"); if it's less
                        # than we asked for, shrink max_tokens and retry so the turn
                        # succeeds instead of failing every time. Only truly-broke
                        # (afford too small / no number) falls through to an error.
                        body = resp.text or ""
                        m = re.search(r"can only afford (\d+)", body)
                        afford = int(m.group(1)) if m else 0
                        cur = payload.get("max_tokens") or max_tokens
                        if afford >= 256 and afford < cur:
                            payload["max_tokens"] = afford - 16   # small safety margin
                            last_err = (f"HTTP 402 — shrinking max_tokens to "
                                        f"{payload['max_tokens']} (credit-limited) and retrying")
                            retry_after = 0.0   # no backoff; it's a config retry
                        else:
                            raise RuntimeError(
                                f"LLM HTTP 402 (out of credits): {resp.text[:200]} — "
                                f"add credits at openrouter.ai/settings, or lower "
                                f"--max-tokens / ROBODOG_MAX_TOKENS below the affordable "
                                f"amount ({afford or 'unknown'}).")
                    elif resp.status_code in (429,) or resp.status_code >= 500:
                        last_err = f"HTTP {resp.status_code}"
                        # Honor the server's backoff ask on rate-limit / overload.
                        retry_after = _parse_retry_after(
                            resp.headers.get("Retry-After"))
                    else:
                        hint = _http_error_hint(resp.status_code, self.url, self.model, resp.text)
                        raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:300]}{hint}")
                except _rq.ConnectTimeout:
                    last_err = ("connect timeout (>10s to reach the host — VPN down, "
                                "wrong URL, or the gateway is unreachable)")
                except _rq.ReadTimeout:
                    last_err = (f"read timeout after {self.timeout:.0f}s (the gateway "
                                "accepted the request but didn't answer in time — it's "
                                "slow/overloaded, or the prompt is large. Raise "
                                "ROBODOG_LLM_TIMEOUT, or shrink the request)")
                except _rq.ConnectionError as exc:
                    last_err = f"connection error ({type(exc).__name__}) — host/network unreachable"
                except _rq.Timeout as exc:
                    last_err = f"timeout ({type(exc).__name__})"
                if attempt < self.max_attempts:
                    delay = _backoff_delay(attempt, retry_after)
                    self.on_retry(attempt, self.max_attempts, delay, last_err)
                    time.sleep(delay)
            raise RuntimeError(f"LLM failed after {self.max_attempts} attempts: {last_err}")
        finally:
            if sem is not None:
                sem.release()

    def diagnose(self, prompt: str = "ping", max_tokens: int = 5) -> dict:
        """One-shot TIMED probe for /test — no retries. Returns a dict with
        {ok, status, elapsed, detail} describing exactly what happened (a fast
        connect failure vs a slow read timeout vs an HTTP error), so a user
        chasing gateway timeouts can see the phase and the latency. Never raises."""
        import time as _t
        import requests as _rq
        payload = {"model": self.model, "temperature": 0, "max_tokens": max_tokens,
                   "messages": [{"role": "user", "content": prompt}]}
        t0 = _t.time()
        try:
            resp = self._session.post(
                self.url, json=payload, timeout=(10, self.timeout),
                headers={"Authorization": f"Bearer {self.api_key}",
                         "HTTP-Referer": self.referer})
            elapsed = _t.time() - t0
            if resp.status_code == 200:
                try:
                    txt = ((resp.json().get("choices") or [{}])[0]
                           .get("message", {}).get("content") or "").strip()
                except Exception:
                    txt = ""
                return {"ok": True, "status": 200, "elapsed": elapsed,
                        "detail": f"replied in {elapsed:.1f}s"
                                  + (f": {txt[:50]!r}" if txt else " (empty body)")}
            hint = _http_error_hint(resp.status_code, self.url, self.model, resp.text)
            return {"ok": False, "status": resp.status_code, "elapsed": elapsed,
                    "detail": f"HTTP {resp.status_code} in {elapsed:.1f}s"
                              f"{(' — ' + resp.text[:160]) if resp.text else ''}{hint}"}
        except _rq.ConnectTimeout:
            return {"ok": False, "status": None, "elapsed": _t.time() - t0,
                    "detail": "connect timeout (>10s) — can't reach the host "
                              "(VPN down, wrong ROBODOG_LLM_URL, or gateway offline)"}
        except _rq.ReadTimeout:
            return {"ok": False, "status": None, "elapsed": _t.time() - t0,
                    "detail": f"read timeout after {self.timeout:.0f}s — connected to the "
                              "gateway but it never answered even a tiny request. It's "
                              "slow/overloaded (not a robodog issue). Raise "
                              "ROBODOG_LLM_TIMEOUT, or check the gateway/model health."}
        except Exception as exc:
            return {"ok": False, "status": None, "elapsed": _t.time() - t0,
                    "detail": f"{type(exc).__name__}: {str(exc)[:160]}"}


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
