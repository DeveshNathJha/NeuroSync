"""
src/core/events.py
------------------
The single data type every detector produces and every other part consumes.

An Event is a SUGGESTION: it starts as "pending" and only a human reviewer
can mark it "confirmed" or "rejected". Reports use confirmed events only.

Names describe what is observable ("repetitive hand/arm movement"), never a
clinical interpretation.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

# kind -> human-readable, non-diagnostic label
EVENT_LABELS: dict[str, str] = {
    "repetitive_hand_movement": "Repetitive hand/arm movement",
    "repetitive_head_movement": "Repetitive head movement",
    "head_turned_away": "Head turned away from camera",
    "loud_vocalisation": "Loud vocalisation / loud sound",
    "elevated_heart_rate": "Heart rate above personal baseline",
}

SOURCES = ("vision", "audio", "rppg")
STATUSES = ("pending", "confirmed", "rejected")


@dataclass
class Event:
    kind: str
    start: float                 # seconds since the session started
    end: float
    confidence: float            # 0..1, computed by the detector (not hard-coded)
    source: str                  # vision | audio | rppg
    evidence: dict[str, Any] = field(default_factory=dict)   # e.g. {"freq_hz": 3.2}
    status: str = "pending"      # pending | confirmed | rejected
    note: str = ""               # reviewer's note
    linked: list[str] = field(default_factory=list)          # ids of co-occurring events
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def __post_init__(self):
        if self.kind not in EVENT_LABELS:
            raise ValueError(f"unknown event kind '{self.kind}'")
        if self.source not in SOURCES:
            raise ValueError(f"unknown source '{self.source}'")
        if self.status not in STATUSES:
            raise ValueError(f"unknown status '{self.status}'")
        if self.end < self.start:
            raise ValueError("event end is before its start")
        self.confidence = float(min(max(self.confidence, 0.0), 1.0))

    @property
    def label(self) -> str:
        return EVENT_LABELS[self.kind]

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        return cls(**d)


def merge_events(events: list[Event], gap_s: float) -> list[Event]:
    """
    Merge events of the same kind and source that overlap or are closer than
    `gap_s`. Confidence of a merged event = max of its parts.
    """
    out: list[Event] = []
    for ev in sorted(events, key=lambda e: (e.kind, e.source, e.start)):
        last = out[-1] if out else None
        if last and last.kind == ev.kind and last.source == ev.source and ev.start - last.end <= gap_s:
            last.end = max(last.end, ev.end)
            last.confidence = max(last.confidence, ev.confidence)
            last.evidence = {**last.evidence, **ev.evidence}
        else:
            out.append(Event(**{**ev.to_dict(), "id": ev.id}))
    return sorted(out, key=lambda e: e.start)
