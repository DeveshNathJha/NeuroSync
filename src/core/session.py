"""
src/core/session.py
-------------------
One observation session: consent, a fixed start/stop, the suggested events
and the reviewer's decisions.

Design rules (real-world use):
  - no session without a recorded consent (when settings require it)
  - a session always ends: explicit stop or `max_duration_min`
  - only events a reviewer CONFIRMED reach reports and history
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from src.core.events import EVENT_LABELS, Event, merge_events


@dataclass
class Consent:
    subject_id: str              # pseudonymous id chosen by the professional, never a name
    given_by: str                # role of the person who consented, e.g. "parent/guardian"
    recorded_by: str             # professional running the session
    purpose: str = "Session observation notes"
    video_stored: bool = False   # raw video is not kept unless explicitly allowed
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        for name in ("subject_id", "given_by", "recorded_by"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"consent field '{name}' is required")


class SessionError(RuntimeError):
    pass


class Session:
    def __init__(self, consent: Optional[Consent], mode: str = "live",
                 max_duration_s: float = 90 * 60, require_consent: bool = True,
                 clock=time.time):
        if require_consent and consent is None:
            raise SessionError("A recorded consent is required before a session can start.")
        if mode not in ("live", "video"):
            raise ValueError("mode must be 'live' or 'video'")
        self.id = uuid.uuid4().hex[:12]
        self.consent = consent
        self.mode = mode
        self.max_duration_s = max_duration_s
        self._clock = clock
        self.started_at: Optional[float] = None
        self.ended_at: Optional[float] = None
        self.events: list[Event] = []
        self.heart_rate: list[tuple[float, float, float]] = []   # (t, bpm, snr_db)
        self.baseline_hr: Optional[float] = None

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self.started_at is not None:
            raise SessionError("session already started")
        self.started_at = self._clock()

    def stop(self) -> None:
        if self.started_at is None:
            raise SessionError("session not started")
        if self.ended_at is None:
            self.ended_at = self._clock()

    @property
    def running(self) -> bool:
        return self.started_at is not None and self.ended_at is None

    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.ended_at if self.ended_at is not None else self._clock()
        return end - self.started_at

    def check_time_limit(self) -> bool:
        """Stops the session when the maximum duration is reached. Returns True if it stopped."""
        if self.running and self.elapsed() >= self.max_duration_s:
            self.stop()
            return True
        return False

    # ------------------------------------------------------------------ events
    def add_events(self, events: list[Event], merge_gap_s: float = 0.0) -> None:
        self.events = merge_events(self.events + list(events), merge_gap_s) if merge_gap_s else \
            sorted(self.events + list(events), key=lambda e: e.start)

    def review(self, event_id: str, status: str, note: str = "") -> Event:
        if status not in ("confirmed", "rejected", "pending"):
            raise ValueError("status must be confirmed, rejected or pending")
        for ev in self.events:
            if ev.id == event_id:
                ev.status = status
                ev.note = note
                return ev
        raise KeyError(f"no event with id {event_id}")

    def confirmed(self) -> list[Event]:
        return [e for e in self.events if e.status == "confirmed"]

    def pending(self) -> list[Event]:
        return [e for e in self.events if e.status == "pending"]

    # ------------------------------------------------------------------ summary
    def summary(self) -> dict[str, Any]:
        """Statistics over CONFIRMED events only (what goes into reports and history)."""
        conf = self.confirmed()
        by_kind = {k: 0 for k in EVENT_LABELS}
        dur_by_kind = {k: 0.0 for k in EVENT_LABELS}
        for e in conf:
            by_kind[e.kind] += 1
            dur_by_kind[e.kind] += e.duration
        reliable_hr = [bpm for _, bpm, snr in self.heart_rate if bpm > 0]
        return {
            "session_id": self.id,
            "subject_id": self.consent.subject_id if self.consent else None,
            "mode": self.mode,
            "duration_s": round(self.elapsed(), 1),
            "suggested_events": len(self.events),
            "confirmed_events": len(conf),
            "rejected_events": sum(e.status == "rejected" for e in self.events),
            "counts_by_kind": {k: v for k, v in by_kind.items() if v},
            "seconds_by_kind": {k: round(v, 1) for k, v in dur_by_kind.items() if v},
            "mean_heart_rate": round(sum(reliable_hr) / len(reliable_hr), 1) if reliable_hr else None,
            "baseline_heart_rate": self.baseline_hr,
        }

    # ------------------------------------------------------------------ persistence
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mode": self.mode,
            "consent": asdict(self.consent) if self.consent else None,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "max_duration_s": self.max_duration_s,
            "baseline_hr": self.baseline_hr,
            "heart_rate": self.heart_rate,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Session:
        s = cls(Consent(**d["consent"]) if d.get("consent") else None, mode=d["mode"],
                max_duration_s=d.get("max_duration_s", 90 * 60), require_consent=False)
        s.id = d["id"]
        s.started_at, s.ended_at = d.get("started_at"), d.get("ended_at")
        s.baseline_hr = d.get("baseline_hr")
        s.heart_rate = [tuple(x) for x in d.get("heart_rate", [])]
        s.events = [Event.from_dict(e) for e in d.get("events", [])]
        return s
