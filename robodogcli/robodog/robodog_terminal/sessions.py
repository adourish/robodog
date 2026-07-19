# file: robodog_terminal/sessions.py
"""
Conversation persistence — JSONL-per-project sessions, mirroring Claude Code.

Each project gets a directory under <base_dir> named by a filesystem-safe slug
of the project path (non-alphanumerics replaced with '-', like Claude Code's
~/.claude/projects layout). Each session is a single append-only JSONL file:

  {"type": "meta", "id": ..., "name": ..., "created": ..., "project": ...}
  {"type": "turn", "role": ..., "content": ..., "tool_name": ..., "ts": ...}
  {"type": "meta_update", <arbitrary keys>, "ts": ...}

Appends are cheap (open-append-close) and never raise — persistence must not
be able to take down the agent loop. Readers are tolerant of corrupt lines.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _slugify(project_dir: str) -> str:
    """Filesystem-safe project slug: every non-alphanumeric char becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", project_dir)


class SessionStore:
    def __init__(self, project_dir: str, base_dir: Optional[str] = None):
        self.project_dir = project_dir
        self.base_dir = (
            Path(base_dir) if base_dir else Path.home() / ".robodog" / "projects"
        )
        self.slug = _slugify(project_dir)
        self.dir = self.base_dir / self.slug

    # ---- internals ------------------------------------------------------
    def _path(self, session_id: str) -> Path:
        return self.dir / f"{session_id}.jsonl"

    def _append_line(self, path: Path, obj: Dict[str, Any]) -> bool:
        """Append one JSON line. Never raises; logs and returns False on error."""
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            return True
        except OSError as exc:
            logger.warning("session write failed for %s: %s", path, exc)
            return False

    def _read(self, path: Path) -> Optional[Tuple[float, Dict[str, Any], List[dict]]]:
        """Parse a session file -> (mtime, merged_meta, turns), or None if unreadable.

        Later meta_update lines override earlier meta keys. Corrupt or
        unexpected lines are skipped.
        """
        try:
            mtime = path.stat().st_mtime
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("session read failed for %s: %s", path, exc)
            return None
        meta: Dict[str, Any] = {}
        turns: List[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("skipping corrupt line in %s", path)
                continue
            if not isinstance(obj, dict):
                continue
            kind = obj.get("type")
            if kind == "meta":
                meta.update({k: v for k, v in obj.items() if k != "type"})
            elif kind == "meta_update":
                meta.update({k: v for k, v in obj.items() if k not in ("type", "ts")})
            elif kind == "turn":
                turns.append({
                    "role": obj.get("role", ""),
                    "content": obj.get("content", ""),
                    "tool_name": obj.get("tool_name", ""),
                })
        return mtime, meta, turns

    # ---- write path -----------------------------------------------------
    def new_session(self, name: Optional[str] = None) -> str:
        """Create a session file; return its id like '20260718-231455-a3f2'."""
        self.dir.mkdir(parents=True, exist_ok=True)
        session_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self._append_line(self._path(session_id), {
            "type": "meta",
            "id": session_id,
            "name": name,
            "created": time.time(),
            "project": self.project_dir,
        })
        return session_id

    def append_turn(self, session_id: str, role: str, content: str,
                    tool_name: str = "") -> None:
        """Append one turn line. Cheap; never raises (log + swallow IO errors)."""
        path = self._path(session_id)
        if not path.exists():
            logger.warning("append_turn: session %s is gone; turn dropped", session_id)
            return
        self._append_line(path, {
            "type": "turn",
            "role": role,
            "content": content,
            "tool_name": tool_name,
            "ts": time.time(),
        })

    def set_meta(self, session_id: str, **kv: Any) -> None:
        """Append a meta_update line (e.g. name=, model=, total_tokens=)."""
        path = self._path(session_id)
        if not path.exists():
            logger.warning("set_meta: session %s is gone; update dropped", session_id)
            return
        entry: Dict[str, Any] = {"type": "meta_update"}
        entry.update(kv)
        entry["ts"] = time.time()
        self._append_line(path, entry)

    # ---- read path ------------------------------------------------------
    def list_sessions(self) -> List[dict]:
        """All sessions in this project, newest first (by file mtime)."""
        if not self.dir.is_dir():
            return []
        out: List[dict] = []
        for path in self.dir.glob("*.jsonl"):
            parsed = self._read(path)
            if parsed is None:
                continue
            mtime, meta, turns = parsed
            first_prompt = next(
                (t["content"] for t in turns if t["role"] == "user"), "")[:80]
            out.append({
                "id": meta.get("id", path.stem),
                "name": meta.get("name") or "",
                "created": meta.get("created", 0.0),
                "mtime": mtime,
                "turn_count": len(turns),
                "first_prompt": first_prompt,
            })
        out.sort(key=lambda s: s["mtime"], reverse=True)
        return out

    def load(self, session_id: str) -> Optional[dict]:
        """{'meta': merged meta, 'turns': [...]} or None if missing/unreadable."""
        parsed = self._read(self._path(session_id))
        if parsed is None:
            return None
        _mtime, meta, turns = parsed
        return {"meta": meta, "turns": turns}

    def latest(self) -> Optional[str]:
        """id of the most recently modified session in this project, or None."""
        sessions = self.list_sessions()
        return sessions[0]["id"] if sessions else None

    # ---- management -----------------------------------------------------
    def rename(self, session_id: str, name: str) -> bool:
        path = self._path(session_id)
        if not path.exists():
            return False
        return self._append_line(path, {
            "type": "meta_update", "name": name, "ts": time.time(),
        })

    def delete(self, session_id: str) -> bool:
        try:
            self._path(session_id).unlink()
            return True
        except OSError:
            return False

    def prune(self, keep_days: int = 30) -> int:
        """Delete session files older than keep_days (by mtime); return count."""
        if not self.dir.is_dir():
            return 0
        cutoff = time.time() - keep_days * 86400
        deleted = 0
        for path in list(self.dir.glob("*.jsonl")):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    deleted += 1
            except OSError as exc:
                logger.warning("prune failed for %s: %s", path, exc)
                continue
        return deleted
