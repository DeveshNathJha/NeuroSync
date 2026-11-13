"""Behaviour detector on synthetic landmark sequences (no camera, no models needed)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.perception.behaviour import BehaviourDetector, analyse_oscillation, oscillation_score  # noqa: E402
from src.perception.landmarks import FrameLandmarks  # noqa: E402

FPS = 30


def frame(t, wrist_dy=0.0, wrist_dx=0.0, nose_dy=0.0, nose_dx=0.0, face=True, pose=True):
    lm = FrameLandmarks(t=t)
    if face:
        lm.nose = (0.5 + nose_dx, 0.3 + nose_dy)
        lm.left_ear, lm.right_ear = (0.45, 0.3), (0.55, 0.3)
    if pose:
        lm.left_shoulder, lm.right_shoulder = (0.4, 0.5), (0.6, 0.5)          # shoulder width 0.2
        lm.left_wrist = (0.38 + wrist_dx, 0.7 + wrist_dy)
        lm.right_wrist = (0.62, 0.7)
    return lm


def run(make, seconds=8.0, fps=FPS):
    det = BehaviourDetector(fps=fps)
    events = []
    for i in range(int(seconds * fps)):
        events += det.update(make(i / fps))
    return events + det.flush(seconds), det


def kinds(events):
    return [e.kind for e in events]


def test_fast_wrist_oscillation_is_repetitive_hand_movement():
    events, _ = run(lambda t: frame(t, wrist_dy=0.06 * np.sin(2 * np.pi * 3 * t)))
    assert kinds(events) == ["repetitive_hand_movement"]
    ev = events[0]
    assert ev.status == "pending" and ev.source == "vision"
    assert 2.5 < ev.evidence["freq_hz"] < 3.5
    assert 0.5 <= ev.confidence <= 1.0
    assert ev.end - ev.start > 5


def test_still_hands_produce_nothing():
    rng = np.random.default_rng(0)
    events, det = run(lambda t: frame(t, wrist_dy=rng.normal(0, 0.002)))
    assert events == []
    assert det.live_state()["repetitive_hand_movement"] < 0.5


def test_slow_movement_and_raised_hand_are_not_flapping():
    slow, _ = run(lambda t: frame(t, wrist_dy=0.06 * np.sin(2 * np.pi * 0.5 * t)))
    raised, _ = run(lambda t: frame(t, wrist_dy=-0.3 if t > 2 else 0.0))       # hand raised and held
    assert "repetitive_hand_movement" not in kinds(slow)
    assert "repetitive_hand_movement" not in kinds(raised)


def test_tiny_fast_tremor_below_amplitude_threshold():
    events, _ = run(lambda t: frame(t, wrist_dy=0.004 * np.sin(2 * np.pi * 4 * t)))
    assert events == []


def test_irregular_frame_rate_and_short_gaps_are_handled():
    rng = np.random.default_rng(1)
    det = BehaviourDetector(fps=FPS)
    t, events = 0.0, []
    while t < 8:
        t += rng.uniform(0.02, 0.06)                     # 16-50 fps jitter
        visible = not (3.0 < t < 3.2)                   # 200 ms dropout
        events += det.update(frame(t, wrist_dy=0.06 * np.sin(2 * np.pi * 3 * t), pose=visible))
    events += det.flush(t)
    assert "repetitive_hand_movement" in kinds(events)


def test_repetitive_head_movement():
    events, _ = run(lambda t: frame(t, nose_dy=0.02 * np.sin(2 * np.pi * 1.5 * t)))
    assert kinds(events) == ["repetitive_head_movement"]


def test_head_turned_away_needs_minimum_duration():
    long_turn, _ = run(lambda t: frame(t, nose_dx=0.04 if 1 < t < 5 else 0.0))
    short_turn, _ = run(lambda t: frame(t, nose_dx=0.04 if 1 < t < 2 else 0.0))
    assert kinds(long_turn) == ["head_turned_away"]
    assert 0.9 < long_turn[0].start < 1.2 and 4.8 < long_turn[0].end < 5.1
    assert short_turn == []


def test_face_missing_is_not_head_turned():
    events, _ = run(lambda t: frame(t, face=False))
    assert events == []


def test_two_bursts_far_apart_give_two_events():
    def make(t):
        burst = (1 < t < 5) or (10 < t < 14)
        return frame(t, wrist_dy=0.06 * np.sin(2 * np.pi * 3 * t) if burst else 0.0)
    events, _ = run(make, seconds=16)
    hand = [e for e in events if e.kind == "repetitive_hand_movement"]
    assert len(hand) == 2 and hand[0].end < hand[1].start


def test_oscillation_helpers():
    t = np.arange(0, 2, 1 / 30)
    osc = analyse_oscillation(t, 0.2 * np.sin(2 * np.pi * 3 * t), (2, 6), 2.0)
    assert osc is not None and abs(osc.freq_hz - 3) < 0.6 and osc.power_ratio > 0.9
    assert analyse_oscillation(t[:10], np.zeros(10), (2, 6), 2.0) is None        # window not covered
    score, active = oscillation_score(osc, 0.15, 0.45)
    assert active and 0.5 <= score <= 1.0
    assert oscillation_score(None, 0.15, 0.45) == (0.0, False)


@pytest.mark.parametrize("fps", [15, 30])
def test_works_at_analysis_frame_rates(fps):
    events, _ = run(lambda t: frame(t, wrist_dy=0.06 * np.sin(2 * np.pi * 3 * t)), fps=fps)
    assert "repetitive_hand_movement" in kinds(events)
