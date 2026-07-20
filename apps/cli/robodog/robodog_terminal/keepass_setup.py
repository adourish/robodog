# file: robodog_terminal/keepass_setup.py
"""
KeePass vault bootstrap for `/keepass` — turns the manual README procedure
(create db + keyfile, write a loader module, add a provider entry) into one
command.

Safety rules that shape this module:
  * NEVER overwrite an existing .kdbx or .keyfile. The keyfile is the only
    way into a password-less vault — clobbering it destroys every credential
    inside, unrecoverably. init() refuses and tells the user what to do.
  * Never print, log, or return a secret value. Status output names entry
    titles only.
  * Keep the on-disk layout identical to what app._keepass_candidates()
    already probes (~/.robodog/automation-keys.kdbx + .keyfile +
    keepass_loader.py), so a fresh init needs no config.env at all.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

# Default provider entry titles -> the URL robodog expects for each.
PROVIDER_URLS = {
    "OpenRouter": "https://openrouter.ai/api/v1",
    "OpenAI": "https://api.openai.com/v1",
    "Gateway": "",
}

DB_NAME = "automation-keys.kdbx"
KEYFILE_NAME = "automation-keys.keyfile"

# The loader module robodog imports by name. Kept byte-identical to the
# README's interface so a hand-rolled loader and this one are interchangeable.
LOADER_SOURCE = '''# file: keepass_loader.py
"""Credential loader for robodog. Written by `/keepass init`."""
from pykeepass import PyKeePass


class KeePassLoader:
    def __init__(self, db_path, keyfile=None):
        self.db_path, self.keyfile, self.kp = db_path, keyfile, None

    def unlock(self, password=None):
        self.kp = PyKeePass(self.db_path, password=password,
                            keyfile=self.keyfile)

    def get_credentials(self, title):
        e = self.kp.find_entries(title=title, first=True)
        if e is None:
            return None
        return {"title": e.title, "username": e.username,
                "password": e.password, "url": e.url}
'''

_PIP_HINT = ("KeePass support needs the pykeepass package:\n"
             "    pip install pykeepass")


def robodog_dir() -> Path:
    """Where the vault lives: $ROBODOG_KEEPASS_DIR or ~/.robodog."""
    return Path(os.environ.get("ROBODOG_KEEPASS_DIR") or (Path.home() / ".robodog"))


def vault_paths(directory: Optional[Path] = None) -> Tuple[Path, Path, Path]:
    """(db, keyfile, loader) honoring ROBODOG_KEEPASS_DB/KEYFILE overrides."""
    d = Path(directory) if directory else robodog_dir()
    db = Path(os.environ.get("ROBODOG_KEEPASS_DB") or (d / DB_NAME))
    keyfile = Path(os.environ.get("ROBODOG_KEEPASS_KEYFILE")
                   or db.with_suffix(".keyfile"))
    return db, keyfile, d / "keepass_loader.py"


def _import_pykeepass():
    try:
        import pykeepass  # noqa: F401
        return pykeepass, None
    except ImportError:
        return None, _PIP_HINT


def init(key: Optional[str] = None, title: str = "OpenRouter",
         directory: Optional[Path] = None) -> Tuple[bool, str]:
    """
    Create the vault, keyfile, and loader module; optionally seed one entry.

    Refuses if the database already exists — use `/keepass set` to add or
    update entries in a vault that's already there.
    """
    pk, err = _import_pykeepass()
    if err:
        return False, err
    from pykeepass import create_database

    db, keyfile, loader = vault_paths(directory)

    # Guard first, write nothing on refusal — a partial init that replaced the
    # keyfile would lock the user out of their own database.
    if db.exists():
        return False, (
            f"vault already exists: {db}\n"
            f"  Refusing to overwrite it — that would destroy every credential\n"
            f"  inside (the keyfile is the only way in).\n"
            f"  Add or update a key instead:  /keepass set {title}")
    if keyfile.exists():
        return False, (
            f"keyfile already exists without a database: {keyfile}\n"
            f"  Move or delete it by hand if you're sure it's unused, then rerun.")

    db.parent.mkdir(parents=True, exist_ok=True)
    loader.parent.mkdir(parents=True, exist_ok=True)

    keyfile.write_bytes(os.urandom(32))     # random keyfile => no master password
    try:
        os.chmod(keyfile, 0o600)            # best effort; no-op semantics on Windows
    except OSError:
        pass

    try:
        kp = create_database(str(db), password=None, keyfile=str(keyfile))
        if key:
            kp.add_entry(kp.root_group, title, "robodog", key,
                         url=PROVIDER_URLS.get(title, ""))
        kp.save()
    except Exception as exc:
        # Roll back so a failed init doesn't leave a half-built vault behind.
        for p in (db, keyfile):
            try:
                p.unlink()
            except OSError:
                pass
        return False, f"failed to create vault: {type(exc).__name__}: {exc}"

    loader.write_text(LOADER_SOURCE, encoding="utf-8")

    # The backup warning gets its own line rather than trailing the keyfile
    # path: paths are long enough to wrap at 80 cols, which would split the
    # one message the user must not miss. ASCII-only for legacy cp1252
    # consoles, where an em dash renders as mojibake.
    msg = [f"created {db}",
           f"created {keyfile}",
           f"created {loader}",
           "",
           "!! BACK UP THE KEYFILE - it is the ONLY way into this vault.",
           "   There is no master password to fall back on."]
    if key:
        msg.append(f"added entry '{title}'")
    else:
        msg.append(f"no key stored yet — add one:  /keepass set {title}")
    if directory or os.environ.get("ROBODOG_KEEPASS_DB"):
        msg.append("non-default location: keep ROBODOG_KEEPASS_DB / "
                   "ROBODOG_KEEPASS_DIR set in ~/.robodog/config.env")
    return True, "\n".join(msg)


def set_entry(title: str, key: str,
              directory: Optional[Path] = None) -> Tuple[bool, str]:
    """Create or update one provider entry. The key goes in the password field."""
    pk, err = _import_pykeepass()
    if err:
        return False, err
    from pykeepass import PyKeePass

    if not key:
        return False, "no key given — usage: /keepass set <Title> <key>"

    db, keyfile, _ = vault_paths(directory)
    if not db.exists():
        return False, f"no vault at {db} — create one first:  /keepass init"

    try:
        kp = PyKeePass(str(db), password=None,
                       keyfile=str(keyfile) if keyfile.exists() else None)
    except Exception as exc:
        return False, f"could not unlock {db}: {type(exc).__name__}: {exc}"

    entry = kp.find_entries(title=title, first=True)
    if entry is None:
        kp.add_entry(kp.root_group, title, "robodog", key,
                     url=PROVIDER_URLS.get(title, ""))
        action = "added"
    else:
        entry.password = key
        action = "updated"
    kp.save()

    note = ""
    if os.environ.get("ROBODOG_LLM_KEY"):
        note = ("\n  ⚠ ROBODOG_LLM_KEY is set in your environment and WINS over "
                "KeePass.\n    Remove it from ~/.robodog/config.env for this "
                "entry to take effect.")
    return True, f"{action} entry '{title}' in {db.name}{note}"


def status(directory: Optional[Path] = None) -> Tuple[bool, str]:
    """Report what robodog would find. Never prints secret values."""
    db, keyfile, loader = vault_paths(directory)
    lines = [f"db      {db}      {'ok' if db.exists() else 'MISSING'}",
             f"keyfile {keyfile} {'ok' if keyfile.exists() else 'MISSING'}",
             f"loader  {loader}  {'ok' if loader.exists() else 'MISSING'}"]

    if not db.exists():
        lines.append("\nno vault yet — create one:  /keepass init")
        return False, "\n".join(lines)

    pk, err = _import_pykeepass()
    if err:
        lines.append("\n" + err)
        return False, "\n".join(lines)
    from pykeepass import PyKeePass

    try:
        kp = PyKeePass(str(db), password=None,
                       keyfile=str(keyfile) if keyfile.exists() else None)
    except Exception as exc:
        lines.append(f"\nunlock FAILED: {type(exc).__name__}: {exc}")
        return False, "\n".join(lines)

    titles: List[str] = sorted({e.title for e in kp.entries if e.title})
    known = [t for t in titles if t in PROVIDER_URLS]
    lines.append(f"\nunlocked · {len(titles)} entries")
    lines.append("provider entries robodog looks for: "
                 + (", ".join(known) if known else "NONE — "
                    "add one:  /keepass set OpenRouter <key>"))
    if os.environ.get("ROBODOG_LLM_KEY"):
        lines.append("⚠ ROBODOG_LLM_KEY is set and overrides KeePass.")
    return True, "\n".join(lines)


def handle(rest: str) -> Tuple[bool, str]:
    """
    Dispatch for the `/keepass` command.

      /keepass                       -> status
      /keepass init [key]            -> create vault (+ seed OpenRouter)
      /keepass set <Title> <key>     -> add/update an entry
    """
    parts = (rest or "").strip().split()
    if not parts or parts[0] == "status":
        return status()

    sub = parts[0].lower()
    if sub == "init":
        return init(key=parts[1] if len(parts) > 1 else None)
    if sub == "set":
        if len(parts) < 3:
            return False, ("usage: /keepass set <Title> <key>\n"
                           f"  titles robodog looks up: "
                           f"{', '.join(PROVIDER_URLS)}")
        return set_entry(parts[1], parts[2])
    return False, ("usage:\n"
                   "  /keepass                    show vault status\n"
                   "  /keepass init [key]         create vault + loader\n"
                   "  /keepass set <Title> <key>  add or update an entry")
