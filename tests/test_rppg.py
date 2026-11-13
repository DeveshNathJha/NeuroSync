"""Contactless heart rate on synthetic colour traces / frames (no camera needed)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import AttrDict, settings  # noqa: E402
from src.perception.rppg import HeartRateMonitor, HRReading, RPPGEstimator, estimate_baseline, skin_roi  # noqa: E402


def synthetic_trace(est, seconds=20, fps=30, pulse_hz=1.2, pulse=1.0, noise=0.25, seed=0, jitter=False):
    rng = np.random.default_rng(seed)
    readings, t = [], 0.0
    for i in range(int(seconds * fps)):
        t = i / fps + (rng.uniform(-0.008, 0.008) if jitter else 0.0)
        p = pulse * 0.6 * np.sin(2 * np.pi * pulse_hz * t)
        rgb = (120 + 0.3 * p + rng.normal(0, noise), 90 + 1.0 * p + rng.normal(0, noise),
               70 + 0.5 * p + rng.normal(0, noise))
        est.add_sample(t, rgb)
        r = est.estimate(t)
        if r:
            readings.append(r)
    return readings


@pytest.mark.parametrize("method", ["pos", "green"])
def test_recovers_72_bpm(method):
    cfg = AttrDict(dict(settings.rppg))
    cfg.method = method
    readings = synthetic_trace(RPPGEstimator(cfg))
    assert readings, "should emit once window_s of data exists"
    last = readings[-1]
    assert abs(last.bpm - 72) < 3
    assert last.reliable and last.snr_db >= settings.rppg.min_snr_db


def test_irregular_timestamps():
    last = synthetic_trace(RPPGEstimator(), jitter=True, pulse_hz=1.5)[-1]
    assert abs(last.bpm - 90) < 4 and last.reliable


def test_pure_noise_is_unreliable():
    readings = synthetic_trace(RPPGEstimator(), pulse=0.0)
    assert readings and not any(r.reliable for r in readings[-3:])


def test_no_estimate_before_window_and_rate_limited():
    est = RPPGEstimator()
    readings = synthetic_trace(est, seconds=20)
    assert readings[0].t >= settings.rppg.window_s * 0.9
    gaps = np.diff([r.t for r in readings])
    assert np.all(gaps >= settings.rppg.update_every_s - 1e-6)


def test_update_with_frames_and_face_box():
    est = RPPGEstimator()
    rng = np.random.default_rng(0)
    out = None
    for i in range(30 * 15):
        t = i / 30
        p = 0.6 * np.sin(2 * np.pi * 1.2 * t)
        frame = np.zeros((120, 160, 3), dtype=np.float64)
        frame[..., 0] = 70 + 0.5 * p                     # B
        frame[..., 1] = 90 + 1.0 * p                     # G
        frame[..., 2] = 120 + 0.3 * p                    # R
        frame = np.clip(frame + rng.normal(0, 2, frame.shape), 0, 255).astype(np.uint8)
        r = est.update(t, frame, (40, 20, 80, 90))
        out = r or out
    assert out is not None and abs(out.bpm - 72) < 4


def test_no_face_no_reading():
    est = RPPGEstimator()
    frame = np.zeros((10, 10, 3), np.uint8)
    assert all(est.update(i / 30, frame, None) is None for i in range(400))


def test_skin_roi_inside_frame():
    rows, cols = skin_roi((0, 0, 100, 100), (50, 60, 3))
    assert rows.stop <= 50 and cols.stop <= 60
    assert skin_roi((0, 0, 2, 2), (50, 60, 3)) is None


def _r(t, bpm, reliable=True, snr=8.0):
    return HRReading(t=t, bpm=bpm, snr_db=snr, reliable=reliable)


def test_baseline_is_median_of_reliable_readings():
    assert estimate_baseline([_r(0, 70), _r(1, 74), _r(2, 200, reliable=False), _r(3, 72)]) == 72
    assert estimate_baseline([_r(0, 70, reliable=False)]) is None


def test_monitor_needs_baseline():
    mon = HeartRateMonitor()
    assert [mon.update(_r(t, 150)) for t in range(20)] == [[]] * 20
    assert mon.flush() == []


def test_elevated_heart_rate_event():
    mon = HeartRateMonitor()
    mon.set_baseline(75)
    events = []
    for t in range(30):
        bpm = 105 if 5 <= t <= 15 else 76                 # baseline + 30 for 10 s
        events += mon.update(_r(float(t), bpm))
    events += mon.flush()
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "elevated_heart_rate" and ev.source == "rppg"
    assert ev.start == 5 and ev.end == 15 and 0.5 <= ev.confidence <= 1
    assert ev.evidence["baseline_bpm"] == 75


def test_short_or_unreliable_elevation_is_ignored():
    mon = HeartRateMonitor()
    mon.set_baseline(75)
    events = []
    for t in range(20):
        events += mon.update(_r(float(t), 110 if t in (3, 4) else 76))            # 1 s only
        events += mon.update(_r(float(t) + 0.5, 140, reliable=False))             # unreliable spikes
    assert events + mon.flush() == []
