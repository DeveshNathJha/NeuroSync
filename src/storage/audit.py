"""
src/storage/audit.py
--------------------
Append-only, tamper-evident audit trail of who did what with which session.

Each line is a JSON object with an ISO timestamp, the action, the actor, ids
and a SHA-256 hash chain: `hash = sha256(prev_hash + canonical_json(entry))`.
Editing or deleting any earlier line breaks verify().

Only ids and actions are logged – never names, notes, video or sensor data.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import data_dir

GENESIS = "0" * 64


def _digest(prev_hash: str, entry: dict) -> str:
    payload = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, root: Optional[Path] = None):
        root = Path(root) if root is not None else data_dir()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "audit.jsonl"
        self._lock = threading.Lock()

    def _entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def log(self, action: str, actor: str, subject_id: Optional[str] = None,
            session_id: Optional[str] = None, details: str = "") -> dict:
        with self._lock:
            entries = self._entries()
            prev = entries[-1]["hash"] if entries else GENESIS
            entry = {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "action": action,
                "actor": actor,
                "subject_id": subject_id,
                "session_id": session_id,
                "details": details,
                "prev_hash": prev,
            }
            entry["hash"] = _digest(prev, entry)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
            return entry

    def read(self, limit: int = 200) -> list[dict]:
        """Newest entries first."""
        return list(reversed(self._entries()))[:limit]

    def verify(self) -> bool:
        prev = GENESIS
        for entry in self._entries():
            body = {k: v for k, v in entry.items() if k != "hash"}
            if body.get("prev_hash") != prev or _digest(prev, body) != entry.get("hash"):
                return False
            prev = entry["hash"]
        return True
