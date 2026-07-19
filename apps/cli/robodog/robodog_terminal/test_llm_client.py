# file: robodog_terminal/test_llm_client.py
"""
Tests for llm_client.py: ElsaClient wire format + retry/backoff/empty-guard,
OpenAICompatClient URL normalization + retry, EchoClient, factory.
Run: python robodog_terminal/test_llm_client.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import robodog_terminal.llm_client as lc  # noqa: E402
from robodog_terminal.llm_client import (Completion, EchoClient, ElsaClient,  # noqa: E402
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


def elsa_payload(txt):
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

    # ---- ElsaClient wire format ------------------------------------------
    ec = ElsaClient(endpoint="https://x/runPixel", engine_id="ENG",
                    access_key="a", secret_key="s", session=FakeSession([]))
    expr = ec._build_expression("What?", "sys ctx", 8192, 0.3)
    check('engine = "ENG"' in expr and "<encode>What?</encode>" in expr
          and "<encode>sys ctx</encode>" in expr and "useHistory=false" in expr
          and '"max_completion_tokens": 8192' in expr, "expression matches FDA guide")
    ec_h = ElsaClient(endpoint="https://x/r", engine_id="E", access_key="a",
                      secret_key="s", use_history=True, session=FakeSession([]))
    check("useHistory=true" in ec_h._build_expression("q", "", 100, 0.1),
          "useHistory=true wired")
    comp = ElsaClient._parse(elsa_payload("The FDA regulates..."))
    check(comp.text == "The FDA regulates..." and comp.total_tokens == 12,
          "response parse extracts text + tokens")
    try:
        ElsaClient._parse({"bogus": 1})
        check(False, "bad shape raises")
    except RuntimeError:
        check(True, "bad response shape raises RuntimeError")
    try:
        ElsaClient(endpoint="", engine_id="e", access_key="a", secret_key="s")
        check(False, "missing endpoint raises")
    except ValueError:
        check(True, "missing endpoint raises ValueError")
    try:
        ElsaClient(endpoint="x", engine_id="e", access_key="", secret_key="s")
        check(False, "missing key raises")
    except ValueError:
        check(True, "missing key raises ValueError")

    # ---- ElsaClient retry/backoff ---------------------------------------
    retries = []

    def mk(responses, attempts=4):
        return ElsaClient(endpoint="https://x/runPixel", engine_id="e",
                          access_key="a", secret_key="s",
                          session=FakeSession(responses), max_attempts=attempts,
                          on_retry=lambda a, m, d, r: retries.append((a, d, r)))

    retries.clear()
    cl = mk([FakeResp(500, text="boom"), FakeResp(500, text="boom"),
             FakeResp(200, elsa_payload("hello"))])
    check(cl.complete("hi").text == "hello" and len(retries) == 2
          and retries[0][1] == 1 and retries[1][1] == 2,
          "5xx retried with 1s,2s backoff")
    retries.clear()
    cl = mk([FakeResp(200, elsa_payload("")), FakeResp(200, elsa_payload("ok"))])
    check(cl.complete("hi").text == "ok" and "empty" in retries[0][2],
          "empty response retried")
    retries.clear()
    cl = mk([requests.ConnectionError("refused"), FakeResp(200, elsa_payload("ok"))])
    check(cl.complete("hi").text == "ok" and "network" in retries[0][2],
          "network error retried")
    retries.clear()
    cl = mk([FakeResp(429, text="slow down"), FakeResp(200, elsa_payload("ok"))])
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

    # ---- factory ---------------------------------------------------------
    check(isinstance(build_client_from_config(None), EchoClient),
          "factory: None -> EchoClient")
    check(isinstance(build_client_from_config({"protocol": "echo"}), EchoClient),
          "factory: echo protocol")
    cl = build_client_from_config({"protocol": "elsa", "endpoint": "https://x/r",
                                   "engine_id": "e", "access_key": "a",
                                   "secret_key": "s"})
    check(isinstance(cl, ElsaClient), "factory: elsa protocol")
    try:
        build_client_from_config({"protocol": "nope"})
        check(False, "unknown protocol raises")
    except ValueError:
        check(True, "factory: unknown protocol raises")

    print("\nLLM CLIENT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
