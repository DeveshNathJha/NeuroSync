"""
src/storage/store.py
--------------------
Encrypted, local-only storage of sessions.

Layout (<data_dir>/sessions):
    <session_id>.enc   Fernet-encrypted JSON of Session.to_dict()
    index.enc          Fernet-encrypted {session_id: summary} for fast listing

Privacy features:
  - everything at rest is encrypted with a key kept outside the repository
  - delete_subject(): right to erasure – all sessions of a person are removed
  - export_subject(): data portability – a decrypted JSON copy for the family
  - purge_older_than(): retention policy
  - every read, write, export and deletion is recorded in the audit log
  - history and trends use CONFIRMED events only (Session.summary())
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from src.config import data_dir
from src.core.events import EVENT_LABELS
from src.core.session import Session
from src.storage.audit import AuditLog
from src.storage.keystore import KeyStore

INDEX_FILE = "index.enc"


class StoreError(RuntimeError):
    pass


class SessionStore:
    def __init__(self, root: Optional[Path] = None, keystore: Optional[KeyStore] = None,
                 audit: Optional[AuditLog] = None):
        self.root = Path(root) if root is not None else data_dir() / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)
        self.keystore = keystore or KeyStore()
        self.audit = audit or AuditLog()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ helpers
    def _fernet(self) -> Fernet:
        return self.keystore.fernet()

    def _path(self, session_id: str) -> Path:
        if not session_id.isalnum():
            raise StoreError(f"invalid session id '{session_id}'")
        return self.root / f"{session_id}.enc"

    def _read_index(self) -> dict:
        path = self.root / INDEX_FILE
        if not path.exists():
            return {}
        try:
            return json.loads(self._fernet().decrypt(path.read_bytes()))
        except InvalidToken as exc:
            raise StoreError("Index cannot be decrypted – wrong or missing key.") from exc

    def _write_index(self, index: dict) -> None:
        tmp = self.root / (INDEX_FILE + ".tmp")
        tmp.write_bytes(self._fernet().encrypt(json.dumps(index).encode("utf-8")))
        tmp.replace(self.root / INDEX_FILE)

    @staticmethod
    def _index_entry(session: Session) -> dict:
        s = session.summary()
        s.update({"started_at": session.started_at, "ended_at": session.ended_at})
        return s

    # ------------------------------------------------------------------ write
    def save(self, session: Session, actor: str) -> Path:
        path = self._path(session.id)
        data = json.dumps(session.to_dict()).encode("utf-8")
        with self._lock:
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(self._fernet().encrypt(data))
            tmp.replace(path)
            index = self._read_index()
            index[session.id] = self._index_entry(session)
            self._write_index(index)
        subject = session.consent.subject_id if session.consent else None
        self.audit.log("save_session", actor, subject_id=subject, session_id=session.id,
                       details=f"confirmed={len(session.confirmed())}")
        return path

    # ------------------------------------------------------------------ read
    def load(self, session_id: str, actor: str) -> Session:
        path = self._path(session_id)
        if not path.exists():
            raise KeyError(f"no session {session_id}")
        try:
            session = Session.from_dict(json.loads(self._fernet().decrypt(path.read_bytes())))
        except InvalidToken as exc:
            raise StoreError("Session cannot be decrypted – wrong or missing key.") from exc
        subject = session.consent.subject_id if session.consent else None
        self.audit.log("view_session", actor, subject_id=subject, session_id=session_id)
        return session

    def list_sessions(self, subject_id: Optional[str] = None) -> list[dict]:
        """Summaries (confirmed events only), newest first."""
        rows = [{"session_id": sid, **entry} for sid, entry in self._read_index().items()]
        if subject_id is not None:
            rows = [r for r in rows if r.get("subject_id") == subject_id]
        return sorted(rows, key=lambda r: r.get("started_at") or 0, reverse=True)

    def subjects(self) -> list[str]:
        return sorted({r["subject_id"] for r in self._read_index().values() if r.get("subject_id")})

    def trends(self, subject_id: str) -> list[dict]:
        """Chronological per-session counts of CONFIRMED events by kind, plus mean heart rate."""
        out = []
        for row in sorted(self.list_sessions(subject_id), key=lambda r: r.get("started_at") or 0):
            counts = row.get("counts_by_kind", {})
            out.append({
                "session_id": row["session_id"],
                "started_at": row.get("started_at"),
                "duration_s": row.get("duration_s"),
                "confirmed_events": row.get("confirmed_events", 0),
                **{kind: counts.get(kind, 0) for kind in EVENT_LABELS},
                "mean_heart_rate": row.get("mean_heart_rate"),
            })
        return out

    # ------------------------------------------------------------------ delete / export
    def delete_session(self, session_id: str, actor: str) -> bool:
        path = self._path(session_id)
        with self._lock:
            index = self._read_index()
            entry = index.pop(session_id, None)
            existed = path.exists()
            if existed:
                path.unlink()
            if entry is not None:
                self._write_index(index)
        if existed or entry is not None:
            self.audit.log("delete_session", actor, subject_id=(entry or {}).get("subject_id"),
                           session_id=session_id)
        return existed or entry is not None

    def delete_subject(self, subject_id: str, actor: str) -> int:
        """Right to erasure: remove every session of this subject. Returns the number removed."""
        with self._lock:
            index = self._read_index()
            ids = [sid for sid, e in index.items() if e.get("subject_id") == subject_id]
            for sid in ids:
                self._path(sid).unlink(missing_ok=True)
                index.pop(sid, None)
            self._write_index(index)
        self.audit.log("delete_subject", actor, subject_id=subject_id, details=f"sessions={len(ids)}")
        return len(ids)

    def export_subject(self, subject_id: str, actor: str) -> bytes:
        """Decrypted JSON of all sessions of a subject (data portability)."""
        sessions = []
        for row in self.list_sessions(subject_id):
            path = self._path(row["session_id"])
            if path.exists():
                sessions.append(json.loads(self._fernet().decrypt(path.read_bytes())))
        self.audit.log("export_subject", actor, subject_id=subject_id, details=f"sessions={len(sessions)}")
        payload = {"subject_id": subject_id, "exported_at": time.time(), "sessions": sessions}
        return json.dumps(payload, indent=2).encode("utf-8")

    def purge_older_than(self, days: float, actor: str, now: Optional[float] = None) -> int:
        """Retention policy: delete sessions that started more than `days` ago."""
        cutoff = (now if now is not None else time.time()) - days * 86400
        with self._lock:
            index = self._read_index()
            old = [sid for sid, e in index.items() if (e.get("started_at") or 0) < cutoff]
            for sid in old:
                self._path(sid).unlink(missing_ok=True)
                index.pop(sid, None)
            self._write_index(index)
        self.audit.log("purge_retention", actor, details=f"days={days} sessions={len(old)}")
        return len(old)

    # ------------------------------------------------------------------ key rotation
    def rotate_key(self, actor: str) -> int:
        """Re-encrypt every session and the index with a fresh key. Returns files re-encrypted."""
        with self._lock:
            old = self._fernet()
            new_key = Fernet.generate_key()
            new = Fernet(new_key)
            files = [p for p in self.root.glob("*.enc")]
            plain = {p: old.decrypt(p.read_bytes()) for p in files}  # decrypt all first: fail before writing
            for p, data in plain.items():
                tmp = p.with_suffix(".tmp")
                tmp.write_bytes(new.encrypt(data))
                tmp.replace(p)
            self.keystore.replace_key(new_key)
        self.audit.log("rotate_key", actor, details=f"files={len(files)}")
        return len(files)
