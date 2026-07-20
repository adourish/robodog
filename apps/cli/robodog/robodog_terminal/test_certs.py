# file: robodog_terminal/test_certs.py
"""
Tests for certs.py: URL host/port parsing, PEM parsing, chain capture against
a REAL public host (skipped offline), file writing, and the /cert command
dispatch (host from ROBODOG_LLM_URL, out from REQUESTS_CA_BUNDLE, usage errors).
Run: python robodog_terminal/test_certs.py   (from robodogcli/robodog)
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal import certs  # noqa: E402

ok = True


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def _online(host="pypi.org") -> bool:
    try:
        socket.create_connection((host, 443), timeout=8)
        return True
    except Exception:
        return False


def main() -> int:
    global ok

    # ---- URL host/port parsing -------------------------------------------
    check(certs.host_port_from_url(
        "https://elsa.example/Monolith/api/model/openai") == ("elsa.example", 443),
        "host_port_from_url: default 443")
    check(certs.host_port_from_url("https://api.groq.com:8443/v1") == ("api.groq.com", 8443),
          "host_port_from_url: explicit port")
    check(certs.host_port_from_url("bare-host.local") == ("bare-host.local", 443),
          "host_port_from_url: bare host gets https + 443")
    check(certs.host_port_from_url("not a url at all with spaces") is None
          or certs.host_port_from_url("://")  is None,
          "host_port_from_url: junk -> None")

    # ---- PEM regex --------------------------------------------------------
    two = ("-----BEGIN CERTIFICATE-----\nAAA\n-----END CERTIFICATE-----\n"
           "noise\n-----BEGIN CERTIFICATE-----\nBBB\n-----END CERTIFICATE-----")
    check(len(certs._PEM_RE.findall(two)) == 2, "PEM regex finds multiple blocks")

    # ---- /cert dispatch: usage errors (no network needed) ----------------
    saved = {k: os.environ.get(k) for k in ("ROBODOG_LLM_URL", "REQUESTS_CA_BUNDLE")}
    try:
        os.environ.pop("ROBODOG_LLM_URL", None)
        os.environ.pop("REQUESTS_CA_BUNDLE", None)
        good, msg = certs.handle("")
        check(not good and "usage" in msg.lower() and "ROBODOG_LLM_URL" in msg,
              "/cert with no host and no ROBODOG_LLM_URL -> usage")
        good, msg = certs.handle("some-host.example")
        check(not good and "REQUESTS_CA_BUNDLE" in msg,
              "/cert host but no out path -> points at REQUESTS_CA_BUNDLE")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # ---- unreachable host fails cleanly (no raise) -----------------------
    out = str(Path(tempfile.mkdtemp(prefix="rd_cert_")) / "ca.pem")
    good, msg = certs.capture_to_file("no-such-host-xyz.invalid", out, timeout=5)
    check(not good and "could not capture" in msg, "unreachable host -> clean failure")
    check(not Path(out).exists(), "no file written on capture failure")

    # ---- REAL capture against a public host (skips offline) --------------
    if _online():
        out2 = str(Path(tempfile.mkdtemp(prefix="rd_cert2_")) / "pypi.pem")
        good, msg = certs.capture_to_file("pypi.org", out2)
        check(good and Path(out2).exists(), "captured a live chain to a file")
        txt = Path(out2).read_text(encoding="utf-8")
        check(txt.count("BEGIN CERTIFICATE") >= 1, "written bundle has >=1 certificate")
        check("wrote" in msg and "chain" in msg, "capture message summarizes the chain")
        # /cert end-to-end via env (host from URL, out from REQUESTS_CA_BUNDLE)
        out3 = str(Path(tempfile.mkdtemp(prefix="rd_cert3_")) / "viaenv.pem")
        os.environ["ROBODOG_LLM_URL"] = "https://pypi.org/simple"
        os.environ["REQUESTS_CA_BUNDLE"] = out3
        try:
            good, msg = certs.handle("")
            check(good and Path(out3).exists(),
                  "/cert with ROBODOG_LLM_URL + REQUESTS_CA_BUNDLE captures end-to-end")
        finally:
            os.environ.pop("ROBODOG_LLM_URL", None)
            os.environ.pop("REQUESTS_CA_BUNDLE", None)
    else:
        print("  [SKIP] live-capture checks (offline)")

    print("\nCERTS:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
