# file: robodog_terminal/test_doctor.py
"""
Tests for robodog_terminal/doctor.py — the /doctor environment diagnostics.

Verifies: every check reports, no secret-looking strings in any detail,
known-good checks pass on this machine, bogus cwd fails without raising,
report summary counts match, and exception paths are exercised (unreachable
a gateway host, missing KeePass loader, crashing check, failing imports).

Run:  python robodog_terminal/test_doctor.py          (from robodogcli/robodog/)
   or: python -m robodog.robodog_terminal.test_doctor (from robodogcli/)
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

# Support both "python -m robodog.robodog_terminal.test_doctor" and direct execution.
try:
    from . import doctor
    from .doctor import CheckResult, format_report, run_doctor
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from robodog_terminal import doctor
    from robodog_terminal.doctor import CheckResult, format_report, run_doctor

EXPECTED_NAMES = [
    "version",
    "python", "rich", "prompt_toolkit", "requests", "tty", "encoding",
    "cwd-writable", "robodog-home", "keepass", "gateway-env", "gateway-endpoint",
    "openai-endpoint", "ca-bundle", "git", "powershell", "model-backend",
    "llm-config", "terminal-modules",
]

# A secret-looking string: a long unbroken alnum run (real keys are 25+ chars
# of [A-Za-z0-9]; versions "3.11.9", paths "C:\\Users\\sol90", and hostnames
# "a gateway host" all contain separators so they pass).
SECRET_RE = re.compile(r"[A-Za-z0-9]{25,}")

ok = True


def check(cond, msg):
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"  [{status}] {msg}")


def by_name(results):
    return {r.name: r for r in results}


def main() -> int:
    all_results = []

    # ================= scenario 1: normal run on this machine ============
    print("=== scenario 1: run_doctor(cwd) on this machine ===")
    results = run_doctor(os.getcwd())
    all_results.extend(results)
    names = [r.name for r in results]
    check(len(results) == len(EXPECTED_NAMES),
          f"one result per check ({len(results)}/{len(EXPECTED_NAMES)})")
    missing = [n for n in EXPECTED_NAMES if n not in names]
    check(not missing, f"all expected check names present (missing: {missing or 'none'})")
    r = by_name(results)
    check(r["python"].ok is True, f"python check passes ({r['python'].detail})")
    check(r["rich"].ok is True, "rich importable")
    check(r["requests"].ok is True, "requests importable")
    check(r["prompt_toolkit"].ok is True, "prompt_toolkit importable")
    check(r["terminal-modules"].ok is True,
          f"terminal package modules import ({r['terminal-modules'].detail})")
    check(r["cwd-writable"].ok is True, "cwd is writable")
    check(r["robodog-home"].ok is True, "~/.robodog is writable")
    check(r["gateway-env"].ok is None, "gateway-env is informational (ok=None)")
    check(r["tty"].ok in (True, None), "tty check is pass or warn, never fail")
    check(r["encoding"].ok in (True, None), "encoding check is pass or warn")
    check(all(isinstance(x, CheckResult) and x.detail for x in results),
          "every result is a CheckResult with a non-empty detail")

    # ================= scenario 2: report formatting =====================
    print("\n=== scenario 2: format_report ===")
    report = format_report(results)
    n_ok = sum(1 for x in results if x.ok is True)
    n_warn = sum(1 for x in results if x.ok is None)
    n_fail = sum(1 for x in results if x.ok is False)
    check(f"{n_ok} ok, {n_warn} warnings, {n_fail} failed" in report,
          f"summary line matches counts ({n_ok} ok, {n_warn} warnings, {n_fail} failed)")
    check(all(f"] {x.name}" in report for x in results),
          "every check name appears in the report")
    synth = [CheckResult("aaa", True, "fine"),
             CheckResult("bbb", False, "broken"),
             CheckResult("ccc", None, "meh")]
    synth_report = format_report(synth)
    check("  [OK] aaa" in synth_report, "ok=True renders as [OK]")
    check("  [!!] bbb" in synth_report, "ok=False renders as [!!]")
    check("  [--] ccc" in synth_report, "ok=None renders as [--]")
    check("1 ok, 1 warnings, 1 failed" in synth_report, "synthetic summary counts")

    # ================= scenario 3: bogus cwd fails, never raises =========
    print("\n=== scenario 3: bogus cwd ===")
    try:
        bogus = run_doctor("Z:\\nope")
        all_results.extend(bogus)
        b = by_name(bogus)
        check(b["cwd-writable"].ok is False,
              f"cwd-writable fails for Z:\\nope ({b['cwd-writable'].detail})")
        check(len(bogus) == len(EXPECTED_NAMES), "all checks still ran")
    except Exception as exc:
        check(False, f"run_doctor raised on bogus cwd: {type(exc).__name__}")

    # ============ scenario 4: garbage cwd + forced failure paths =========
    # One combined run: empty cwd, unreachable a gateway host, missing KeePass
    # loader dir, and a check function that crashes outright.
    print("\n=== scenario 4: empty cwd, unreachable the gateway, crashed check ===")
    saved_endpoint = os.environ.get("GATEWAY_ENDPOINT")
    saved_kp_dir = doctor.KEEPASS_LOADER_DIR
    saved_py_check = doctor._check_python

    def _boom():
        raise RuntimeError("synthetic check crash")

    try:
        os.environ["GATEWAY_ENDPOINT"] = "https://localhost-nonexistent-host-xyz.invalid/"
        doctor.KEEPASS_LOADER_DIR = "Z:\\no-such-keys-dir"
        doctor._check_python = _boom
        garbage = run_doctor("")
        all_results.extend(garbage)
        g = by_name(garbage)
        check(len(garbage) == len(EXPECTED_NAMES), "run_doctor('') completed all checks")
        check(g["gateway-endpoint"].ok is False, "unreachable a gateway host -> ok=False")
        check("unreachable" in g["gateway-endpoint"].detail
              and "expected off gateway network" in g["gateway-endpoint"].detail,
              f"the gateway failure notes off-network is expected ({g['gateway-endpoint'].detail})")
        check(g["keepass"].ok is None
              and "loader not found" in g["keepass"].detail
              and "/keepass loader" in g["keepass"].detail,
              "missing KeePass loader -> warn pointing at /keepass loader")
        check(g["python"].ok is False and "check crashed" in g["python"].detail
              and "RuntimeError" in g["python"].detail,
              "a crashing check is caught and reported, not raised")
    except Exception as exc:
        check(False, f"run_doctor raised in scenario 4: {type(exc).__name__}: {exc}")
    finally:
        if saved_endpoint is None:
            os.environ.pop("GATEWAY_ENDPOINT", None)
        else:
            os.environ["GATEWAY_ENDPOINT"] = saved_endpoint
        doctor.KEEPASS_LOADER_DIR = saved_kp_dir
        doctor._check_python = saved_py_check

    # ================= scenario 5: no secrets in any detail ==============
    print("\n=== scenario 5: no secret-looking strings in details ===")
    leaks = [(x.name, x.detail) for x in all_results
             if "sk-" in x.detail or SECRET_RE.search(x.detail)]
    check(not leaks, f"no detail contains 'sk-' or a 25+ char token (leaks: {leaks or 'none'})")
    fake_key = "sk" + "A1b2C3d4" * 5  # 42-char alnum run
    masked = doctor._sanitize(f"key {fake_key} leaked")
    check("<redacted>" in masked and not SECRET_RE.search(masked),
          "_sanitize masks token-like runs")
    check(doctor._sanitize("python 3.11.9 at C:/Users/sol90") ==
          "python 3.11.9 at C:/Users/sol90",
          "_sanitize leaves versions and paths alone")

    # ================= scenario 6: individual check paths ================
    print("\n=== scenario 6: individual check functions ===")
    imp = doctor._check_importable("definitely_not_a_module_xyz_123")
    check(imp.ok is False and "import failed" in imp.detail,
          "importable check fails cleanly for a missing module")

    tcp = doctor._check_tcp("t", "no-such-host-abc.invalid", "unreachable note")
    check(tcp.ok is False and "unreachable note" in tcp.detail,
          "tcp check fails cleanly for an unresolvable host")

    tmpdir = tempfile.mkdtemp(prefix="robodog_doctor_")
    wr = doctor._check_cwd_writable(tmpdir)
    check(wr.ok is True, "cwd-writable passes for a real temp dir")

    which = doctor._check_which("bogus-tool", "no-such-exe-xyz")
    check(which.ok is False and "not found on PATH" in which.detail,
          "which check fails for a missing executable")

    os.environ["GATEWAY_ENDPOINT"] = "not a url"
    try:
        parse = doctor._check_gateway_endpoint()
        check(parse.ok is False and "could not parse" in parse.detail,
              "gateway-endpoint fails cleanly on an unparseable URL")
    finally:
        if saved_endpoint is None:
            os.environ.pop("GATEWAY_ENDPOINT", None)
        else:
            os.environ["GATEWAY_ENDPOINT"] = saved_endpoint

    env = doctor._check_gateway_env()
    check(env.ok is None and "set:" in env.detail and "unset:" in env.detail,
          "gateway-env reports set/unset names only")
    for var in doctor.GATEWAY_ENV_VARS:
        check(os.environ.get(var, "") not in env.detail or not os.environ.get(var),
              f"gateway-env never leaks the value of {var}")

    # CA bundle: set-and-present passes, set-and-missing fails, unset is info
    _saved_ca = os.environ.pop("REQUESTS_CA_BUNDLE", None)
    _saved_ssl = os.environ.pop("SSL_CERT_FILE", None)
    try:
        cab = doctor._check_ca_bundle()
        check(cab.ok is None and "no custom CA bundle" in cab.detail,
              "ca-bundle: unset -> informational")
        real_pem = Path(tempfile.mkdtemp(prefix="rd_ca_")) / "ca.pem"
        real_pem.write_text("-----BEGIN CERTIFICATE-----", encoding="utf-8")
        os.environ["REQUESTS_CA_BUNDLE"] = str(real_pem)
        cab = doctor._check_ca_bundle()
        check(cab.ok is True and "present" in cab.detail,
              "ca-bundle: existing file -> pass")
        os.environ["REQUESTS_CA_BUNDLE"] = r"C:\nope\missing-ca.pem"
        cab = doctor._check_ca_bundle()
        check(cab.ok is False and "missing file" in cab.detail
              and "TLS requests will fail" in cab.detail,
              "ca-bundle: missing file -> fail with the actionable reason")
    finally:
        os.environ.pop("REQUESTS_CA_BUNDLE", None)
        os.environ.pop("SSL_CERT_FILE", None)
        if _saved_ca is not None:
            os.environ["REQUESTS_CA_BUNDLE"] = _saved_ca
        if _saved_ssl is not None:
            os.environ["SSL_CERT_FILE"] = _saved_ssl

    # version staleness: tuple compare + disable flag (no network needed)
    check(doctor._ver_tuple("0.3.5") == (0, 3, 5), "_ver_tuple parses dotted version")
    check(doctor._ver_tuple("0.3.10") > doctor._ver_tuple("0.3.9"),
          "_ver_tuple compares numerically (0.3.10 > 0.3.9)")
    check(doctor._ver_tuple("1.0") < doctor._ver_tuple("1.0.1"),
          "_ver_tuple: shorter version sorts below its patch")
    _saved_vc = os.environ.get("ROBODOG_NO_VERSION_CHECK")
    os.environ["ROBODOG_NO_VERSION_CHECK"] = "1"
    try:
        vr = doctor._check_version()
        check(vr.name == "version" and vr.ok is True and "disabled" in vr.detail,
              "version check honors ROBODOG_NO_VERSION_CHECK (no network)")
    finally:
        if _saved_vc is None:
            os.environ.pop("ROBODOG_NO_VERSION_CHECK", None)
        else:
            os.environ["ROBODOG_NO_VERSION_CHECK"] = _saved_vc

    # llm-config surfaces the concurrency cap + timeout
    _sc = os.environ.pop("ROBODOG_LLM_MAX_CONCURRENCY", None)
    _st = os.environ.pop("ROBODOG_LLM_TIMEOUT", None)
    try:
        lc0 = doctor._check_llm_config()
        check(lc0.ok is None and "unlimited" in lc0.detail
              and "ROBODOG_LLM_MAX_CONCURRENCY" in lc0.detail,
              "llm-config: uncapped -> warn recommending the cap")
        os.environ["ROBODOG_LLM_MAX_CONCURRENCY"] = "2"
        os.environ["ROBODOG_LLM_TIMEOUT"] = "180"
        lc1 = doctor._check_llm_config()
        check(lc1.ok is True and "max concurrency: 2" in lc1.detail
              and "timeout: 180s" in lc1.detail,
              "llm-config: cap + timeout reported when set")
    finally:
        os.environ.pop("ROBODOG_LLM_MAX_CONCURRENCY", None)
        os.environ.pop("ROBODOG_LLM_TIMEOUT", None)
        if _sc is not None:
            os.environ["ROBODOG_LLM_MAX_CONCURRENCY"] = _sc
        if _st is not None:
            os.environ["ROBODOG_LLM_TIMEOUT"] = _st

    tty = doctor._check_tty()
    check(tty.name == "tty" and tty.ok in (True, None), "tty check returns pass/warn")
    enc = doctor._check_encoding()
    check(enc.name == "encoding" and "encoding" in enc.detail, "encoding check reports codec")

    # model/backend coherence (the opaque-HTTP-400-before-it-happens check)
    mb = doctor._check_model_backend("openai", "anthropic/claude-sonnet-4.6")
    check(mb.ok is False and "openrouter" in mb.detail.lower(),
          "openai backend + provider-prefixed model -> fail with openrouter hint")
    mb = doctor._check_model_backend("openrouter", "gpt-4o")
    check(mb.ok is False and "provider prefix" in mb.detail,
          "openrouter backend + bare model -> fail with prefix hint")
    mb = doctor._check_model_backend("openrouter", "anthropic/claude-sonnet-4.6")
    check(mb.ok is True, "matched openrouter pairing passes")
    mb = doctor._check_model_backend("openai", "gpt-4o-mini")
    check(mb.ok is True, "matched openai pairing passes")
    mb = doctor._check_model_backend("", "")
    check(mb.ok is None, "no config -> informational, not a failure")
    mb = doctor._check_model_backend("auto", "anthropic/claude-sonnet-4.6")
    check(mb.ok is True, "auto backend never flags a mismatch")

    # KeePass unlock-failure path via a fake loader that raises.
    fake_dir = Path(tempfile.mkdtemp(prefix="robodog_fakekp_"))
    (fake_dir / "keepass_loader.py").write_text(
        "class KeePassLoader:\n"
        "    def __init__(self, **kw):\n"
        "        pass\n"
        "    def unlock(self):\n"
        "        raise RuntimeError('bad keyfile')\n",
        encoding="utf-8")
    saved_mod = sys.modules.pop("keepass_loader", None)
    doctor.KEEPASS_LOADER_DIR = str(fake_dir)
    try:
        kp = doctor._check_keepass()
        check(kp.ok is False and "unlock failed" in kp.detail
              and "RuntimeError" in kp.detail,
              "keepass unlock failure -> ok=False, error type only (no values)")
    finally:
        doctor.KEEPASS_LOADER_DIR = saved_kp_dir
        sys.modules.pop("keepass_loader", None)
        if saved_mod is not None:
            sys.modules["keepass_loader"] = saved_mod
        if str(fake_dir) in sys.path:
            sys.path.remove(str(fake_dir))

    # ============ scenario 7: remaining branches (stubs/patches) =========
    print("\n=== scenario 7: remaining branches ===")
    import types

    saved_sys = doctor.sys
    try:
        doctor.sys = types.SimpleNamespace(version_info=(3, 8, 0))
        old_py = doctor._check_python()
        check(old_py.ok is False and "need >= 3.9" in old_py.detail,
              "python < 3.9 -> ok=False with version requirement")

        doctor.sys = types.SimpleNamespace(
            stdin=types.SimpleNamespace(isatty=lambda: True))
        tty_yes = doctor._check_tty()
        check(tty_yes.ok is True and "is a TTY" in tty_yes.detail,
              "real TTY -> ok=True")

        def _isatty_boom():
            raise ValueError("closed stdin")
        doctor.sys = types.SimpleNamespace(
            stdin=types.SimpleNamespace(isatty=_isatty_boom))
        tty_err = doctor._check_tty()
        check(tty_err.ok is None, "isatty raising -> treated as not-a-TTY warn")
    finally:
        doctor.sys = saved_sys

    saved_os = doctor.os

    def _getpid_boom():
        raise OSError("no pid for you")

    try:
        doctor.os = types.SimpleNamespace(getpid=_getpid_boom)
        wr_err = doctor._check_cwd_writable(tmpdir)
        check(wr_err.ok is False and "cannot write" in wr_err.detail
              and "OSError" in wr_err.detail,
              "cwd-writable write error -> ok=False with error type")
        home_err = doctor._check_robodog_home()
        check(home_err.ok is False and "cannot write" in home_err.detail,
              "robodog-home write error -> ok=False with error type")
    finally:
        doctor.os = saved_os

    # KeePass: unlock succeeds but every get_credentials raises -> all missing.
    fake_dir2 = Path(tempfile.mkdtemp(prefix="robodog_fakekp2_"))
    (fake_dir2 / "keepass_loader.py").write_text(
        "class KeePassLoader:\n"
        "    def __init__(self, **kw):\n"
        "        pass\n"
        "    def unlock(self):\n"
        "        pass\n"
        "    def get_credentials(self, title=None):\n"
        "        raise KeyError(title)\n",
        encoding="utf-8")
    saved_mod2 = sys.modules.pop("keepass_loader", None)
    doctor.KEEPASS_LOADER_DIR = str(fake_dir2)
    _saved_llm_key = os.environ.pop("ROBODOG_LLM_KEY", None)
    _saved_llm_entry = os.environ.pop("ROBODOG_KEEPASS_LLM_ENTRY", None)
    try:
        kp2 = doctor._check_keepass("openai")
        # all entries missing + no env key -> actionable warning (ok=None), and
        # the report leads with the entry the backend actually needs.
        check(kp2.ok is None and "entries present: none" in kp2.detail
              and "LLM entry 'OpenAI': MISSING" in kp2.detail
              and "fall back to echo" in kp2.detail,
              "missing LLM entry (no env key) -> warn, names the entry + fix")
    finally:
        if _saved_llm_key is not None:
            os.environ["ROBODOG_LLM_KEY"] = _saved_llm_key
        if _saved_llm_entry is not None:
            os.environ["ROBODOG_KEEPASS_LLM_ENTRY"] = _saved_llm_entry
        doctor.KEEPASS_LOADER_DIR = saved_kp_dir
        sys.modules.pop("keepass_loader", None)
        if saved_mod2 is not None:
            sys.modules["keepass_loader"] = saved_mod2
        if str(fake_dir2) in sys.path:
            sys.path.remove(str(fake_dir2))

    # KeePass: ROBODOG_KEEPASS_LLM_ENTRY is probed and reported present.
    fake_dir3 = Path(tempfile.mkdtemp(prefix="robodog_fakekp3_"))
    (fake_dir3 / "keepass_loader.py").write_text(
        "class KeePassLoader:\n"
        "    def __init__(self, **kw):\n"
        "        pass\n"
        "    def unlock(self):\n"
        "        pass\n"
        "    def get_credentials(self, title=None):\n"
        "        return {'password': 'x'} if title == 'SEMOSS-Elsa-Dev' else None\n",
        encoding="utf-8")
    saved_mod3 = sys.modules.pop("keepass_loader", None)
    doctor.KEEPASS_LOADER_DIR = str(fake_dir3)
    _sk = os.environ.pop("ROBODOG_LLM_KEY", None)
    os.environ["ROBODOG_KEEPASS_LLM_ENTRY"] = "SEMOSS-Elsa-Dev"
    try:
        kp3 = doctor._check_keepass("openai")
        check(kp3.ok is True and "LLM entry 'SEMOSS-Elsa-Dev': present" in kp3.detail,
              "configured ROBODOG_KEEPASS_LLM_ENTRY is probed and reported present")
    finally:
        os.environ.pop("ROBODOG_KEEPASS_LLM_ENTRY", None)
        if _sk is not None:
            os.environ["ROBODOG_LLM_KEY"] = _sk
        doctor.KEEPASS_LOADER_DIR = saved_kp_dir
        sys.modules.pop("keepass_loader", None)
        if saved_mod3 is not None:
            sys.modules["keepass_loader"] = saved_mod3
        if str(fake_dir3) in sys.path:
            sys.path.remove(str(fake_dir3))

    os.environ["GATEWAY_ENDPOINT"] = "http://[bad-ipv6-url"
    try:
        parse2 = doctor._check_gateway_endpoint()
        check(parse2.ok is False and "could not parse" in parse2.detail,
              "urlparse raising -> ok=False could-not-parse")
    finally:
        if saved_endpoint is None:
            os.environ.pop("GATEWAY_ENDPOINT", None)
        else:
            os.environ["GATEWAY_ENDPOINT"] = saved_endpoint

    saved_mods = doctor.TERMINAL_MODULES
    try:
        doctor.TERMINAL_MODULES = ("no_such_terminal_module_xyz",)
        mod_fail = doctor._check_terminal_modules()
        check(mod_fail.ok is False
              and "robodog_terminal.no_such_terminal_module_xyz failed" in mod_fail.detail,
              "module import failure -> ok=False naming the first failed module")
    finally:
        doctor.TERMINAL_MODULES = saved_mods

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
