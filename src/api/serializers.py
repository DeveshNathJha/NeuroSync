"""JSON shapes returned by the API (one place, so the web UI and tests agree)."""

from __future__ import annotations

from typing import Any

from src.core.events import Event
from src.core.formatting import fmt_span
from src.core.session import Session


def event_json(e: Event) -> dict[str, Any]:
    d = e.to_dict()
    d["label"] = e.label
    d["span"] = fmt_span(e.start, e.end)
    d["duration"] = round(e.duration, 2)
    return d


def session_json(session: Session, state: str) -> dict[str, Any]:
    d = session.to_dict()
    d["state"] = state
    d["elapsed_s"] = round(session.elapsed(), 1)
    d["summary"] = session.summary()
    d["events"] = [event_json(e) for e in sorted(session.events, key=lambda ev: ev.start)]
    return d
