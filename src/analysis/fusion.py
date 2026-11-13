"""
src/analysis/fusion.py
----------------------
Links behaviour / sound events with physiological (heart-rate) events that
happen at the same time, so a reviewer sees "this repetitive movement
co-occurred with a heart rate above baseline".

This is a time-overlap annotation only. It does not infer a cause, a
"neurological state" or a confidence of its own (the old engine attached a
fixed 0.98 confidence and EEG wording without any EEG data).
"""

from __future__ import annotations

from src.core.events import Event

PHYSIOLOGICAL = {"elevated_heart_rate"}


def _gap(a: Event, b: Event) -> float:
    """Seconds between two intervals (0 if they overlap)."""
    return max(0.0, max(a.start, b.start) - min(a.end, b.end))


def link_co_occurring(events: list[Event], window_s: float) -> list[Event]:
    """Fill Event.linked (both directions) for behaviour/audio <-> heart-rate pairs within window_s."""
    phys = [e for e in events if e.kind in PHYSIOLOGICAL]
    other = [e for e in events if e.kind not in PHYSIOLOGICAL]
    for a in other:
        for p in phys:
            if _gap(a, p) <= window_s:
                if p.id not in a.linked:
                    a.linked.append(p.id)
                if a.id not in p.linked:
                    p.linked.append(a.id)
    return events
