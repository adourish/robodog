# file: robodog_terminal/test_llm_client.py
"""
Tests for llm_client.py: GatewayClient wire format + retry/backoff/empty-guard,
OpenAICompatClient URL normalization + retry, EchoClient, factory.
Run: python robodog_terminal/test_llm_client.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import robodog_terminal.llm_client as lc  # noqa: E402
from robodog_terminal.llm_client import (Completion, EchoClient, GatewayClient,  # noqa: E402
                                 OpenAICompatClient, build_client_from_config)

lc.time.sleep = lambda s: None  # no real waiting

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


class FakeResp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._p = payload
        self.text = text
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def gateway_payload(txt):
    return {"pixelReturn": [{"output": {
        "response": txt, "numberOfTokensInPrompt": 5,
        "numberOfTokensInResponse": 7}}]}


def oai_payload(txt):
    return {"choices": [{"message": {"content": txt}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4}}


def main() -> int:
    global ok
    import requests

    # ---- Completion ------------------------------------------------------
    c = Completion(text="x", prompt_tokens=2, completion_tokens=3)
    check(c.total_tokens == 5, "Completion.total_tokens sums")

    # ---- EchoClient ------------------------------------------------------
    e = EchoClient(script=["a", "b"])
    check(e.complete("p").text == "a" and e.complete("p").text == "b"
          and e.complete("p").text == "b", "EchoClient list script repeats last")
    e2 = EchoClient(script=lambda p, ctx: f"cb:{len(p)}")
    check(e2.complete("12345").text == "cb:5", "EchoClient callable script")
    e3 = EchoClient()
    check("(echo)" in e3.complete("hi").text, "EchoClient default echoes")

    # ---- GatewayClient wire format ------------------------------------------
    ec = GatewayClient(endpoint="https://x/runPixel", engine_id="ENG",
                    access_key="a", secret_key="s", session=FakeSession([]))
    expr = ec._build_expression("What?", "sys ctx", 8192, 0.3)
    check('engine = "ENG"' in expr and "<encode>What?</encode>" in expr
          and "<encode>sys ctx</encode>" in expr and "useHistory=false" in expr
          and '"max_completion_tokens": 8192' in expr, "expression matches gateway spec")
    ec_h = GatewayClient(endpoint="https://x/r", engine_id="E", access_key="a",
                      secret_key="s", use_history=True, session=FakeSession([]))
    check("useHistory=true" in ec_h._build_expression("q", "", 100, 0.1),
          "useHistory=true wired")
    comp = GatewayClient._parse(gateway_payload("The service returns text..."))
    check(comp.text == "The service returns text..." and comp.total_tokens == 12,
          "response parse extracts text + tokens")
    try:
        GatewayClient._parse({"bogus": 1})
        check(False, "bad shape raises")
    except RuntimeError:
        check(True, "bad response shape raises RuntimeError")
    try:
        GatewayClient(endpoint="", engine_id="e", access_key="a", secret_key="s")
        check(False, "missing endpoint raises")
    except ValueError:
        check(True, "missing endpoint raises ValueError")
    try:
        GatewayClient(endpoint="x", engine_id="e", access_key="", secret_key="s")
        check(False, "missing key raises")
    except ValueError:
        check(True, "missing key raises ValueError")

    # ---- GatewayClient retry/backoff ---------------------------------------
    retries = []

    def mk(responses, attempts=4):
        return GatewayClient(endpoint="https://x/runPixel", engine_id="e",
                          access_key="a", secret_key="s",
                          session=FakeSession(responses), max_attempts=attempts,
                          on_retry=lambda a, m, d, r: retries.append((a, d, r)))

    retries.clear()
    cl = mk([FakeResp(500, text="boom"), FakeResp(500, text="boom"),
             FakeResp(200, gateway_payload("hello"))])
    check(cl.complete("hi").text == "hello" and len(retries) == 2
          and 0.5 <= retries[0][1] <= 1.0 and 1.0 <= retries[1][1] <= 2.0,
          "5xx retried with jittered exponential backoff (~[0.5,1], ~[1,2])")
    retries.clear()
    cl = mk([FakeResp(200, gateway_payload("")), FakeResp(200, gateway_payload("ok"))])
    check(cl.complete("hi").text == "ok" and "empty" in retries[0][2],
          "empty response retried")
    retries.clear()
    cl = mk([requests.ConnectionError("refused"), FakeResp(200, gateway_payload("ok"))])
    check(cl.complete("hi").text == "ok" and "network" in retries[0][2],
          "network error retried")
    retries.clear()
    cl = mk([FakeResp(429, text="slow down"), FakeResp(200, gateway_payload("ok"))])
    check(cl.complete("hi").text == "ok" and len(retries) == 1, "429 retried")
    retries.clear()
    cl = mk([FakeResp(401, text="unauthorized")])
    try:
        cl.complete("hi")
        check(False, "401 fails fast")
    except RuntimeError as exc:
        check("401" in str(exc) and not retries, "401 fails fast, no retry")
    retries.clear()
    cl = mk([FakeResp(500, text="x")] * 4)
    try:
        cl.complete("hi")
        check(False, "exhaustion raises")
    except RuntimeError as exc:
        check("after 4 attempts" in str(exc) and len(retries) == 3,
              "raises after max attempts (3 retries)")
    retries.clear()
    cl = mk([requests.Timeout("slow")] * 4)
    try:
        cl.complete("hi")
        check(False, "timeout exhaustion raises")
    except RuntimeError:
        check(len(retries) == 3, "timeouts retried then raise")

    # ---- OpenAICompatClient ----------------------------------------------
    for base, want in [
        ("https://api.openai.com", "https://api.openai.com/v1/chat/completions"),
        ("https://openrouter.ai/api", "https://openrouter.ai/api/v1/chat/completions"),
        ("https://x.y/v1", "https://x.y/v1/chat/completions"),
        ("https://x.y/v1/chat/completions", "https://x.y/v1/chat/completions"),
    ]:
        oc = OpenAICompatClient(base_url=base, api_key="k", model="m",
                                session=FakeSession([]))
        check(oc.url == want, f"URL normalized: {base} -> {want.split('//')[1][:30]}…")

    sess = FakeSession([FakeResp(200, oai_payload("hi there"))])
    oc = OpenAICompatClient(base_url="https://api.openai.com", api_key="k",
                            model="m", session=sess)
    comp = oc.complete("q", context="sys")
    check(comp.text == "hi there" and comp.total_tokens == 7,
          "openai-compat parses choices+usage")
    body = sess.calls[0][1]["json"]
    check(body["messages"][0] == {"role": "system", "content": "sys"}
          and body["messages"][1]["role"] == "user", "system+user messages built")

    oretries = []
    oc = OpenAICompatClient(base_url="https://x", api_key="k", model="m",
                            session=FakeSession([FakeResp(500, text="err"),
                                                 FakeResp(200, oai_payload("ok"))]),
                            on_retry=lambda a, m_, d, r: oretries.append(r))
    check(oc.complete("q").text == "ok" and len(oretries) == 1,
          "openai-compat retries 5xx")
    oc = OpenAICompatClient(base_url="https://x", api_key="k", model="m",
                            session=FakeSession([FakeResp(404, text="nf")]))
    try:
        oc.complete("q")
        check(False, "404 fails fast")
    except RuntimeError as exc:
        check("404" in str(exc), "openai-compat 404 fails fast")

    # (3.2) A garbled 200 (no 'choices' / unparseable body) is RETRIED, not a crash.
    oretries.clear()
    oc = OpenAICompatClient(base_url="https://x", api_key="k", model="m",
                            session=FakeSession([FakeResp(200, {"unexpected": "shape"}),
                                                 FakeResp(200, oai_payload("recovered"))]),
                            on_retry=lambda a, m_, d, r: oretries.append(r))
    check(oc.complete("q").text == "recovered" and len(oretries) == 1,
          "malformed 200 (missing choices) is retried, not a crash")

    class _BadJSON(FakeResp):
        def json(self):
            raise ValueError("not json (SSE?)")
    oretries.clear()
    oc = OpenAICompatClient(base_url="https://x", api_key="k", model="m",
                            session=FakeSession([_BadJSON(200, text="data: ..."),
                                                 FakeResp(200, oai_payload("ok2"))]),
                            on_retry=lambda a, m_, d, r: oretries.append(r))
    check(oc.complete("q").text == "ok2" and "malformed" in oretries[0],
          "a 200 whose body won't parse as JSON is retried")

    # ---- backend/model mismatch hint --------------------------------------
    oc = OpenAICompatClient(base_url="https://api.openai.com", api_key="k",
                            model="anthropic/claude-sonnet-4.6",
                            session=FakeSession([FakeResp(400, text="invalid model ID")]))
    try:
        oc.complete("q")
        check(False, "openai + provider-prefixed model raises")
    except RuntimeError as exc:
        check("--backend openrouter" in str(exc),
              "hints --backend openrouter for OpenAI + provider-prefixed model")

    oc = OpenAICompatClient(base_url="https://openrouter.ai/api", api_key="k",
                            model="gpt-4o",
                            session=FakeSession([FakeResp(400, text="invalid model ID")]))
    try:
        oc.complete("q")
        check(False, "openrouter + bare model raises")
    except RuntimeError as exc:
        check("provider prefix" in str(exc),
              "hints provider prefix for OpenRouter + bare model")

    # no hint when model/backend actually match
    oc = OpenAICompatClient(base_url="https://api.openai.com", api_key="k",
                            model="gpt-4o-mini",
                            session=FakeSession([FakeResp(400, text="bad request")]))
    try:
        oc.complete("q")
        check(False, "matched backend/model still raises")
    except RuntimeError as exc:
        check("Hint:" not in str(exc), "no spurious hint for matched backend/model")

    # ---- actionable hints for 401 / 402 / 404 -----------------------------
    for status, want, label in [
        (401, "ROBODOG_LLM_KEY", "401 hints at the key source"),
        (403, "ROBODOG_LLM_KEY", "403 hints at the key source"),
        (402, "credits", "402 hints at credits/quota"),
        (404, "ROBODOG_LLM_URL", "404 hints at the base URL"),
    ]:
        oc = OpenAICompatClient(base_url="https://openrouter.ai/api", api_key="k",
                                model="anthropic/claude-sonnet-4.6",
                                session=FakeSession([FakeResp(status, text="err")]))
        try:
            oc.complete("q")
            check(False, f"HTTP {status} raises")
        except RuntimeError as exc:
            check(want in str(exc) and f"{status}" in str(exc), label)
    oc = OpenAICompatClient(base_url="https://x", api_key="k", model="m",
                            max_attempts=2,
                            session=FakeSession([FakeResp(200, oai_payload("")),
                                                 FakeResp(200, oai_payload(""))]),
                            on_retry=lambda *a: None)
    try:
        oc.complete("q")
        check(False, "empty exhaustion raises")
    except RuntimeError as exc:
        check("empty" in str(exc), "openai-compat empty response exhausts")
    try:
        OpenAICompatClient(base_url="", api_key="k", model="m")
        check(False, "missing base raises")
    except ValueError:
        check(True, "openai-compat missing base_url raises")

    # ---- model passthrough across providers ------------------------------
    # Every provider/model the CLI can target must be sent verbatim in the
    # request body's `model` field, at the correctly-normalized endpoint.
    PROVIDER_MODELS = [
        ("https://openrouter.ai/api", "anthropic/claude-sonnet-4.6",
         "https://openrouter.ai/api/v1/chat/completions"),
        ("https://openrouter.ai/api", "openai/gpt-4o",
         "https://openrouter.ai/api/v1/chat/completions"),
        ("https://openrouter.ai/api", "google/gemini-2.0-flash-001",
         "https://openrouter.ai/api/v1/chat/completions"),
        ("https://openrouter.ai/api", "meta-llama/llama-3.3-70b-instruct",
         "https://openrouter.ai/api/v1/chat/completions"),
        ("https://openrouter.ai/api", "deepseek/deepseek-chat",
         "https://openrouter.ai/api/v1/chat/completions"),
        ("https://api.openai.com", "gpt-4o-mini",
         "https://api.openai.com/v1/chat/completions"),
        ("https://api.groq.com/openai", "llama-3.1-8b-instant",
         "https://api.groq.com/openai/v1/chat/completions"),
        ("https://api.together.xyz", "mistralai/Mixtral-8x7B-Instruct-v0.1",
         "https://api.together.xyz/v1/chat/completions"),
        ("http://localhost:11434", "qwen2.5-coder:7b",
         "http://localhost:11434/v1/chat/completions"),
    ]
    for base, model, want_url in PROVIDER_MODELS:
        sess = FakeSession([FakeResp(200, oai_payload("ok"))])
        oc = OpenAICompatClient(base_url=base, api_key="k", model=model, session=sess)
        oc.complete("hi")
        body = sess.calls[0][1]["json"]
        check(oc.url == want_url and body["model"] == model,
              f"model passthrough: {model} @ {base.split('//')[1][:22]}…")

    # temperature + max_tokens flow into the body verbatim
    sess = FakeSession([FakeResp(200, oai_payload("ok"))])
    oc = OpenAICompatClient(base_url="https://x", api_key="k", model="m", session=sess)
    oc.complete("hi", context="", max_tokens=1234, temperature=0.7)
    body = sess.calls[0][1]["json"]
    check(body["max_tokens"] == 1234 and body["temperature"] == 0.7,
          "openai-compat: max_tokens+temperature in body")

    # gateway engine_id passthrough for varied engine names
    for eng in ["claude-sonnet", "gpt-4o-azure", "llama3-70b", "engine_123"]:
        gc = GatewayClient(endpoint="https://x/r", engine_id=eng, access_key="a",
                           secret_key="s", session=FakeSession([]))
        check(f'engine = "{eng}"' in gc._build_expression("q", "", 100, 0.2),
              f"gateway engine passthrough: {eng}")

    # ---- surrogate cleaning on the wire (all backends) -------------------
    # A split emoji from a Windows clipboard paste = lone hi+lo surrogates.
    SURR = "fix bug 🐕 in " + chr(0xD800) + "core.py"
    has_surr = lambda s: any(0xD800 <= ord(c) <= 0xDFFF for c in (s or ""))
    check(has_surr(SURR), "test fixture actually contains surrogates")

    # EchoClient: no crash, and echoed token counts computed on clean text
    check(EchoClient(script=["done"]).complete(SURR, context=SURR).text == "done",
          "EchoClient survives surrogate prompt+context")

    # OpenAICompatClient: body sent to the wire is surrogate-free & utf-8 encodable
    sess = FakeSession([FakeResp(200, oai_payload("ok"))])
    oc = OpenAICompatClient(base_url="https://x", api_key="k", model="m", session=sess)
    oc.complete(SURR, context=SURR)
    sent = sess.calls[0][1]["json"]
    wire = sent["messages"][0]["content"] + sent["messages"][1]["content"]
    check(not has_surr(wire), "openai-compat strips surrogates before send")
    try:
        (wire).encode("utf-8"); check(True, "openai-compat body is utf-8 encodable")
    except UnicodeEncodeError:
        check(False, "openai-compat body is utf-8 encodable")

    # GatewayClient: the form-url-encoded expression is surrogate-free
    gc = GatewayClient(endpoint="https://x/r", engine_id="e", access_key="a",
                       secret_key="s", session=FakeSession([FakeResp(200, gateway_payload("ok"))]))
    gc.complete(SURR, context=SURR)
    check(True, "gateway survives surrogate prompt without crashing")

    # ---- factory ---------------------------------------------------------
    check(isinstance(build_client_from_config(None), EchoClient),
          "factory: None -> EchoClient")
    check(isinstance(build_client_from_config({"protocol": "echo"}), EchoClient),
          "factory: echo protocol")
    cl = build_client_from_config({"protocol": "gateway", "endpoint": "https://x/r",
                                   "engine_id": "e", "access_key": "a",
                                   "secret_key": "s"})
    check(isinstance(cl, GatewayClient), "factory: gateway protocol")
    try:
        build_client_from_config({"protocol": "nope"})
        check(False, "unknown protocol raises")
    except ValueError:
        check(True, "factory: unknown protocol raises")

    # ---- concurrency cap (ROBODOG_LLM_MAX_CONCURRENCY) -------------------
    # Parallel subagents share one client; a cap serializes requests so a slow
    # gateway isn't overwhelmed. Verify the semaphore selection + throttling.
    import os as _os
    import threading as _th
    _saved = _os.environ.get("ROBODOG_LLM_MAX_CONCURRENCY")
    _saved_url = _os.environ.get("ROBODOG_LLM_URL")
    try:
        _os.environ.pop("ROBODOG_LLM_MAX_CONCURRENCY", None)
        _os.environ.pop("ROBODOG_LLM_URL", None)
        lc._OPENAI_SEM = None
        check(lc._openai_semaphore() is None, "no cap, no url -> no semaphore (unbounded)")

        # a known fast provider stays uncapped by default
        _os.environ["ROBODOG_LLM_URL"] = "https://openrouter.ai/api/v1"
        check(lc._effective_max_concurrency() == 0, "openrouter url -> uncapped default")
        # a CUSTOM gateway auto-caps out of the box (no env var needed)
        _os.environ["ROBODOG_LLM_URL"] = "https://elsa.example/Monolith/api/model/openai"
        check(lc._effective_max_concurrency() == lc._DEFAULT_CUSTOM_CONCURRENCY,
              "custom gateway url -> auto concurrency cap")
        # explicit env always wins over the auto-default
        _os.environ["ROBODOG_LLM_MAX_CONCURRENCY"] = "1"
        check(lc._effective_max_concurrency() == 1, "explicit cap wins over auto-default")
        _os.environ.pop("ROBODOG_LLM_MAX_CONCURRENCY", None)

        # timeout: custom gateway gets a longer default; explicit wins
        _os.environ.pop("ROBODOG_LLM_TIMEOUT", None)
        _os.environ["ROBODOG_LLM_URL"] = "https://elsa.example/Monolith/api/model/openai"
        check(lc._effective_timeout() == lc._DEFAULT_CUSTOM_TIMEOUT,
              "custom gateway -> longer default timeout")
        _os.environ["ROBODOG_LLM_URL"] = "https://openrouter.ai/api/v1"
        check(lc._effective_timeout() == lc._DEFAULT_TIMEOUT,
              "known provider -> standard default timeout")
        _os.environ["ROBODOG_LLM_TIMEOUT"] = "600"
        check(lc._effective_timeout() == 600.0, "explicit ROBODOG_LLM_TIMEOUT wins")
        _os.environ.pop("ROBODOG_LLM_TIMEOUT", None)
        _os.environ.pop("ROBODOG_LLM_URL", None)

        _os.environ["ROBODOG_LLM_MAX_CONCURRENCY"] = "2"
        lc._OPENAI_SEM = None
        check(lc._openai_semaphore() is not None, "cap set -> semaphore created")

        active = {"now": 0, "max": 0}
        lk = _th.Lock()

        class _SlowResp:
            status_code = 200
            def json(self):
                return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

        class _SlowSession:
            def post(self, *a, **k):
                with lk:
                    active["now"] += 1
                    active["max"] = max(active["max"], active["now"])
                _th.Event().wait(0.1)   # real delay (time.sleep is no-op'd here)
                with lk:
                    active["now"] -= 1
                return _SlowResp()

        def _worker():
            OpenAICompatClient(base_url="https://x", api_key="k", model="m",
                               session=_SlowSession()).complete("hi")

        threads = [_th.Thread(target=_worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        check(active["max"] <= 2,
              f"6 concurrent calls throttled to the cap of 2 (peak {active['max']})")
    finally:
        for _k, _v in (("ROBODOG_LLM_MAX_CONCURRENCY", _saved),
                       ("ROBODOG_LLM_URL", _saved_url)):
            if _v is None:
                _os.environ.pop(_k, None)
            else:
                _os.environ[_k] = _v
        lc._OPENAI_SEM = None

    # ---- error classification: connect vs read timeout ------------------
    import requests as _requests

    class _RaiseSession:
        def __init__(self, exc):
            self.exc = exc
        def post(self, *a, **k):
            raise self.exc

    oc = OpenAICompatClient(base_url="https://x", api_key="k", model="m",
                            max_attempts=1, on_retry=lambda *a: None,
                            session=_RaiseSession(_requests.exceptions.ReadTimeout()))
    try:
        oc.complete("q")
        check(False, "read timeout raises")
    except RuntimeError as exc:
        check("read timeout" in str(exc) and "ROBODOG_LLM_TIMEOUT" in str(exc),
              "ReadTimeout -> 'gateway didn't answer' message + timeout hint")
    oc = OpenAICompatClient(base_url="https://x", api_key="k", model="m",
                            max_attempts=1, on_retry=lambda *a: None,
                            session=_RaiseSession(_requests.exceptions.ConnectTimeout()))
    try:
        oc.complete("q")
        check(False, "connect timeout raises")
    except RuntimeError as exc:
        check("connect timeout" in str(exc) and "reach the host" in str(exc),
              "ConnectTimeout -> 'can't reach the host' message")

    # ---- diagnose(): one-shot timed probe -------------------------------
    class _OKResp:
        status_code = 200
        text = ""
        def json(self):
            return {"choices": [{"message": {"content": "pong"}}], "usage": {}}
    d = OpenAICompatClient(base_url="https://x", api_key="k", model="m",
                           session=type("S", (), {"post": lambda self, *a, **k: _OKResp()})())
    r = d.diagnose()
    check(r["ok"] is True and r["status"] == 200 and "replied in" in r["detail"],
          "diagnose: 200 -> ok with latency + reply")

    d2 = OpenAICompatClient(base_url="https://x", api_key="k", model="m",
                            session=_RaiseSession(_requests.exceptions.ReadTimeout()))
    r = d2.diagnose()
    check(r["ok"] is False and "read timeout" in r["detail"]
          and "slow/overloaded" in r["detail"],
          "diagnose: ReadTimeout -> not-ok, explains the gateway is slow")

    class _Resp401:
        status_code = 401
        text = "Unauthorized"
        def json(self):
            return {}
    d3 = OpenAICompatClient(base_url="https://api.openai.com", api_key="k", model="m",
                            session=type("S", (), {"post": lambda self, *a, **k: _Resp401()})())
    r = d3.diagnose()
    check(r["ok"] is False and r["status"] == 401,
          "diagnose: HTTP 401 reported with status")

    # ---- gateway resilience (roadmap 3.1): Retry-After + jittered backoff ----
    import email.utils as _eu, time as _tt
    from robodog_terminal.llm_client import _parse_retry_after, _backoff_delay
    check(_parse_retry_after("5") == 5.0 and _parse_retry_after(" 12 ") == 12.0,
          "Retry-After: delta-seconds parsed")
    check(_parse_retry_after(None) is None and _parse_retry_after("garbage") is None,
          "Retry-After: absent/garbage -> None")
    _ra = _parse_retry_after(_eu.formatdate(_tt.time() + 30, usegmt=True))
    check(_ra is not None and 20 < _ra <= 31, "Retry-After: HTTP-date -> seconds-from-now")
    check(all(5.0 <= _backoff_delay(1, retry_after=5.0) <= 6.0 for _ in range(30)),
          "backoff honors Retry-After (waits >= it, small jitter)")
    _delays = {round(_backoff_delay(a), 3) for a in range(1, 6) for _ in range(20)}
    check(all(0.5 <= d <= 60.0 for d in _delays) and len(_delays) > 20,
          "backoff is jittered (varies) and bounded to [0.5, 60]s")
    check(_backoff_delay(20, retry_after=9999) <= 60.5,
          "backoff caps a huge Retry-After at ~60s")

    print("\nLLM CLIENT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
