"""Health, configuration and data-location endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.deps import services
from src.api.state import Services
from src.config import data_dir, resolve, settings
from src.core.events import EVENT_LABELS

router = APIRouter(prefix="/api", tags=["system"])

MODEL_FILES = ("pose_landmarker_lite.task", "face_landmarker.task")


def models_present() -> bool:
    return all((resolve("models") / name).exists() for name in MODEL_FILES)


@router.get("/health")
def health(svc: Services = Depends(services)):
    try:
        audio = svc.audio_factory()
        mic = bool(audio is not None and getattr(audio, "available", False))
    except Exception:  # noqa: BLE001
        mic = False
    return {
        "status": "ok",
        "version": settings.app.version,
        "models_present": models_present(),
        "notes_mode": svc.reporter.available_mode,
        "mic_available": mic,
        "camera_busy": svc.registry.camera_busy,
    }


@router.get("/config")
def config():
    return {
        "disclaimer": settings.app.disclaimer,
        "event_labels": EVENT_LABELS,
        "max_duration_min": settings.session.max_duration_min,
        "baseline_s": settings.session.baseline_s,
        "delete_video_after_analysis": settings.storage.delete_video_after_analysis,
        "retention_days": settings.storage.retention_days,
        "max_upload_mb": settings.storage.max_upload_mb,
        "data_dir": str(data_dir()),
    }
