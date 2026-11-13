"""
src/sensors/camera.py
---------------------
One interface for a webcam and a recorded video file.

get_frame() returns (ok, frame_bgr, t) where t is a timestamp in seconds:
  - webcam: wall-clock time (time.time()) at capture
  - video file: position in the video (CAP_PROP_POS_MSEC), so offline
    analysis uses the video's own timeline, not processing speed
"""

from __future__ import annotations

import time
from typing import Optional, Union

import cv2
import numpy as np

try:
    from src.utils.logger import logger
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger("neurosync")


class CameraSensor:
    def __init__(self, source: Union[int, str] = 0, width: Optional[int] = None, height: Optional[int] = None):
        self.source = source
        self.is_file = not isinstance(source, int)
        self.width, self.height = width, height
        self.cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.fps = 0.0
        self.frame_count = 0
        self._frames_read = 0

    def start(self) -> bool:
        self.stop()
        try:
            self.cap = cv2.VideoCapture(self.source)
            if not self.cap.isOpened():
                raise RuntimeError(f"could not open video source {self.source!r}")
            if not self.is_file:
                if self.width:
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                if self.height:
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
            self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) if self.is_file else 0
            self._frames_read = 0
            self.running = True
            logger.info(f"Video source opened: {self.source!r} ({self.fps:.1f} fps)")
            return True
        except Exception as exc:
            logger.error(f"Camera error: {exc}")
            self.stop()
            return False

    def get_frame(self) -> tuple[bool, Optional[np.ndarray], float]:
        if not self.running or self.cap is None:
            return False, None, 0.0
        ok, frame = self.cap.read()
        if not ok or frame is None:
            self.stop()
            return False, None, 0.0
        self._frames_read += 1
        if self.is_file:
            t = float(self.cap.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
            if t <= 0 and self.fps > 0:            # some containers don't report position
                t = (self._frames_read - 1) / self.fps
        else:
            t = time.time()
        return True, frame, t

    def progress(self) -> float:
        """Fraction of a video file read so far (0 for a webcam)."""
        if not self.is_file or self.frame_count <= 0:
            return 0.0
        return min(self._frames_read / self.frame_count, 1.0)

    def stop(self) -> None:
        self.running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
