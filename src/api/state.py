"""
src/api/state.py
----------------
In-memory state of the local server:

  - ActiveSession: a session that has not been discarded yet (live or video),
    with its processing state ("created" | "running" | "analysing" | "stopped")
  - Registry: all active sessions + the single LiveRunner (one camera, one live
    session at a time)
  - Services: everything the routes need (store, audit, report generator and
    the factories that tests replace with fakes)

Saved sessions live encrypted in SessionStore; this registry is only the
working copy while a professional records and reviews a session.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from src.core.session import Session


@dataclass
class ActiveSession:
    session: Session
    state: str = "created"               # created | running | analysing | stopped
    video: dict[str, Any] = field(default_factory=lambda: {
        "progress": 0.0, "error": None, "video_kept": False, "path": None})
    saved: bool = False


class Registry:
    def __init__(self):
        self._items: dict[str, ActiveSession] = {}
        self._lock = threading.RLock()
        self.live_runner = None           # the one LiveRunner, if any

    def add(self, entry: ActiveSession) -> ActiveSession:
        with self._lock:
            self._items[entry.session.id] = entry
            return entry

    def get(self, session_id: str) -> ActiveSession:
        with self._lock:
            if session_id not in self._items:
                raise KeyError(session_id)
            return self._items[session_id]

    def remove(self, session_id: str) -> Optional[ActiveSession]:
        with self._lock:
            return self._items.pop(session_id, None)

    def all(self) -> list[ActiveSession]:
        with self._lock:
            return list(self._items.values())

    @property
    def camera_busy(self) -> bool:
        runner = self.live_runner
        return bool(runner is not None and runner.running)


@dataclass
class Services:
    store: Any
    audit: Any
    reporter: Any
    camera_factory: Callable[[], Any]
    pipeline_factory: Callable[[Session], Any]
    audio_factory: Callable[[], Any]
    extractor_factory: Optional[Callable[[], Any]] = None
    registry: Registry = field(default_factory=Registry)
