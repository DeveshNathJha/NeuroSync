"""
Active sessions: consent → create, review (confirm / reject), save, notes, exports.

A session can only be created with a confirmed consent. Notes and exports
contain CONFIRMED events only.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from src.api.deps import active, actor, services, subject_of
from src.api.serializers import event_json, session_json
from src.api.state import ActiveSession, Services
from src.config import data_dir, settings
from src.core.formatting import confirmed_csv, identifier_warnings
from src.core.session import Consent, Session
from src.reporting.fhir_export import to_fhir_bundle
from src.reporting.pdf_report import render_pdf

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

Audience = Literal["professional", "family"]


# ----------------------------------------------------------------------------- models
class ConsentIn(BaseModel):
    subject_id: str = Field(min_length=1, max_length=64, description="Pseudonymous id – never a real name")
    given_by: str = Field(min_length=1, max_length=64, description="Role of the person who consented")
    recorded_by: str = Field(min_length=1, max_length=64, description="Professional running the session")
    purpose: str = Field(default="Session observation notes", max_length=200)
    video_stored: bool = False

    @field_validator("subject_id", "given_by", "recorded_by")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


class SessionCreate(BaseModel):
    mode: Literal["live", "video"] = "live"
    consent: ConsentIn
    consent_confirmed: bool

    @field_validator("consent_confirmed")
    @classmethod
    def _must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent must be confirmed before a session can be created.")
        return v


class ReviewIn(BaseModel):
    status: Literal["confirmed", "rejected", "pending"]
    note: Optional[str] = Field(default=None, max_length=2000)


class BulkReviewIn(BaseModel):
    status: Literal["confirmed", "rejected", "pending"]
    event_ids: Optional[list[str]] = None      # None = every pending event


class NotesIn(BaseModel):
    audience: Audience = "professional"


# ----------------------------------------------------------------------------- create / read
@router.post("", status_code=201)
def create_session(body: SessionCreate, svc: Services = Depends(services), who: str = Depends(actor)):
    consent = Consent(**body.consent.model_dump())
    session = Session(consent, mode=body.mode,
                      max_duration_s=float(settings.session.max_duration_min) * 60,
                      require_consent=bool(settings.session.require_consent))
    svc.registry.add(ActiveSession(session=session))
    svc.audit.log("consent_recorded", who, subject_id=consent.subject_id, session_id=session.id,
                  details=f"mode={body.mode} video_stored={consent.video_stored}")
    return {"session_id": session.id, "warnings": identifier_warnings(consent.subject_id)}


@router.get("")
def list_sessions(svc: Services = Depends(services)):
    return [{
        "session_id": e.session.id,
        "mode": e.session.mode,
        "subject_id": subject_of(e),
        "state": e.state,
        "elapsed_s": round(e.session.elapsed(), 1),
        "saved": e.saved,
    } for e in svc.registry.all()]


@router.get("/{session_id}")
def get_session(session_id: str, svc: Services = Depends(services)):
    entry = active(svc, session_id)
    return session_json(entry.session, entry.state)


@router.delete("/{session_id}")
def discard_session(session_id: str, svc: Services = Depends(services), who: str = Depends(actor)):
    """Discard the in-memory working copy (a saved copy in the encrypted store is kept)."""
    entry = active(svc, session_id)
    runner = svc.registry.live_runner
    if runner is not None and runner.session is entry.session and runner.running:
        runner.stop()
    path = entry.video.get("path")
    if path and Path(path).exists():
        Path(path).unlink(missing_ok=True)
    svc.registry.remove(session_id)
    svc.audit.log("discard_session", who, subject_id=subject_of(entry), session_id=session_id,
                  details=f"saved={entry.saved}")
    return {"discarded": True}


# ----------------------------------------------------------------------------- review
def _require_reviewable(entry: ActiveSession) -> None:
    if entry.state in ("running", "analysing"):
        raise HTTPException(409, "The session is still running or being analysed.")


@router.patch("/{session_id}/events/{event_id}")
def review_event(session_id: str, event_id: str, body: ReviewIn, svc: Services = Depends(services)):
    entry = active(svc, session_id)
    _require_reviewable(entry)
    note = body.note
    if note is None:
        note = next((e.note for e in entry.session.events if e.id == event_id), "")
    try:
        ev = entry.session.review(event_id, body.status, note)
    except KeyError:
        raise HTTPException(404, f"No event '{event_id}' in this session.") from None
    return event_json(ev)


@router.post("/{session_id}/events/bulk")
def review_bulk(session_id: str, body: BulkReviewIn, svc: Services = Depends(services)):
    entry = active(svc, session_id)
    _require_reviewable(entry)
    if body.event_ids is None:
        targets = [e for e in entry.session.events if e.status == "pending"]
    else:
        wanted = set(body.event_ids)
        targets = [e for e in entry.session.events if e.id in wanted]
    for e in targets:
        entry.session.review(e.id, body.status, e.note)
    return {"updated": len(targets)}


# ----------------------------------------------------------------------------- save / notes / export
@router.post("/{session_id}/save")
def save_session(session_id: str, svc: Services = Depends(services), who: str = Depends(actor)):
    entry = active(svc, session_id)
    _require_reviewable(entry)
    if entry.session.started_at is None:
        raise HTTPException(409, "Nothing to save: the session was never started.")
    path = svc.store.save(entry.session, who)
    entry.saved = True
    return {"saved": True, "path": str(path)}


@router.post("/{session_id}/notes")
async def session_notes(session_id: str, body: NotesIn, svc: Services = Depends(services),
                        who: str = Depends(actor)):
    entry = active(svc, session_id)
    _require_reviewable(entry)
    report = await run_in_threadpool(svc.reporter.generate, entry.session, body.audience)
    svc.audit.log("generate_notes", who, subject_id=subject_of(entry), session_id=session_id,
                  details=f"audience={body.audience} mode={report['mode']}")
    return report


def export_response(session: Session, fmt: str, audience: str, svc: Services, who: str) -> Response:
    """Build a download for a session (active or stored). Confirmed events only."""
    sid = session.id
    subject = session.consent.subject_id if session.consent else None
    if fmt == "csv":
        body, media, ext = confirmed_csv(session.events).encode("utf-8"), "text/csv", "csv"
    elif fmt == "fhir":
        body = json.dumps(to_fhir_bundle(session), indent=2).encode("utf-8")
        media, ext = "application/fhir+json", "json"
    elif fmt == "pdf":
        report = svc.reporter.generate(session, audience)
        tmp_dir = data_dir() / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tmp_dir) as d:
            path = render_pdf(session, report, Path(d) / f"{sid}.pdf")
            body = Path(path).read_bytes()
        media, ext = "application/pdf", "pdf"
    else:
        raise HTTPException(404, "Export format must be pdf, csv or fhir.")
    svc.audit.log(f"export_{fmt}", who, subject_id=subject, session_id=sid)
    filename = f"neurosync_{subject or 'session'}_{sid}.{ext}"
    return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{session_id}/export/{fmt}")
async def export_active(session_id: str, fmt: str, audience: Audience = Query("professional"),
                        svc: Services = Depends(services), who: str = Depends(actor)):
    entry = active(svc, session_id)
    _require_reviewable(entry)
    return await run_in_threadpool(export_response, entry.session, fmt, audience, svc, who)
