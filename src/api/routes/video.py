"""
Recorded-video analysis (secondary mode): upload → background analysis → review.

The upload is written to <data_dir>/tmp and deleted after analysis unless the
consent allows storing video AND the storage policy keeps it.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from src.api.deps import active, actor, services, subject_of
from src.api.state import ActiveSession, Services
from src.config import data_dir, settings
from src.core.formatting import should_keep_video
from src.pipeline import analyse_video

try:
    from src.utils.logger import logger
except Exception:  # pragma: no cover
    import logging
    logger = logging.getLogger("neurosync")

router = APIRouter(prefix="/api/sessions", tags=["video"])

ALLOWED = {".mp4", ".mov", ".avi"}
CHUNK = 1024 * 1024


def _run_analysis(entry: ActiveSession, path: Path, svc: Services, who: str) -> None:
    session = entry.session
    keep = should_keep_video(bool(session.consent and session.consent.video_stored),
                             bool(settings.storage.delete_video_after_analysis))

    def progress(frac: float) -> None:
        entry.video["progress"] = round(float(frac), 3)

    try:
        extractor = svc.extractor_factory() if svc.extractor_factory else None
        analyse_video(str(path), session, progress=progress, extractor=extractor)
        entry.video["progress"] = 1.0
        svc.audit.log("video_analysed", who, subject_id=subject_of(entry), session_id=session.id,
                      details=f"suggested={len(session.events)} kept={keep}")
    except Exception as exc:  # noqa: BLE001 – reported to the client
        logger.exception(f"Video analysis failed: {exc}")
        entry.video["error"] = f"Video analysis failed: {exc}"
    finally:
        if not keep:
            Path(path).unlink(missing_ok=True)
            entry.video["path"] = None
        entry.video["video_kept"] = keep and Path(path).exists()
        entry.state = "stopped"


@router.post("/{session_id}/video", status_code=202)
async def upload_video(session_id: str, file: UploadFile = File(...), svc: Services = Depends(services),
                       who: str = Depends(actor)):
    entry = active(svc, session_id)
    if entry.session.mode != "video":
        raise HTTPException(400, "This session was created for a live recording, not for video analysis.")
    if entry.state != "created":
        raise HTTPException(409, "A video was already analysed for this session. Create a new session.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(415, "Unsupported file type – use .mp4, .mov or .avi.")

    tmp_dir = data_dir() / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    path = tmp_dir / f"{session_id}_{uuid.uuid4().hex[:8]}{suffix}"
    limit = int(settings.storage.max_upload_mb) * 1024 * 1024
    written = 0
    try:
        with open(path, "wb") as out:
            while chunk := await file.read(CHUNK):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(413, f"Video is larger than {settings.storage.max_upload_mb} MB.")
                out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    if written == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "The uploaded file is empty.")

    entry.state = "analysing"
    entry.video.update({"progress": 0.0, "error": None, "video_kept": False, "path": str(path)})
    threading.Thread(target=_run_analysis, args=(entry, path, svc, who), daemon=True,
                     name=f"video-{session_id}").start()
    return {"state": "analysing"}


@router.get("/{session_id}/video/status")
def video_status(session_id: str, svc: Services = Depends(services)):
    entry = active(svc, session_id)
    return {"state": entry.state, "progress": entry.video.get("progress", 0.0),
            "error": entry.video.get("error"), "video_kept": bool(entry.video.get("video_kept"))}
