"""
src/perception/audio.py
-----------------------
Suggests 'loud_vocalisation' events from sound loudness.

This measures LOUDNESS only (dBFS with hysteresis). It cannot tell a scream
from a dropped book or a clap – which is exactly why every event is a
suggestion for a human to confirm. (The old code called this "meltdown
detection"; that claim was not justified by the method.)

  dbfs()              loudness of a block, dBFS (0 = digital full scale)
  LoudnessDetector    block-by-block state machine -> events
  LiveAudio           microphone via sounddevice (optional; degrades gracefully)
  analyse_video_audio audio track of a video via the ffmpeg binary shipped
                      with imageio-ffmpeg (no system ffmpeg needed)
"""

from __future__ import annotations

import queue
import subprocess
from typing import Optional

import numpy as np

from src.config import settings
from src.core.events import Event, merge_events

try:
    from src.utils.logger import logger
except Exception:  # pragma: no cover - logger is owned by another module
    import logging
    logger = logging.getLogger("neurosync")

SILENCE_DBFS = -120.0
HYSTERESIS_DB = 3.0


def dbfs(samples: np.ndarray) -> float:
    """RMS level in dBFS for float samples in [-1, 1] (int16 is rescaled)."""
    x = np.asarray(samples)
    if x.size == 0:
        return SILENCE_DBFS
    if x.dtype.kind in "iu":
        x = x.astype(np.float64) / np.iinfo(x.dtype).max
    rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
    return max(20 * np.log10(rms), SILENCE_DBFS) if rms > 0 else SILENCE_DBFS


class LoudnessDetector:
    """
    A loud event starts when a block is >= loud_dbfs and ends when the level
    falls below loud_dbfs - 3 dB (hysteresis, avoids flicker). Events shorter
    than loud_min_s are dropped; events closer than merge_gap_s are merged.
    Confidence: 0.5 at the threshold, 1.0 at 12 dB above it.
    """

    def __init__(self, cfg=None):
        self.cfg = cfg if cfg is not None else settings.audio
        self._start: Optional[float] = None
        self._end: Optional[float] = None
        self._levels: list[float] = []
        self._pending: list[Event] = []
        self.last_dbfs = SILENCE_DBFS

    def _close(self) -> None:
        if self._start is not None and self._end - self._start >= self.cfg.loud_min_s:
            over = float(np.mean(self._levels)) - self.cfg.loud_dbfs
            self._pending.append(Event(
                kind="loud_vocalisation", start=round(self._start, 2), end=round(self._end, 2),
                confidence=0.5 + 0.5 * min(max(over / 12.0, 0.0), 1.0), source="audio",
                evidence={"mean_dbfs": round(float(np.mean(self._levels)), 1),
                          "peak_dbfs": round(float(np.max(self._levels)), 1)}))
        self._start = self._end = None
        self._levels = []

    def _release(self, t: float, final: bool = False) -> list[Event]:
        """Return pending events once no merge partner can follow."""
        gap = self.cfg.merge_gap_s
        ongoing_close = lambda e: self._start is not None and self._start - e.end <= gap  # noqa: E731
        ready = [e for e in self._pending if final or (t - e.end > gap and not ongoing_close(e))]
        if not ready:
            return []
        self._pending = [e for e in self._pending if e not in ready]
        return merge_events(ready, self.cfg.merge_gap_s)

    def update(self, t: float, block: np.ndarray) -> list[Event]:
        """t = session time at the START of the block."""
        level = dbfs(block)
        self.last_dbfs = level
        block_s = len(block) / float(self.cfg.sample_rate) if len(block) else self.cfg.block_s
        t_end = t + block_s
        loud_on = level >= self.cfg.loud_dbfs
        loud_hold = level >= self.cfg.loud_dbfs - HYSTERESIS_DB
        if self._start is None:
            if loud_on:
                self._start, self._end, self._levels = t, t_end, [level]
        elif loud_hold:
            self._end = t_end
            self._levels.append(level)
        else:
            self._close()
        # merge consecutive pending events that are close together
        if len(self._pending) > 1:
            self._pending = merge_events(self._pending, self.cfg.merge_gap_s)
        return self._release(t_end)

    def flush(self, t: float) -> list[Event]:
        self._close()
        return self._release(t, final=True)


class LiveAudio:
    """Microphone input. `available` is False (and nothing crashes) without sounddevice/a mic."""

    def __init__(self, cfg=None):
        self.cfg = cfg if cfg is not None else settings.audio
        self.detector = LoudnessDetector(self.cfg)
        self._q: queue.Queue = queue.Queue(maxsize=200)
        self._stream = None
        self._t0: Optional[float] = None
        self._samples_seen = 0
        try:
            import sounddevice as sd
            self._sd = sd
            sd.query_devices(kind="input")
            self.available = True
        except Exception as exc:
            self._sd = None
            self.available = False
            logger.warning(f"Live audio unavailable: {exc}")

    def _callback(self, indata, frames, time_info, status):  # pragma: no cover - needs hardware
        try:
            self._q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def start(self, session_t0: float = 0.0) -> bool:
        if not self.available:
            return False
        try:
            self._t0 = session_t0
            self._samples_seen = 0
            self._stream = self._sd.InputStream(
                channels=1, samplerate=self.cfg.sample_rate, callback=self._callback,
                blocksize=int(self.cfg.sample_rate * self.cfg.block_s), dtype="float32")
            self._stream.start()
            return True
        except Exception as exc:  # pragma: no cover - needs hardware
            logger.warning(f"Could not open microphone: {exc}")
            self.available = False
            return False

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def drain(self) -> list[tuple[float, np.ndarray]]:
        """
        Raw blocks captured since the last call as (t, block), t = session_t0 + samples/rate.
        Use this to feed SessionPipeline.process_audio_block (don't mix with poll()).
        """
        out = []
        while True:
            try:
                block = self._q.get_nowait()
            except queue.Empty:
                return out
            out.append(((self._t0 or 0.0) + self._samples_seen / self.cfg.sample_rate, block))
            self._samples_seen += len(block)

    def poll(self, t: float) -> tuple[float, list[Event]]:
        """Drain queued blocks. Block times come from the sample count, not wall-clock arrival."""
        events: list[Event] = []
        while True:
            try:
                block = self._q.get_nowait()
            except queue.Empty:
                break
            t_block = (self._t0 or 0.0) + self._samples_seen / self.cfg.sample_rate
            self._samples_seen += len(block)
            events += self.detector.update(t_block, block)
        return self.detector.last_dbfs, events

    def flush(self, t: float) -> list[Event]:
        return self.detector.flush(t)


def _ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def read_audio_track(path: str, sample_rate: int) -> Optional[np.ndarray]:
    """Mono float32 samples of a video's audio track, or None if it has none."""
    cmd = [_ffmpeg_exe(), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sample_rate),
           "-f", "s16le", "-"]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        return None
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def analyse_video_audio(path: str, cfg=None) -> list[Event]:
    """Loud-sound events of a recorded video (session time = video time)."""
    cfg = cfg if cfg is not None else settings.audio
    try:
        samples = read_audio_track(path, cfg.sample_rate)
    except Exception as exc:
        logger.warning(f"Audio extraction failed for {path}: {exc}")
        return []
    if samples is None or samples.size == 0:
        logger.warning(f"No audio track in {path}; skipping sound analysis.")
        return []
    det = LoudnessDetector(cfg)
    n = max(int(cfg.sample_rate * cfg.block_s), 1)
    events: list[Event] = []
    for i in range(0, len(samples), n):
        events += det.update(i / cfg.sample_rate, samples[i:i + n])
    events += det.flush(len(samples) / cfg.sample_rate)
    return merge_events(events, cfg.merge_gap_s)
