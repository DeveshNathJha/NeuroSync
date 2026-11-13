"""
src/api/live.py
---------------
LiveRunner: runs ONE live session in a background thread.

It owns the camera, the SessionPipeline and the microphone for the duration
of the session, keeps the latest annotated frame (as JPEG bytes, in memory
only – frames are never written to disk) and the latest live state for the
API, measures a resting heart-rate baseline on request, and stops by itself
at the session's maximum duration. Camera and microphone are always released
in `finally`.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

import cv2

from src.api.serializers import event_json
from src.api.state import ActiveSession
from src.perception.rppg import estimate_baseline

try:
    from src.utils.logger import logger
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger("neurosync")


class CameraUnavailable(RuntimeError):
    pass


class LiveRunner:
    def __init__(self, entry: ActiveSession, camera_factory, pipeline_factory, audio_factory,
                 baseline_s: float = 60.0, jpeg_quality: int = 75):
        self.entry = entry
        self.session = entry.session
        self._camera_factory = camera_factory
        self._pipeline_factory = pipeline_factory
        self._audio_factory = audio_factory
        self.baseline_s = baseline_s
        self.jpeg_quality = jpeg_quality

        self.pipeline = None
        self._camera = None
        self._audio = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._done = threading.Event()
        self._lock = threading.Lock()

        self._jpeg: Optional[bytes] = None
        self._frame_no = 0
        self._live: dict[str, Any] = {}
        self._recent: list = []
        self._suggested = 0
        self._baseline_from: Optional[float] = None
        self._baseline_until: Optional[float] = None
        self.error: Optional[str] = None
        self.end_reason: Optional[str] = None

    # ------------------------------------------------------------------ control
    @property
    def running(self) -> bool:
        return self._thread is not None and not self._done.is_set()

    def start(self) -> None:
        camera = self._camera_factory()
        if not camera.start():
            raise CameraUnavailable("Camera could not be opened. Check that it is connected "
                                    "and not used by another application.")
        self._camera = camera
        self.session.start()
        self.pipeline = self._pipeline_factory(self.session)
        self._audio = self._start_audio()
        self.entry.state = "running"
        self._thread = threading.Thread(target=self._run, name=f"live-{self.session.id}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self._done.wait(timeout)

    def start_baseline(self) -> None:
        if not self.running:
            raise RuntimeError("baseline can only be measured during a running live session")
        now = self.session.elapsed()
        with self._lock:
            self._baseline_from, self._baseline_until = now, now + self.baseline_s

    # ------------------------------------------------------------------ outputs
    def jpeg(self) -> tuple[int, Optional[bytes]]:
        with self._lock:
            return self._frame_no, self._jpeg

    def state(self) -> dict[str, Any]:
        with self._lock:
            live = dict(self._live)
            recent = list(self._recent[-10:])
            suggested = self._suggested
            measuring = self._baseline_until is not None
            remaining = max(0.0, self._baseline_until - self.session.elapsed()) if measuring else 0.0
        return {
            "running": self.running,
            "elapsed_s": round(self.session.elapsed(), 1),
            "max_s": self.session.max_duration_s,
            "behaviour_scores": live.get("behaviour_scores", {}),
            "heart_rate": live.get("heart_rate"),
            "hr_reliable": bool(live.get("hr_reliable", False)),
            "hr_snr_db": live.get("hr_snr_db"),
            "baseline_hr": self.session.baseline_hr,
            "baseline_measuring": measuring,
            "baseline_remaining_s": round(remaining, 1),
            "loudness_dbfs": live.get("loudness_dbfs"),
            "face_visible": bool(live.get("face_visible", False)),
            "body_visible": bool(live.get("body_visible", False)),
            "suggested_events": suggested,
            "recent_events": [event_json(e) for e in recent],
            "time_limit_reached": self.end_reason == "time_limit" or bool(live.get("time_limit_reached")),
            "error": self.error,
        }

    # ------------------------------------------------------------------ loop
    def _start_audio(self):
        try:
            audio = self._audio_factory()
        except Exception as exc:  # noqa: BLE001 – a missing mic must never stop a session
            logger.warning(f"Microphone unavailable: {exc}")
            return None
        if audio is None or not getattr(audio, "available", False):
            return None
        try:
            return audio if audio.start(session_t0=self.session.elapsed()) else None
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Microphone could not start: {exc}")
            return None

    def _poll_audio(self) -> tuple[Optional[float], list]:
        if self._audio is None:
            return None, []
        try:
            dbfs, events = self._audio.poll(self.session.elapsed())
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Microphone read failed: {exc}")
            return None, []
        if events:
            self.pipeline.add_external_events(events)
        return dbfs, events

    def _encode(self, frame) -> Optional[bytes]:
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        return buf.tobytes() if ok else None

    def _check_baseline(self) -> None:
        with self._lock:
            until, start = self._baseline_until, self._baseline_from
        if until is None or self.session.elapsed() < until:
            return
        readings = [r for r in getattr(self.pipeline, "hr_readings", []) if r.t >= start]
        bpm = estimate_baseline(readings)
        if bpm:
            self.pipeline.set_baseline_hr(bpm)
        else:
            self.error = "Baseline could not be measured (no reliable heart-rate readings – check lighting)."
        with self._lock:
            self._baseline_from = self._baseline_until = None

    def _run(self) -> None:
        try:
            while not self._stop.is_set() and self.session.running:
                ok, frame, t = self._camera.get_frame()
                if not ok:
                    self.end_reason = "camera_ended"
                    break
                dbfs, audio_events = self._poll_audio()
                annotated, live = self.pipeline.process_frame(frame, t)
                if dbfs is not None:
                    live["loudness_dbfs"] = dbfs
                new = list(live.get("new_events") or []) + list(audio_events)
                jpeg = self._encode(annotated)
                with self._lock:
                    self._live = live
                    if jpeg is not None:
                        self._jpeg = jpeg
                        self._frame_no += 1
                    self._recent.extend(new)
                    self._suggested += len(new)
                self._check_baseline()
                if live.get("time_limit_reached"):
                    self.end_reason = "time_limit"
                    break
            else:
                self.end_reason = self.end_reason or ("stopped" if self._stop.is_set() else "time_limit")
        except Exception as exc:  # noqa: BLE001 – report, never leave the camera open
            logger.exception(f"Live session failed: {exc}")
            self.error = f"Live session stopped after an error: {exc}"
            self.end_reason = "error"
        finally:
            self._shutdown()

    def _shutdown(self) -> None:
        try:
            if self._camera is not None:
                self._camera.stop()
        finally:
            if self._audio is not None:
                try:
                    self.pipeline.add_external_events(self._audio.flush(self.session.elapsed()))
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self._audio.stop()
                except Exception:  # noqa: BLE001
                    pass
            if self.session.running:
                self.session.stop()
            try:
                if self.pipeline is not None:
                    self.pipeline.finish()
            finally:
                self.entry.state = "stopped"
                self._done.set()
                logger.info(f"Live session {self.session.id} ended ({self.end_reason}).")


def wait_for_frame(runner: LiveRunner, after: int, timeout: float = 2.0) -> tuple[int, Optional[bytes]]:
    """Block until a frame newer than `after` exists (or timeout / runner stopped)."""
    end = time.time() + timeout
    while time.time() < end:
        n, jpeg = runner.jpeg()
        if jpeg is not None and n > after:
            return n, jpeg
        if not runner.running:
            return n, jpeg
        time.sleep(0.02)
    return runner.jpeg()
