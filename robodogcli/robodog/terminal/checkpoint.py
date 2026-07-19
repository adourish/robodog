# file: terminal/checkpoint.py
"""
File checkpointing for /rewind — the undo layer under YOLO permissions.

Before every mutating file operation the registry snapshots the target file
here. Checkpoints are grouped by a "marker" (the prompt index: which user
message triggered the change), so /rewind can restore the working tree to the
state before any given prompt. Mirrors Claude Code's checkpointing (100 most
recent, per-prompt restore).
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional

MAX_SNAPSHOTS = 100


class Checkpointer:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.jsonl"
        self.marker = 0          # current prompt index (app bumps per user msg)
        self._seq = 0
        self._entries: List[dict] = []
        self._load()

    def _load(self):
        if self.manifest_path.exists():
            for line in self.manifest_path.read_text(encoding="utf-8").splitlines():
                try:
                    self._entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if self._entries:
                self._seq = max(e["seq"] for e in self._entries) + 1

    def _append(self, entry: dict):
        self._entries.append(entry)
        with self.manifest_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def set_marker(self, marker: int):
        self.marker = marker

    # ---- capture --------------------------------------------------------
    def snapshot(self, path: Path):
        """Snapshot an existing file before it is mutated."""
        path = Path(path)
        if not path.exists():
            return
        snap_name = f"{self._seq:05d}{path.suffix or '.snap'}"
        shutil.copy2(path, self.root / snap_name)
        self._append({
            "seq": self._seq, "marker": self.marker, "kind": "modified",
            "path": str(path), "snap": snap_name, "ts": time.time(),
        })
        self._seq += 1
        self._prune()

    def record_new(self, path: Path):
        """Record a file the agent created (restore = delete it)."""
        self._append({
            "seq": self._seq, "marker": self.marker, "kind": "created",
            "path": str(Path(path)), "snap": None, "ts": time.time(),
        })
        self._seq += 1

    def _prune(self):
        snaps = [e for e in self._entries if e["snap"]]
        if len(snaps) <= MAX_SNAPSHOTS:
            return
        for e in snaps[: len(snaps) - MAX_SNAPSHOTS]:
            try:
                (self.root / e["snap"]).unlink(missing_ok=True)
                e["snap"] = None  # keep manifest entry, snapshot gone
            except OSError:
                pass

    # ---- inspect / restore ---------------------------------------------
    def markers(self) -> Dict[int, int]:
        """{marker: file-change count} for the /rewind listing."""
        out: Dict[int, int] = {}
        for e in self._entries:
            out[e["marker"]] = out.get(e["marker"], 0) + 1
        return out

    def restore(self, from_marker: int) -> List[str]:
        """
        Undo all changes made at prompt >= from_marker, newest first.
        Returns human-readable actions taken.
        """
        actions: List[str] = []
        restored: set = set()
        for e in reversed(self._entries):
            if e["marker"] < from_marker:
                continue
            p = Path(e["path"])
            key = (e["path"])
            if key in restored:
                continue  # earliest snapshot in range wins; skip newer dupes
            if e["kind"] == "created":
                if p.exists():
                    p.unlink()
                    actions.append(f"deleted {p} (was created)")
                restored.add(key)
            elif e["kind"] == "modified" and e["snap"]:
                # find the OLDEST snapshot of this file within range — that is
                # the pre-change content for from_marker
                oldest = next((x for x in self._entries
                               if x["path"] == e["path"] and x["snap"]
                               and x["marker"] >= from_marker), None)
                if oldest:
                    shutil.copy2(self.root / oldest["snap"], p)
                    actions.append(f"restored {p}")
                restored.add(key)
        return actions
