"""
src/pipeline.py
---------------
Wires the perception modules to a Session.

Live (main mode):
    pipe = SessionPipeline(session)            # session.start() first
    annotated, state = pipe.process_frame(frame, t_abs)   # t_abs = capture time.time()
    # microphone: EITHER let LiveAudio detect loud sounds itself (what the UI does) …
    dbfs, audio_events = live_audio.poll(session.elapsed())
    pipe.add_external_events(audio_events)
    # … OR feed raw blocks here (don't do both, or loud sounds are counted twice):
    #   for t, block in live_audio.drain(): pipe.process_audio_block(block, t)
    events = pipe.finish()                     # at session end -> suggestions for review

Recorded video (secondary mode):
    analyse_video(path, session, progress=callback)

Every produced event has status "pending"; only a human reviewer confirms it.
No simulated data is ever injected.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

import numpy as np

from src.analysis.fusion import link_co_occurring
from src.config import settings as default_settings
from src.core.events import Event
from src.core.session import Session
from src.perception.audio import LoudnessDetector, analyse_video_audio
from src.perception.behaviour import BehaviourDetector
from src.perception.landmarks import FrameLandmarks
from src.perception.rppg import HeartRateMonitor, HRReading, RPPGEstimator, estimate_baseline


class SessionPipeline:
    def __init__(self, session: Session, cfg=None, extractor=None, audio=None):
        self.session = session
        self.cfg = cfg if cfg is not None else default_settings
        self._extractor = extractor                     # lazily created (MediaPipe is heavy)
        self.behaviour = BehaviourDetector(self.cfg.behaviour, fps=self.cfg.video.target_fps)
        self.rppg = RPPGEstimator(self.cfg.rppg)
        self.hr_monitor = HeartRateMonitor(self.cfg.rppg)
        self.audio = audio if audio is not None else LoudnessDetector(self.cfg.audio)
        self.hr_readings: list[HRReading] = []
        self._events: list[Event] = []
        self._last_reading: Optional[HRReading] = None
        self._last_t = 0.0
        self._finished = False
        if session.baseline_hr:
            self.hr_monitor.set_baseline(session.baseline_hr)

    # ------------------------------------------------------------------ helpers
    @property
    def extractor(self):
        if self._extractor is None:
            from src.perception.landmarks import LandmarkExtractor
            self._extractor = LandmarkExtractor()
        return self._extractor

    def _session_t(self, t_abs: float) -> float:
        if self.session.started_at is None:
            raise RuntimeError("start the session before processing data")
        return max(0.0, t_abs - self.session.started_at)

    def set_baseline_hr(self, bpm: Optional[float]) -> None:
        self.hr_monitor.set_baseline(bpm)
        self.session.baseline_hr = float(bpm) if bpm else None

    def baseline_from_readings(self) -> Optional[float]:
        """Median of the reliable heart-rate readings seen so far (for calibration)."""
        return estimate_baseline(self.hr_readings)

    def add_external_events(self, events: list[Event]) -> None:
        self._events.extend(events)

    # ------------------------------------------------------------------ live
    def process_frame(self, frame_bgr: np.ndarray, t_abs: float) -> tuple[np.ndarray, dict]:
        t = self._session_t(t_abs)
        self._last_t = max(self._last_t, t)
        lm: FrameLandmarks = self.extractor.process(frame_bgr, t)
        new = self.behaviour.update(lm)

        reading = self.rppg.update(t, frame_bgr, lm.face_box)
        if reading is not None:
            self._last_reading = reading
            self.hr_readings.append(reading)
            if reading.reliable:
                self.session.heart_rate.append((reading.t, reading.bpm, reading.snr_db))
            new += self.hr_monitor.update(reading)
        self._events.extend(new)

        draw = getattr(self.extractor, "draw", None)
        annotated = draw(frame_bgr, lm) if callable(draw) else frame_bgr
        last = self._last_reading
        state = {
            "t": round(t, 2),
            "behaviour_scores": self.behaviour.live_state(),
            "heart_rate": last.bpm if last is not None and last.reliable else None,
            "hr_reliable": bool(last.reliable) if last is not None else False,
            "hr_snr_db": last.snr_db if last is not None else None,
            "loudness_dbfs": getattr(self.audio, "last_dbfs", None),
            "face_visible": lm.has_face,
            "body_visible": lm.has_pose,
            "new_events": new,
            "time_limit_reached": self.session.check_time_limit(),
        }
        return annotated, state

    def process_audio_block(self, block: np.ndarray, t_abs: float) -> list[Event]:
        t = self._session_t(t_abs)
        self._last_t = max(self._last_t, t)
        new = self.audio.update(t, block)
        self._events.extend(new)
        return new

    def finish(self) -> list[Event]:
        """Close all detectors, link co-occurring events and hand them to the session (once)."""
        if self._finished:
            return self.session.events
        self._finished = True
        t_end = max(self._last_t, self.session.elapsed() if self.session.started_at is not None else 0.0)
        events = self._events
        events += self.behaviour.flush(t_end)
        events += self.hr_monitor.flush()
        events += self.audio.flush(t_end)
        link_co_occurring(events, self.cfg.fusion.co_occurrence_window_s)
        self.session.add_events(events)          # each detector already merged its own events
        self._events = []
        return self.session.events


def analyse_video(path: str, session: Session, cfg=None, progress: Optional[Callable[[float], None]] = None,
                  analysis_fps: float = 15.0, extractor=None) -> Session:
    """
    Analyse a recorded session video. Session time = video time.

    Frames are analysed at `analysis_fps` (default 15: enough for the 2–6 Hz
    movement band and for heart rate up to 180 BPM, and twice as fast as 30).
    """
    from src.sensors.camera import CameraSensor

    cfg = cfg if cfg is not None else default_settings
    cam = CameraSensor(path)
    if not cam.start():
        raise RuntimeError(f"Could not open video: {path}")
    if session.started_at is None:
        session.start()
    base = session.started_at
    pipe = SessionPipeline(session, cfg, extractor=extractor)
    pipe.add_external_events(analyse_video_audio(path, cfg.audio))

    step = 1.0 / analysis_fps if analysis_fps else 0.0
    next_t, last_vt, n = 0.0, 0.0, 0
    try:
        while True:
            ok, frame, vt = cam.get_frame()
            if not ok:
                break
            last_vt = vt
            if vt + 1e-6 < next_t:
                continue
            next_t = vt + step
            pipe.process_frame(frame, base + vt)
            n += 1
            if progress is not None and n % 15 == 0:
                progress(cam.progress())
    finally:
        cam.stop()
    pipe._last_t = max(pipe._last_t, last_vt)
    session.ended_at = base + last_vt            # video timeline, not processing time
    pipe.finish()
    if progress is not None:
        progress(1.0)
    return session
