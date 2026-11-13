"""Tests for src/config.py, src/core/events.py and src/core/session.py."""

import os
from pathlib import Path

import pytest

from src.config import PROJECT_ROOT, data_dir, load_settings, resolve, settings
from src.core.events import EVENT_LABELS, Event, merge_events
from src.core.session import Consent, Session, SessionError


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def consent(subject="S-01"):
    return Consent(subject_id=subject, given_by="parent/guardian", recorded_by="therapist")


def ev(kind="repetitive_hand_movement", start=0.0, end=2.0, source="vision", conf=0.8, **kw):
    return Event(kind=kind, start=start, end=end, confidence=conf, source=source, **kw)


# ----------------------------------------------------------------- config
def test_settings_load_and_attribute_access():
    assert settings.app.name == "NeuroSync"
    assert settings.session.require_consent is True
    assert load_settings().behaviour.window_s > 0


def test_data_dir_uses_env_and_is_outside_project(tmp_path, monkeypatch):
    monkeypatch.setenv("NEUROSYNC_DATA_DIR", str(tmp_path / "d"))
    d = data_dir()
    assert d.exists() and d == (tmp_path / "d").resolve()
    # the test session's data dir is never inside the repo
    assert not str(Path(os.environ["NEUROSYNC_DATA_DIR"]).resolve()).startswith(str(PROJECT_ROOT))


def test_resolve_project_relative():
    assert resolve("models/x.gguf") == PROJECT_ROOT / "models" / "x.gguf"


# ----------------------------------------------------------------- events
def test_event_validation_and_clamping():
    e = ev(conf=1.7)
    assert e.confidence == 1.0 and e.status == "pending" and e.label == EVENT_LABELS[e.kind]
    with pytest.raises(ValueError):
        ev(kind="meltdown")
    with pytest.raises(ValueError):
        ev(source="eeg")
    with pytest.raises(ValueError):
        ev(start=5, end=1)


def test_event_roundtrip():
    e = ev(evidence={"freq_hz": 3.1}, note="x")
    assert Event.from_dict(e.to_dict()) == e


def test_merge_events_same_kind_within_gap():
    events = [ev(start=0, end=2, conf=0.5), ev(start=2.5, end=4, conf=0.9), ev(start=10, end=11),
              ev(kind="loud_vocalisation", start=1, end=2, source="audio")]
    merged = merge_events(events, gap_s=1.0)
    hand = [m for m in merged if m.kind == "repetitive_hand_movement"]
    assert [(m.start, m.end) for m in hand] == [(0, 4), (10, 11)]
    assert hand[0].confidence == 0.9
    assert len(merged) == 3


# ----------------------------------------------------------------- session
def test_consent_required():
    with pytest.raises(SessionError):
        Session(None)
    with pytest.raises(ValueError):
        Consent(subject_id=" ", given_by="parent", recorded_by="t")
    Session(None, require_consent=False)  # allowed only when explicitly disabled


def test_lifecycle_and_time_limit():
    clock = Clock()
    s = Session(consent(), max_duration_s=60, clock=clock)
    with pytest.raises(SessionError):
        s.stop()
    s.start()
    assert s.running
    with pytest.raises(SessionError):
        s.start()
    clock.t += 30
    assert not s.check_time_limit() and s.running
    clock.t += 31
    assert s.check_time_limit() and not s.running
    assert s.elapsed() == pytest.approx(61)


def test_review_and_summary_counts_confirmed_only():
    clock = Clock()
    s = Session(consent(), clock=clock)
    s.start()
    a, b, c = ev(start=0, end=3), ev(start=10, end=12), ev(kind="loud_vocalisation", start=5, end=6, source="audio")
    s.add_events([a, b, c])
    s.review(a.id, "confirmed", note="seen")
    s.review(c.id, "rejected")
    with pytest.raises(KeyError):
        s.review("nope", "confirmed")
    with pytest.raises(ValueError):
        s.review(a.id, "maybe")
    clock.t += 100
    s.stop()
    summ = s.summary()
    assert summ["confirmed_events"] == 1 and summ["rejected_events"] == 1 and summ["suggested_events"] == 3
    assert summ["counts_by_kind"] == {"repetitive_hand_movement": 1}
    assert summ["seconds_by_kind"] == {"repetitive_hand_movement": 3.0}
    assert summ["subject_id"] == "S-01" and summ["duration_s"] == 100
    assert [e.id for e in s.pending()] == [b.id]


def test_session_roundtrip():
    s = Session(consent())
    s.start()
    s.add_events([ev(), ev(kind="elevated_heart_rate", source="rppg", start=1, end=9)])
    s.heart_rate = [(1.0, 80.0, 6.0)]
    s.baseline_hr = 75.0
    s.stop()
    r = Session.from_dict(s.to_dict())
    assert r.id == s.id and r.consent == s.consent and r.baseline_hr == 75.0
    assert [e.to_dict() for e in r.events] == [e.to_dict() for e in s.events]
    assert r.heart_rate == [(1.0, 80.0, 6.0)]
