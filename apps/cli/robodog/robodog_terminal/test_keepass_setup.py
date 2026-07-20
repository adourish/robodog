# file: robodog_terminal/test_keepass_setup.py
"""
`/keepass` vault bootstrap tests: init creates a usable keyfile-unlocked
vault + loader, entries round-trip, status never leaks secrets, and — the
one that matters — init REFUSES to touch an existing vault.

Everything runs in a temp dir via ROBODOG_KEEPASS_DIR, so a developer's real
~/.robodog vault is never opened, created, or overwritten by the suite.
Run: python robodog_terminal/test_keepass_setup.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from robodog_terminal import keepass_setup as ks  # noqa: E402

ok = True
SECRET = "sk-or-v1-TOTALLY-SECRET-VALUE"


def check(cond, msg):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    ok = ok and cond


def _clear_env():
    for var in ("ROBODOG_KEEPASS_DB", "ROBODOG_KEEPASS_KEYFILE",
                "ROBODOG_KEEPASS_DIR", "ROBODOG_LLM_KEY"):
        os.environ.pop(var, None)


def main() -> int:
    global ok
    try:
        import pykeepass  # noqa: F401
    except ImportError:
        print("  [SKIP] pykeepass not installed — /keepass tests skipped")
        print("\nKEEPASS: ALL PASS (skipped)")
        return 0

    saved = {k: os.environ.get(k) for k in
             ("ROBODOG_KEEPASS_DB", "ROBODOG_KEEPASS_KEYFILE",
              "ROBODOG_KEEPASS_DIR", "ROBODOG_LLM_KEY")}
    try:
        with tempfile.TemporaryDirectory() as td:
            _clear_env()
            os.environ["ROBODOG_KEEPASS_DIR"] = td
            d = Path(td)

            # ---- init -------------------------------------------------
            good, msg = ks.init(key=SECRET, title="OpenRouter")
            check(good, f"init creates a vault ({msg.splitlines()[0] if msg else ''})")
            db, keyfile, loader = ks.vault_paths()
            check(db.exists(), "init wrote the .kdbx")
            check(keyfile.exists() and len(keyfile.read_bytes()) == 32,
                  "init wrote a 32-byte random keyfile")
            check(loader.exists() and "class KeePassLoader" in loader.read_text(),
                  "init wrote keepass_loader.py")

            # ---- the loader robodog actually imports works ------------
            sys.path.insert(0, str(d))
            for mod in ("keepass_loader",):
                sys.modules.pop(mod, None)
            try:
                from keepass_loader import KeePassLoader  # type: ignore
                kp = KeePassLoader(db_path=str(db), keyfile=str(keyfile))
                kp.unlock()
                creds = kp.get_credentials("OpenRouter")
                check(creds and creds["password"] == SECRET,
                      "generated loader round-trips the key robodog will read")
                check(creds and creds["url"] == "https://openrouter.ai/api/v1",
                      "OpenRouter entry carries the expected URL")
            finally:
                sys.modules.pop("keepass_loader", None)
                if str(d) in sys.path:
                    sys.path.remove(str(d))

            # ---- init REFUSES to clobber an existing vault ------------
            before = keyfile.read_bytes()
            good2, msg2 = ks.init(key="different-key")
            check(not good2 and "already exists" in msg2,
                  "init refuses to overwrite an existing vault")
            check(keyfile.read_bytes() == before,
                  "refused init left the keyfile byte-identical (no lockout)")

            # ---- set_entry: update + add ------------------------------
            good3, _ = ks.set_entry("OpenRouter", "sk-or-v1-ROTATED")
            check(good3, "set_entry updates an existing entry")
            good4, _ = ks.set_entry("OpenAI", "sk-openai-NEW")
            check(good4, "set_entry adds a new provider entry")

            sys.path.insert(0, str(d))
            sys.modules.pop("keepass_loader", None)
            try:
                from keepass_loader import KeePassLoader  # type: ignore
                kp = KeePassLoader(db_path=str(db), keyfile=str(keyfile))
                kp.unlock()
                check(kp.get_credentials("OpenRouter")["password"] == "sk-or-v1-ROTATED",
                      "rotated key is what a later read returns")
                check(kp.get_credentials("OpenAI")["password"] == "sk-openai-NEW",
                      "second provider entry round-trips")
            finally:
                sys.modules.pop("keepass_loader", None)
                if str(d) in sys.path:
                    sys.path.remove(str(d))

            # ---- status never prints secrets --------------------------
            good5, report = ks.status()
            check(good5 and "unlocked" in report, "status unlocks and reports")
            check(SECRET not in report and "sk-or-v1-ROTATED" not in report
                  and "sk-openai-NEW" not in report,
                  "status NEVER leaks a secret value")
            check("OpenRouter" in report and "OpenAI" in report,
                  "status names the provider entries it found")

            # env var shadowing is called out, since it silently wins
            os.environ["ROBODOG_LLM_KEY"] = "env-wins"
            _, report2 = ks.status()
            check("overrides" in report2.lower() or "wins" in report2.lower(),
                  "status warns that ROBODOG_LLM_KEY overrides the vault")
            os.environ.pop("ROBODOG_LLM_KEY", None)

            # ---- handle() dispatch ------------------------------------
            good6, help_msg = ks.handle("bogus-subcommand")
            check(not good6 and "usage" in help_msg.lower(),
                  "handle() shows usage for an unknown subcommand")
            good7, set_msg = ks.handle("set OnlyTitle")
            check(not good7 and "usage" in set_msg.lower(),
                  "handle() rejects `set` with a missing key")
            good8, st = ks.handle("")
            check(good8 and "unlocked" in st, "bare /keepass reports status")

        # ---- set_entry with no vault present --------------------------
        with tempfile.TemporaryDirectory() as td2:
            _clear_env()
            os.environ["ROBODOG_KEEPASS_DIR"] = td2
            good9, msg9 = ks.set_entry("OpenRouter", "x")
            check(not good9 and "no vault" in msg9.lower(),
                  "set_entry without a vault points at /keepass init")
            good10, msg10 = ks.status()
            check(not good10 and "MISSING" in msg10,
                  "status reports MISSING files when nothing is set up")

        # ---- /keepass loader: write into an existing vault dir --------
        with tempfile.TemporaryDirectory() as td3:
            _clear_env()
            os.environ["ROBODOG_KEEPASS_DIR"] = td3
            (Path(td3) / "automation-keys.kdbx").write_bytes(b"fake")  # vault, no loader
            okL, msgL = ks.handle("loader")
            loader_path = Path(td3) / "keepass_loader.py"
            check(okL and loader_path.exists(),
                  "/keepass loader writes keepass_loader.py")
            src = loader_path.read_text(encoding="utf-8")
            check("class KeePassLoader" in src and "def unlock" in src
                  and "def get_credentials" in src,
                  "written loader has the interface robodog imports")
            okL2, msgL2 = ks.handle("loader")
            check(okL2 and "already present" in msgL2,
                  "/keepass loader is idempotent (never clobbers)")
            _, help_msg2 = ks.handle("bogus-subcommand")
            check("loader" in help_msg2, "usage lists the loader subcommand")
    finally:
        _clear_env()
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v

    print("\nKEEPASS:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
