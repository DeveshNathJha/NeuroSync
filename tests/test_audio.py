"""Loudness events (no microphone needed); video/audio extraction via imageio-ffmpeg."""

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.perception.audio import LiveAudio, LoudnessDetector, analyse_video_audio, dbfs  # noqa: E402

SR = settings.audio.sample_rate
BLOCK = int(SR * settings.audio.block_s)


def tone(seconds, amp, hz=440):
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def feed(samples):
    det = LoudnessDetector()
    events = []
    for i in range(0, len(samples), BLOCK):
        events += det.update(i / SR, samples[i:i + BLOCK])
    return events + det.flush(len(samples) / SR)


def test_dbfs():
    assert dbfs(tone(1, 1.0)) == pytest.approx(-3.01, abs=0.05)
    assert dbfs(tone(1, 0.1)) == pytest.approx(-23.01, abs=0.05)
    assert dbfs(np.zeros(100)) <= -100
    assert dbfs(np.array([32767, -32767], dtype=np.int16)) == pytest.approx(0, abs=0.01)


def test_loud_burst_gives_one_event_with_times():
    sig = np.concatenate([tone(2, 0.01), tone(1.5, 0.8), tone(2, 0.01)])
    events = feed(sig)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "loud_vocalisation" and ev.source == "audio" and ev.status == "pending"
    assert abs(ev.start - 2.0) <= 0.11 and abs(ev.end - 3.5) <= 0.11
    assert 0.5 < ev.confidence <= 1.0 and ev.evidence["peak_dbfs"] > settings.audio.loud_dbfs


def test_quiet_and_very_short_sounds_are_ignored():
    assert feed(tone(3, 0.02)) == []
    assert feed(np.concatenate([tone(1, 0.01), tone(0.2, 0.9), tone(1, 0.01)])) == []   # < loud_min_s


def test_close_bursts_are_merged():
    gap = tone(0.4, 0.01)                                     # < merge_gap_s
    sig = np.concatenate([tone(1, 0.01), tone(1, 0.8), gap, tone(1, 0.8), tone(2, 0.01)])
    assert len(feed(sig)) == 1


def test_confidence_grows_with_loudness():
    soft = feed(np.concatenate([tone(1, 0.01), tone(1, 0.15), tone(1, 0.01)]))[0]
    loud = feed(np.concatenate([tone(1, 0.01), tone(1, 0.95), tone(1, 0.01)]))[0]
    assert loud.confidence > soft.confidence


def _write_wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())


def test_analyse_audio_track_of_a_file(tmp_path):
    pytest.importorskip("imageio_ffmpeg")
    path = tmp_path / "session.wav"
    _write_wav(path, np.concatenate([tone(2, 0.01), tone(1, 0.8), tone(2, 0.01)]))
    events = analyse_video_audio(str(path))
    assert len(events) == 1 and abs(events[0].start - 2.0) < 0.15


def test_file_without_audio_returns_empty(tmp_path):
    pytest.importorskip("imageio_ffmpeg")
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "silent.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (32, 32))
    for _ in range(10):
        writer.write(np.zeros((32, 32, 3), np.uint8))
    writer.release()
    assert analyse_video_audio(str(path)) == []


def test_live_audio_never_crashes_without_a_microphone():
    live = LiveAudio()
    if not live.available:
        assert live.start() is False
    assert live.poll(0.0)[1] == [] and live.drain() == []
    live.stop()
