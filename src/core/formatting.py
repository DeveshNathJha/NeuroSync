"""
src/core/formatting.py
----------------------
Pure helpers shared by the API and exports (no web framework needed):
time formatting, events -> table rows, CSV export, a heuristic that warns when
a "pseudonymous" subject id looks like a real name / e-mail / phone number,
and the raw-video retention rule.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from typing import Any

from src.core.events import EVENT_LABELS, Event

STATUS_OPTIONS = ["pending", "confirmed", "rejected"]
AUDIENCES = {"Professional": "professional", "Family (plain language)": "family"}


def fmt_mmss(seconds: float | None) -> str:
    """12.3 -> '00:12'; 3725 -> '62:05'. None/negative -> '--:--'."""
    if seconds is None or seconds < 0:
        return "--:--"
    total = int(round(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def fmt_span(start: float, end: float) -> str:
    return f"{fmt_mmss(start)}–{fmt_mmss(end)}"


def event_rows(events: Iterable[Event]) -> list[dict[str, Any]]:
    """One row per event for the review table (keeps the id to map edits back)."""
    rows = []
    for e in sorted(events, key=lambda ev: ev.start):
        rows.append({
            "id": e.id,
            "time": fmt_span(e.start, e.end),
            "event": e.label,
            "confidence": round(e.confidence, 2),
            "source": e.source,
            "linked": ", ".join(e.linked),
            "status": e.status,
            "note": e.note,
        })
    return rows


def changed_reviews(rows: list[dict[str, Any]], events: Iterable[Event]) -> list[tuple[str, str, str]]:
    """Compare edited table rows with the events; return (id, status, note) for rows that changed."""
    by_id = {e.id: e for e in events}
    out = []
    for r in rows:
        ev = by_id.get(r.get("id"))
        if ev is None:
            continue
        status = r.get("status") or "pending"
        note = r.get("note") or ""
        if status not in STATUS_OPTIONS:
            continue
        if status != ev.status or note != ev.note:
            out.append((ev.id, status, note))
    return out


def confirmed_csv(events: Iterable[Event]) -> str:
    """CSV of CONFIRMED events only (what may leave the app)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["start_s", "end_s", "start", "end", "event", "kind", "source", "confidence", "note"])
    for e in sorted(events, key=lambda ev: ev.start):
        if e.status != "confirmed":
            continue
        w.writerow([round(e.start, 2), round(e.end, 2), fmt_mmss(e.start), fmt_mmss(e.end),
                    e.label, e.kind, e.source, round(e.confidence, 3), e.note])
    return buf.getvalue()


_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.I)
_PHONE = re.compile(r"(?:\+?\d[\s-]?){7,}")
_NAME = re.compile(r"^[A-Z][a-z]{1,}(?:\s+[A-Z][a-z]{1,})+$")


def identifier_warnings(subject_id: str) -> list[str]:
    """
    Heuristic check that a subject id is pseudonymous. Returns human-readable
    warnings (empty list = looks fine). It can't prove an id is safe; it
    catches the obvious mistakes: e-mails, phone numbers, 'First Last' names.
    """
    s = (subject_id or "").strip()
    warnings = []
    if not s:
        return ["Subject id is empty."]
    if _EMAIL.search(s):
        warnings.append("Looks like an e-mail address.")
    if _PHONE.search(s):
        warnings.append("Contains a long number that looks like a phone number.")
    if _NAME.match(s):
        warnings.append("Looks like a person's name (e.g. 'First Last').")
    return warnings


def should_keep_video(video_stored_consent: bool, delete_after_analysis: bool) -> bool:
    """Raw video is kept only if consent allows it AND the storage policy doesn't delete it."""
    return bool(video_stored_consent) and not bool(delete_after_analysis)


def summary_label(kind: str) -> str:
    return EVENT_LABELS.get(kind, kind)
