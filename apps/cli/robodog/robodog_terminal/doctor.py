# file: robodog_terminal/doctor.py
"""
/doctor — environment diagnostics for Robodog Terminal (like `claude doctor`).

Runs a battery of small, independent checks (python version, deps, TTY,
encoding, writable dirs, KeePass loader, the gateway env/network, git/powershell,
package imports) and renders a compact report. Built for debugging
deployment on a self-hosted gateway, where network and key storage differ from home.

Every check is exception-proof: run_doctor() NEVER raises, and no detail
line ever contains a secret value (long token-like runs are redacted).

Run:  python -m robodog.robodog_terminal.doctor       (from robodogcli/)
   or: python robodog_terminal/doctor.py              (from robodogcli/robodog/)
"""
from __future__ import annotations

import contextlib
import importlib
import logging
import os
import platform
import re
import shutil
import socket
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

GATEWAY_ENV_VARS = ("GATEWAY_ENDPOINT", "GATEWAY_ENGINE", "GATEWAY_ACCESS_KEY", "GATEWAY_SECRET_KEY")

# KeePass automation DB (home setup; a self-hosted gateway may use C:\keys instead).
KEEPASS_LOADER_DIR = os.environ.get("ROBODOG_KEEPASS_DIR", str(Path.home() / ".robodog"))
KEEPASS_ENTRIES = ("OpenAI", "OpenRouter", "Gateway", "SearchAPI-RapidAPI")

# Modules of the terminal package that must import cleanly.
TERMINAL_MODULES = ("loop", "tools", "llm_client", "toolcall", "agents",
                    "background", "checkpoint", "ui")

# Anything that looks like a key/token (long unbroken alnum run) gets masked.
_SECRET_RUN = re.compile(r"[A-Za-z0-9]{25,}")


@dataclass
class CheckResult:
    name: str
    ok: Optional[bool]      # True=pass, False=fail, None=warn/informational
    detail: str             # one line, NEVER contains a secret value


def _sanitize(detail: str) -> str:
    """Mask any token-like run so a secret can never leak into a report."""
    return _SECRET_RUN.sub("<redacted>", detail)


# ---------------------------------------------------------------- checks ----

def _check_python() -> CheckResult:
    ver = platform.python_version()
    if sys.version_info >= (3, 9):
        return CheckResult("python", True, ver)
    return CheckResult("python", False, f"{ver} (need >= 3.9)")


def _check_importable(module: str) -> CheckResult:
    try:
        mod = importlib.import_module(module)
    except Exception as exc:
        return CheckResult(module, False, f"import failed: {type(exc).__name__}")
    ver = getattr(mod, "__version__", "") or ""
    return CheckResult(module, True, ("importable " + ver).strip())


def _check_tty() -> CheckResult:
    try:
        is_tty = bool(sys.stdin.isatty())
    except Exception:
        is_tty = False
    if is_tty:
        return CheckResult("tty", True, "stdin is a TTY")
    return CheckResult("tty", None, "stdin is not a TTY (fallback UI will be used)")


def _check_encoding() -> CheckResult:
    enc = getattr(sys.stdout, "encoding", None) or "unknown"
    if enc.lower().replace("-", "").replace("_", "") == "utf8":
        return CheckResult("encoding", True, f"stdout encoding {enc}")
    return CheckResult("encoding", None,
                       f"stdout encoding {enc} (not utf-8; box glyphs may break — "
                       "try PYTHONIOENCODING=utf-8)")


def _check_cwd_writable(cwd: str) -> CheckResult:
    target = Path(cwd) if cwd else Path.cwd()
    try:
        if not target.is_dir():
            return CheckResult("cwd-writable", False, f"not a directory: {target}")
        probe = target / f".robodog-doctor-{os.getpid()}.tmp"
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
        return CheckResult("cwd-writable", True, f"writable: {target}")
    except Exception as exc:
        return CheckResult("cwd-writable", False,
                           f"cannot write in {target} ({type(exc).__name__})")


def _check_robodog_home() -> CheckResult:
    try:
        home = Path.home() / ".robodog"
        home.mkdir(parents=True, exist_ok=True)
        probe = home / f".doctor-{os.getpid()}.tmp"
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
        return CheckResult("robodog-home", True, f"writable: {home}")
    except Exception as exc:
        return CheckResult("robodog-home", False,
                           f"cannot write ~/.robodog ({type(exc).__name__})")


def _llm_entry_title(backend: str) -> str:
    """The vault entry title the openai/openrouter backend will actually read:
    ROBODOG_KEEPASS_LLM_ENTRY override, else the backend's default title."""
    override = os.environ.get("ROBODOG_KEEPASS_LLM_ENTRY")
    if override:
        return override
    return "OpenAI" if (backend or "").lower() == "openai" else "OpenRouter"


def _check_keepass(backend: str = "") -> CheckResult:
    """Report loader presence and WHICH entries exist — names only, never values.
    Also probes the entry the current backend will REALLY use (honoring
    ROBODOG_KEEPASS_LLM_ENTRY), so a misconfigured title shows up here instead
    of silently falling back to the echo backend at launch."""
    loader_dir = Path(KEEPASS_LOADER_DIR)
    if not loader_dir.is_dir() or not (loader_dir / "keepass_loader.py").exists():
        return CheckResult("keepass", None,
                           f"loader not found at {KEEPASS_LOADER_DIR} — "
                           "run /keepass loader to create it (won't touch the vault)")
    # Honor explicit DB/keyfile overrides; else default to files beside the loader.
    db = os.environ.get("ROBODOG_KEEPASS_DB") or str(loader_dir / "automation-keys.kdbx")
    keyfile = (os.environ.get("ROBODOG_KEEPASS_KEYFILE")
               or str(Path(db).with_suffix(".keyfile")))
    llm_entry = _llm_entry_title(backend)
    # Probe the defaults plus the entry the LLM backend will read.
    titles = list(KEEPASS_ENTRIES)
    if llm_entry not in titles:
        titles.append(llm_entry)
    try:
        sys.path.insert(0, str(loader_dir))
        from keepass_loader import KeePassLoader  # type: ignore
        # Loader chatter goes to stderr so stdout/report stays clean.
        with contextlib.redirect_stdout(sys.stderr):
            kp = KeePassLoader(db_path=db, keyfile=keyfile)
            kp.unlock()
            present: List[str] = []
            missing: List[str] = []
            for title in titles:
                try:
                    creds = kp.get_credentials(title=title)
                except Exception:
                    creds = None
                (present if creds else missing).append(title)
        # Lead with the entry the current backend actually depends on, since
        # that's the one that determines whether a live key is found.
        llm_ok = llm_entry in present
        env_key = bool(os.environ.get("ROBODOG_LLM_KEY"))
        head = (f"LLM entry '{llm_entry}': {'present' if llm_ok else 'MISSING'}"
                + ("" if llm_ok or env_key
                   else " — /backend openai will fall back to echo; add it with "
                        f"/keepass set {llm_entry} <key>, or set ROBODOG_KEEPASS_LLM_ENTRY"))
        detail = (f"unlocked; {head}; entries present: "
                  + (", ".join(p for p in present if p != llm_entry) or "none"))
        # A missing LLM entry with no env key is a real, actionable problem.
        ok = True if (llm_ok or env_key) else None
        return CheckResult("keepass", ok, detail)
    except Exception as exc:
        logger.debug("keepass check failed", exc_info=True)
        return CheckResult("keepass", False, f"unlock failed: {type(exc).__name__}")


def _check_gateway_env() -> CheckResult:
    """Informational: WHICH GATEWAY_* vars are set — never their values."""
    is_set = [v for v in GATEWAY_ENV_VARS if os.environ.get(v)]
    unset = [v for v in GATEWAY_ENV_VARS if not os.environ.get(v)]
    detail = ("set: " + (", ".join(is_set) or "none")
              + "; unset: " + (", ".join(unset) or "none"))
    return CheckResult("gateway-env", None, detail)


def _check_tcp(name: str, host: str, fail_note: str) -> CheckResult:
    try:
        with socket.create_connection((host, 443), timeout=3):
            pass
        return CheckResult(name, True, f"{host}:443 reachable")
    except Exception:
        return CheckResult(name, False, f"{host}:443 {fail_note}")


def _check_gateway_endpoint() -> CheckResult:
    url = os.environ.get("GATEWAY_ENDPOINT")
    if not url:
        return CheckResult("gateway-endpoint", None,
                           "GATEWAY_ENDPOINT not set (gateway backend unused)")
    try:
        host = urllib.parse.urlparse(url).hostname
    except Exception:
        host = None
    if not host:
        return CheckResult("gateway-endpoint", False,
                           "could not parse host from GATEWAY_ENDPOINT")
    return _check_tcp("gateway-endpoint", host,
                      "unreachable (expected off gateway network)")


def _check_openai_endpoint() -> CheckResult:
    return _check_tcp("openai-endpoint", "api.openai.com",
                      "unreachable (no internet, or blocked — expected on gateway network)")


def _check_which(name: str, exe: str) -> CheckResult:
    path = shutil.which(exe)
    if path:
        return CheckResult(name, True, f"found: {path}")
    return CheckResult(name, False, f"{exe} not found on PATH")


def _check_model_backend(backend: str, model: str) -> CheckResult:
    """
    Catch the backend/model pairings that fail at request time with an opaque
    HTTP 400 — before the user ever sends a prompt.
    """
    if not model or not backend:
        return CheckResult("model-backend", None, "no model/backend configured")
    b = backend.lower()
    if b == "openai" and "/" in model:
        return CheckResult(
            "model-backend", False,
            f"'{model}' is an OpenRouter-style id (provider/model) but the "
            "backend is OpenAI's API directly — use --backend openrouter")
    if b == "openrouter" and "/" not in model:
        return CheckResult(
            "model-backend", False,
            f"OpenRouter ids need a provider prefix — try 'openai/{model}' "
            f"or 'anthropic/{model}'")
    return CheckResult("model-backend", True, f"{model} @ {backend}")


def _check_terminal_modules() -> CheckResult:
    """All terminal package modules must import; report the FIRST failure."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    for name in TERMINAL_MODULES:
        try:
            importlib.import_module(f"robodog_terminal.{name}")
        except Exception as exc:
            logger.debug("module %s failed to import", name, exc_info=True)
            return CheckResult("terminal-modules", False,
                               f"robodog_terminal.{name} failed: {type(exc).__name__}")
    n = len(TERMINAL_MODULES)
    return CheckResult("terminal-modules", True, f"{n}/{n} modules import cleanly")


# ---------------------------------------------------------------- driver ----

def run_doctor(cwd: str, backend: str = "", model: str = "") -> List[CheckResult]:
    """Run every diagnostic. Never raises; every check yields one CheckResult.
    backend/model are optional (the /doctor command passes the live config so
    misconfigured pairings are flagged before a request ever fails)."""
    checks: List[Tuple[str, Callable[[], CheckResult]]] = [
        ("python", _check_python),
        ("rich", lambda: _check_importable("rich")),
        ("prompt_toolkit", lambda: _check_importable("prompt_toolkit")),
        ("requests", lambda: _check_importable("requests")),
        ("tty", lambda: _check_tty()),
        ("encoding", lambda: _check_encoding()),
        ("cwd-writable", lambda: _check_cwd_writable(cwd)),
        ("robodog-home", lambda: _check_robodog_home()),
        ("keepass", lambda: _check_keepass(backend)),
        ("gateway-env", lambda: _check_gateway_env()),
        ("gateway-endpoint", lambda: _check_gateway_endpoint()),
        ("openai-endpoint", lambda: _check_openai_endpoint()),
        ("git", lambda: _check_which("git", "git")),
        ("powershell", lambda: _check_which("powershell", "powershell")),
        ("model-backend", lambda: _check_model_backend(backend, model)),
        ("terminal-modules", lambda: _check_terminal_modules()),
    ]
    results: List[CheckResult] = []
    for name, fn in checks:
        try:
            res = fn()
        except Exception as exc:  # belt and braces — a check must never crash /doctor
            logger.debug("check %s crashed", name, exc_info=True)
            res = CheckResult(name, False, f"check crashed: {type(exc).__name__}")
        res.detail = _sanitize(res.detail)
        results.append(res)
    return results


def format_report(results: List[CheckResult]) -> str:
    """Lines like '  [OK] python 3.11.x', '  [!!] ...', '  [--] ...' plus a
    summary line 'N ok, N warnings, N failed'."""
    lines: List[str] = []
    n_ok = n_warn = n_fail = 0
    for r in results:
        if r.ok is True:
            mark, n_ok = "OK", n_ok + 1
        elif r.ok is False:
            mark, n_fail = "!!", n_fail + 1
        else:
            mark, n_warn = "--", n_warn + 1
        lines.append(f"  [{mark}] {r.name}: {r.detail}")
    lines.append(f"{n_ok} ok, {n_warn} warnings, {n_fail} failed")
    return "\n".join(lines)


if __name__ == "__main__":
    _results = run_doctor(os.getcwd())
    print(format_report(_results))
    raise SystemExit(1 if any(r.ok is False for r in _results) else 0)
