"""
src/perception/landmarks.py
---------------------------
Thin wrapper around the MediaPipe Tasks API (PoseLandmarker + FaceLandmarker).

mediapipe >= 1.0 no longer ships the legacy `mp.solutions` API, so the Tasks
API is used with model files in models/ (fetch them with
`python scripts/download_models.py`). mediapipe is imported lazily, so every
other module (and the tests) work without it.

Output is a small, framework-free FrameLandmarks record with the handful of
points the behaviour and heart-rate code need, in normalised image
coordinates (0..1), plus a pixel face box for the rPPG region of interest.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from src.config import resolve

Point = tuple[float, float]

POSE_MODEL = "pose_landmarker_lite.task"
FACE_MODEL = "face_landmarker.task"

# MediaPipe landmark indices
_POSE_L_SHOULDER, _POSE_R_SHOULDER = 11, 12
_POSE_L_WRIST, _POSE_R_WRIST = 15, 16
_FACE_NOSE_TIP, _FACE_LEFT, _FACE_RIGHT = 1, 234, 454


@dataclass
class FrameLandmarks:
    t: float
    nose: Optional[Point] = None
    left_ear: Optional[Point] = None
    right_ear: Optional[Point] = None
    left_wrist: Optional[Point] = None
    right_wrist: Optional[Point] = None
    left_shoulder: Optional[Point] = None
    right_shoulder: Optional[Point] = None
    face_box: Optional[tuple[int, int, int, int]] = None   # pixel x, y, w, h

    @property
    def has_face(self) -> bool:
        return self.nose is not None and self.left_ear is not None and self.right_ear is not None

    @property
    def has_pose(self) -> bool:
        return None not in (self.left_wrist, self.right_wrist, self.left_shoulder, self.right_shoulder)


class ModelFilesMissing(FileNotFoundError):
    pass


class LandmarkExtractor:
    """Runs pose + face landmark detection on BGR frames (VIDEO running mode)."""

    def __init__(self, models_dir: str | Path | None = None):
        models_dir = Path(models_dir) if models_dir is not None else resolve("models")
        pose_path, face_path = models_dir / POSE_MODEL, models_dir / FACE_MODEL
        missing = [p.name for p in (pose_path, face_path) if not p.exists()]
        if missing:
            raise ModelFilesMissing(
                f"MediaPipe model files missing in {models_dir}: {', '.join(missing)}. "
                "Run: python scripts/download_models.py"
            )

        import mediapipe as mp  # lazy: heavy import
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision

        self._mp = mp
        mode = vision.RunningMode.VIDEO
        self._pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(pose_path)),
            running_mode=mode, num_poses=1))
        self._face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(face_path)),
            running_mode=mode, num_faces=1))
        self._last_ms = -1

    def _timestamp_ms(self, t: float) -> int:
        """MediaPipe VIDEO mode requires strictly increasing integer timestamps."""
        ms = int(round(t * 1000))
        if ms <= self._last_ms:
            ms = self._last_ms + 1
        self._last_ms = ms
        return ms

    def process(self, frame_bgr: np.ndarray, t: float) -> FrameLandmarks:
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        ms = self._timestamp_ms(t)
        lm = FrameLandmarks(t=t)

        pose = self._pose.detect_for_video(image, ms)
        if pose.pose_landmarks:
            p = pose.pose_landmarks[0]
            lm.left_shoulder = (p[_POSE_L_SHOULDER].x, p[_POSE_L_SHOULDER].y)
            lm.right_shoulder = (p[_POSE_R_SHOULDER].x, p[_POSE_R_SHOULDER].y)
            lm.left_wrist = (p[_POSE_L_WRIST].x, p[_POSE_L_WRIST].y)
            lm.right_wrist = (p[_POSE_R_WRIST].x, p[_POSE_R_WRIST].y)

        face = self._face.detect_for_video(image, ms)
        if face.face_landmarks:
            f = face.face_landmarks[0]
            lm.nose = (f[_FACE_NOSE_TIP].x, f[_FACE_NOSE_TIP].y)
            lm.left_ear = (f[_FACE_LEFT].x, f[_FACE_LEFT].y)
            lm.right_ear = (f[_FACE_RIGHT].x, f[_FACE_RIGHT].y)
            xs = np.clip([pt.x for pt in f], 0, 1) * w
            ys = np.clip([pt.y for pt in f], 0, 1) * h
            x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
            if x1 - x0 > 4 and y1 - y0 > 4:
                lm.face_box = (x0, y0, x1 - x0, y1 - y0)
        return lm

    @staticmethod
    def draw(frame_bgr: np.ndarray, lm: FrameLandmarks) -> np.ndarray:
        """Overlay the tracked points (no identity information is drawn)."""
        out = frame_bgr.copy()
        h, w = out.shape[:2]

        def px(p: Point) -> tuple[int, int]:
            return int(p[0] * w), int(p[1] * h)

        for name in ("left_wrist", "right_wrist", "left_shoulder", "right_shoulder"):
            p = getattr(lm, name)
            if p is not None:
                cv2.circle(out, px(p), 6, (0, 200, 0), -1)
        if lm.has_pose:
            cv2.line(out, px(lm.left_shoulder), px(lm.right_shoulder), (0, 200, 0), 2)
            cv2.line(out, px(lm.left_shoulder), px(lm.left_wrist), (0, 160, 0), 1)
            cv2.line(out, px(lm.right_shoulder), px(lm.right_wrist), (0, 160, 0), 1)
        if lm.face_box is not None:
            x, y, bw, bh = lm.face_box
            cv2.rectangle(out, (x, y), (x + bw, y + bh), (255, 160, 0), 1)
        if lm.nose is not None:
            cv2.circle(out, px(lm.nose), 4, (0, 0, 255), -1)
        return out

    def close(self) -> None:
        for task in (getattr(self, "_pose", None), getattr(self, "_face", None)):
            if task is not None:
                task.close()
