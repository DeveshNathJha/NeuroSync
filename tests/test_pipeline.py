"""SessionPipeline and analyse_video with a fake landmark extractor (no models / camera)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import resolve  # noqa: E402
from src.core.session import Consent, Session  # noqa: E402
from src.perception.landmarks import FrameLandmarks  # noqa: E402
from src.pipeline import SessionPipeline, analyse_video  # noqa: E402


class FakeExtractor:
    """Wrists flap at 3 Hz between 2 s and 7 s of session time."""

    def __init__(self):
        self.calls = 0

    def process(self, frame, t):
        self.calls += 1
        dy = 0.06 * np.sin(2 * np.pi * 3 * t) if 2 < t < 7 else 0.0
        return FrameLandmarks(t=t, nose=(0.5, 0.3), left_ear=(0.45, 0.3), right_ear=(0.55, 0.3),
                              left_shoulder=(0.4, 0.5), right_shoulder=(0.6, 0.5),
                              left_wrist=(0.38, 0.7 + dy), right_wrist=(0.62, 0.7), face_box=None)

    def draw(self, frame, lm):
        return frame


def new_session(mode="live"):
    return Session(Consent(subject_id="S-01", given_by="parent/guardian", recorded_by="therapist"), mode=mode)


def test_live_pipeline_produces_pending_events_once():
    s = new_session()
    s.start()
    pipe = SessionPipeline(s, extractor=FakeExtractor())
    frame = np.zeros((48, 64, 3), np.uint8)
    t0 = s.started_at
    state = None
    for i in range(30 * 10):
        _, state = pipe.process_frame(frame, t0 + i / 30)
    assert set(state) >= {"behaviour_scores", "heart_rate", "hr_reliable", "loudness_dbfs", "new_events"}
    assert state["heart_rate"] is None                     # no face box -> no heart rate, never invented

    loud = (0.8 * np.sin(2 * np.pi * 440 * np.arange(1600) / 16000)).astype(np.float32)
    quiet = np.zeros(1600, np.float32)
    for k in range(40):                                    # 4 s of audio, loud from 1 s to 2.5 s
        pipe.process_audio_block(loud if 10 <= k < 25 else quiet, t0 + k * 0.1)

    s.stop()
    events = pipe.finish()
    assert pipe.finish() is events or pipe.finish() == events           # idempotent
    kinds = sorted(e.kind for e in events)
    assert kinds == ["loud_vocalisation", "repetitive_hand_movement"]
    assert all(e.status == "pending" for e in events)
    hand = next(e for e in events if e.kind == "repetitive_hand_movement")
    assert 0 <= hand.start <= 2.5 and 6.5 <= hand.end <= 7.5


def test_pipeline_requires_started_session():
    pipe = SessionPipeline(new_session(), extractor=FakeExtractor())
    with pytest.raises(RuntimeError):
        pipe.process_frame(np.zeros((8, 8, 3), np.uint8), 0.0)


def test_baseline_is_stored_on_session():
    s = new_session()
    pipe = SessionPipeline(s, extractor=FakeExtractor())
    pipe.set_baseline_hr(78.0)
    assert s.baseline_hr == 78.0 and pipe.hr_monitor.baseline == 78.0
    assert pipe.baseline_from_readings() is None


def test_analyse_video_uses_video_time(tmp_path):
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "session.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (64, 48))
    for _ in range(30 * 9):
        writer.write(np.zeros((48, 64, 3), np.uint8))
    writer.release()

    s = new_session(mode="video")
    fake = FakeExtractor()
    progress = []
    analyse_video(str(path), s, progress=progress.append, analysis_fps=15, extractor=fake)
    assert 8.5 <= s.elapsed() <= 9.1                       # duration = video length, not processing time
    assert 120 <= fake.calls <= 140                       # ~15 analysed frames per second
    assert progress[-1] == 1.0
    assert [e.kind for e in s.events] == ["repetitive_hand_movement"]


@pytest.mark.skipif(not (resolve("models") / "pose_landmarker_lite.task").exists(), reason="models not downloaded")
def test_real_extractor_runs_on_a_frame():
    from src.perception.landmarks import LandmarkExtractor
    ext = LandmarkExtractor()
    try:
        frame = np.full((480, 640, 3), 128, np.uint8)
        lm = ext.process(frame, 0.0)
        lm2 = ext.process(frame, 0.0)                      # equal timestamps must not crash
        assert lm.t == 0.0 and not lm.has_face and lm2.face_box is None
        assert ext.draw(frame, lm).shape == frame.shape
    finally:
        ext.close()
