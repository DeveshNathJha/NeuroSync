"""Unit tests for src/core/formatting.py."""

import csv
import io

import pytest

from src.core import formatting as h
from src.core.events import Event


def ev(kind="repetitive_hand_movement", start=0.0, end=2.0, status="pending", note="", source="vision"):
    e = Event(kind=kind, start=start, end=end, confidence=0.8, source=source)
    e.status, e.note = status, note
    return e


@pytest.mark.parametrize("sec, out", [(0, "00:00"), (12.4, "00:12"), (59.6, "01:00"), (3725, "62:05"),
                                      (None, "--:--"), (-1, "--:--")])
def test_fmt_mmss(sec, out):
    assert h.fmt_mmss(sec) == out


def test_fmt_span():
    assert h.fmt_span(61, 75) == "01:01–01:15"


def test_event_rows_sorted_and_complete():
    a, b = ev(start=10, end=12), ev(kind="loud_vocalisation", start=1, end=3, source="audio")
    rows = h.event_rows([a, b])
    assert [r["id"] for r in rows] == [b.id, a.id]
    assert rows[0]["event"] == "Loud vocalisation / loud sound"
    assert set(rows[0]) >= {"id", "time", "event", "confidence", "source", "status", "note", "linked"}


def test_changed_reviews_only_returns_edits():
    a, b = ev(), ev(start=5, end=6)
    rows = h.event_rows([a, b])
    rows[0]["status"] = "confirmed"
    rows[1]["note"] = "ok"
    rows.append({"id": "missing", "status": "confirmed"})
    changes = h.changed_reviews(rows, [a, b])
    assert sorted(changes) == sorted([(a.id, "confirmed", ""), (b.id, "pending", "ok")])


def test_changed_reviews_ignores_invalid_status():
    a = ev()
    rows = h.event_rows([a])
    rows[0]["status"] = "diagnosed"
    assert h.changed_reviews(rows, [a]) == []


def test_confirmed_csv_only_confirmed():
    text = h.confirmed_csv([ev(status="confirmed", note="seen"), ev(start=4, end=5, status="rejected"),
                            ev(start=6, end=7)])
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][0] == "start_s"
    assert len(rows) == 2 and rows[1][-1] == "seen"


@pytest.mark.parametrize("sid, flagged", [
    ("S-014", False), ("child_A", False), ("subj7", False),
    ("Rahul Sharma", True), ("a.b@example.com", True), ("+91 98765 43210", True), ("", True),
])
def test_identifier_warnings(sid, flagged):
    assert bool(h.identifier_warnings(sid)) is flagged


@pytest.mark.parametrize("consent, delete_policy, keep", [
    (False, False, False), (False, True, False), (True, True, False), (True, False, True)])
def test_should_keep_video(consent, delete_policy, keep):
    assert h.should_keep_video(consent, delete_policy) is keep
