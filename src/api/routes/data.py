"""
Stored (saved, encrypted) sessions, subjects, history trends and data rights:
view, export, delete a session, erase a subject, retention purge, audit log.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from src.api.deps import actor, services
from src.api.routes.sessions import Audience, export_response
from src.api.serializers import session_json
from src.api.state import Services
from src.config import data_dir, settings

router = APIRouter(prefix="/api", tags=["data"])


def _load(svc: Services, session_id: str, who: str):
    try:
        return svc.store.load(session_id, who)
    except KeyError:
        raise HTTPException(404, f"No stored session '{session_id}'.") from None


# ----------------------------------------------------------------------------- subjects / history
@router.get("/subjects")
def subjects(svc: Services = Depends(services)):
    return svc.store.subjects()


@router.get("/subjects/{subject_id}/sessions")
def subject_sessions(subject_id: str, svc: Services = Depends(services)):
    return svc.store.list_sessions(subject_id)


@router.get("/subjects/{subject_id}/trends")
def subject_trends(subject_id: str, svc: Services = Depends(services)):
    return svc.store.trends(subject_id)


@router.get("/subjects/{subject_id}/export")
def subject_export(subject_id: str, svc: Services = Depends(services), who: str = Depends(actor)):
    data = svc.store.export_subject(subject_id, who)
    return Response(data, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="neurosync_{subject_id}_export.json"'})


@router.delete("/subjects/{subject_id}")
def subject_delete(subject_id: str, confirm: str = Query(..., description="Repeat the subject id"),
                   svc: Services = Depends(services), who: str = Depends(actor)):
    if confirm != subject_id:
        raise HTTPException(400, "Confirmation does not match the subject id; nothing was deleted.")
    return {"deleted": svc.store.delete_subject(subject_id, who)}


# ----------------------------------------------------------------------------- stored sessions
@router.get("/stored/{session_id}")
def stored_get(session_id: str, svc: Services = Depends(services), who: str = Depends(actor)):
    return session_json(_load(svc, session_id, who), "stored")


@router.get("/stored/{session_id}/export/{fmt}")
async def stored_export(session_id: str, fmt: str, audience: Audience = Query("professional"),
                        svc: Services = Depends(services), who: str = Depends(actor)):
    session = _load(svc, session_id, who)
    return await run_in_threadpool(export_response, session, fmt, audience, svc, who)


@router.delete("/stored/{session_id}")
def stored_delete(session_id: str, svc: Services = Depends(services), who: str = Depends(actor)):
    return {"deleted": svc.store.delete_session(session_id, who)}


# ----------------------------------------------------------------------------- retention / audit / info
@router.post("/data/purge")
def purge(svc: Services = Depends(services), who: str = Depends(actor)):
    return {"purged": svc.store.purge_older_than(float(settings.storage.retention_days), who),
            "retention_days": settings.storage.retention_days}


@router.get("/audit")
def audit(limit: int = Query(200, ge=1, le=5000), svc: Services = Depends(services)):
    return svc.audit.read(limit)


@router.get("/audit/verify")
def audit_verify(svc: Services = Depends(services)):
    return {"intact": svc.audit.verify()}


@router.get("/data/info")
def data_info(svc: Services = Depends(services)):
    keystore = getattr(svc.store, "keystore", None)
    return {
        "data_dir": str(data_dir()),
        "key_path": str(keystore.path) if keystore is not None else None,
        "sessions_dir": str(svc.store.root),
        "audit_path": str(svc.audit.path),
    }
