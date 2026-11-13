"""Co-occurrence linking between behaviour/sound and heart-rate events."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analysis.fusion import link_co_occurring  # noqa: E402
from src.core.events import Event  # noqa: E402


def ev(kind, start, end, source):
    return Event(kind=kind, start=start, end=end, confidence=0.7, source=source)


def test_links_overlapping_and_nearby_events_both_ways():
    hand = ev("repetitive_hand_movement", 10, 14, "vision")
    loud = ev("loud_vocalisation", 22, 23, "audio")
    far = ev("head_turned_away", 60, 65, "vision")
    hr = ev("elevated_heart_rate", 12, 20, "rppg")
    out = link_co_occurring([hand, loud, far, hr], window_s=5.0)
    assert out == [hand, loud, far, hr]                    # same list, annotated in place
    assert hand.linked == [hr.id] and loud.linked == [hr.id]
    assert far.linked == []
    assert set(hr.linked) == {hand.id, loud.id}


def test_no_heart_rate_events_no_links_and_idempotent():
    a = ev("repetitive_hand_movement", 0, 3, "vision")
    b = ev("loud_vocalisation", 1, 2, "audio")
    link_co_occurring([a, b], 5)
    assert a.linked == [] and b.linked == []
    hr = ev("elevated_heart_rate", 2, 9, "rppg")
    link_co_occurring([a, hr], 5)
    link_co_occurring([a, hr], 5)
    assert a.linked == [hr.id] and hr.linked == [a.id]


def test_confidence_is_never_overwritten():
    a = ev("repetitive_hand_movement", 0, 3, "vision")
    hr = ev("elevated_heart_rate", 1, 9, "rppg")
    link_co_occurring([a, hr], 5)
    assert a.confidence == 0.7 and hr.confidence == 0.7
