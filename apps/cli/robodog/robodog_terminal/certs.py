# file: robodog_terminal/certs.py
"""
Capture a server's TLS certificate chain and write it as a PEM bundle — for
endpoints behind a private/internal CA (SEMOSS/ELSA-style) where you can't
reach the normal trust store and don't have the official cert file yet.

This is trust-on-first-use: it writes whatever the server presents. Eyeball
the printed chain (issuer names should look like your org's internal CA)
before relying on it — the same caveat the browser "export the chain" flow has.

Chain capture, most complete first:
  1. openssl s_client -showcerts   (full chain + subjects; git ships openssl
     on Windows, standard elsewhere)
  2. ssl.get_unverified_chain()    (Python 3.13+, full chain)
  3. ssl.get_server_certificate()  (leaf only — last resort; may not satisfy
     verification if the endpoint needs intermediates)
"""
from __future__ import annotations

import os
import re
import shutil
import ssl
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

_PEM_RE = re.compile(
    r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)


def host_port_from_url(url: str, default_port: int = 443) -> Optional[Tuple[str, int]]:
    """Extract (host, port) from an http(s) URL, or None if unparseable."""
    try:
        u = urlparse(url if "://" in url else "https://" + url)
        if not u.hostname:
            return None
        return u.hostname, (u.port or default_port)
    except Exception:
        return None


def _openssl_exe() -> Optional[str]:
    """Find openssl on PATH, or the copy Git for Windows ships."""
    exe = shutil.which("openssl")
    if exe:
        return exe
    for cand in (r"C:\Program Files\Git\usr\bin\openssl.exe",
                 r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
        if Path(cand).is_file():
            return cand
    return None


def _via_openssl(host: str, port: int, timeout: int) -> List[str]:
    exe = _openssl_exe()
    if not exe:
        return []
    try:
        proc = subprocess.run(
            [exe, "s_client", "-showcerts", "-servername", host,
             "-connect", f"{host}:{port}"],
            input="", capture_output=True, text=True, timeout=timeout)
    except Exception:
        return []
    return _PEM_RE.findall(proc.stdout or "")


def _via_python(host: str, port: int, timeout: int) -> List[str]:
    ctx = ssl._create_unverified_context()
    try:
        with ctx.wrap_socket(_connect(host, port, timeout),
                             server_hostname=host) as ss:
            get_chain = getattr(ss, "get_unverified_chain", None)  # 3.13+
            if get_chain:
                der_list = get_chain() or []
                return [ssl.DER_cert_to_PEM_cert(c) for c in der_list]
    except Exception:
        pass
    # last resort: leaf only
    try:
        leaf = ssl.get_server_certificate((host, port))
        return [leaf] if leaf else []
    except Exception:
        return []


def _connect(host: str, port: int, timeout: int):
    import socket
    return socket.create_connection((host, port), timeout=timeout)


def capture_chain(host: str, port: int = 443, timeout: int = 12) -> List[str]:
    """Return the server's certificate chain as a list of PEM strings, most
    complete method first. Empty list if the host can't be reached."""
    chain = _via_openssl(host, port, timeout)
    if len(chain) >= 1:
        return chain
    return _via_python(host, port, timeout)


def _subjects(pems: List[str]) -> List[str]:
    """Best-effort issuer/subject summary via openssl; falls back to a count."""
    exe = _openssl_exe()
    out = []
    if exe:
        for i, pem in enumerate(pems):
            try:
                r = subprocess.run([exe, "x509", "-noout", "-subject", "-issuer"],
                                   input=pem, capture_output=True, text=True, timeout=10)
                line = " ".join(r.stdout.split())
                out.append(line or f"cert {i + 1}")
            except Exception:
                out.append(f"cert {i + 1}")
    else:
        out = [f"cert {i + 1} (install openssl to see subjects)"
               for i in range(len(pems))]
    return out


def capture_to_file(host: str, out_path: str, port: int = 443,
                    timeout: int = 12) -> Tuple[bool, str]:
    """Capture host's chain and write a PEM bundle to out_path. Returns
    (ok, human message). Never raises."""
    chain = capture_chain(host, port, timeout)
    if not chain:
        return False, (f"could not capture a certificate from {host}:{port} — "
                       "unreachable (VPN up?) or not a TLS endpoint")
    try:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(c.strip() + "\n" for c in chain), encoding="utf-8")
    except OSError as exc:
        return False, f"captured {len(chain)} cert(s) but could not write {out_path}: {exc}"
    lines = [f"wrote {len(chain)} certificate(s) to {out_path}",
             "chain (verify these look like your org's internal CA before trusting):"]
    lines += [f"  {i + 1}. {s}" for i, s in enumerate(_subjects(chain))]
    if len(chain) == 1:
        lines.append("⚠ only the leaf was captured — if TLS still fails with "
                     "CERTIFICATE_VERIFY_FAILED the endpoint needs its "
                     "intermediates (install openssl, or use the official cert).")
    lines.append("point REQUESTS_CA_BUNDLE at this file (config.env) and rerun /doctor.")
    return True, "\n".join(lines)


def handle(rest: str) -> Tuple[bool, str]:
    """`/cert` command. With no args, capture from ROBODOG_LLM_URL's host to
    REQUESTS_CA_BUNDLE. Args: /cert [host] [out_path]."""
    parts = (rest or "").strip().split()
    host = parts[0] if parts else None
    out = parts[1] if len(parts) > 1 else os.environ.get("REQUESTS_CA_BUNDLE")

    if not host:
        url = os.environ.get("ROBODOG_LLM_URL")
        hp = host_port_from_url(url) if url else None
        if not hp:
            return False, ("usage: /cert [host] [out-file]\n"
                           "  with no host, set ROBODOG_LLM_URL so /cert knows "
                           "which endpoint to capture from")
        host, port = hp
    else:
        hp = host_port_from_url(host)
        host, port = hp if hp else (host, 443)

    if not out:
        return False, ("no output path — set REQUESTS_CA_BUNDLE in config.env, "
                       "or run: /cert " + host + r" C:\path\to\ca.pem")
    return capture_to_file(host, out, port)
