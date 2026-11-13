"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Request

from src.api.state import ActiveSession, Services


def services(request: Request) -> Services:
    return request.app.state.services


def actor(x_actor: Optional[str] = Header(default=None)) -> str:
    """Who performs the action (written to the audit log). Ids/roles only, never free text."""
    value = (x_actor or "").strip()[:64]
    return value or "local-user"


def active(svc: Services, session_id: str) -> ActiveSession:
    try:
        return svc.registry.get(session_id)
    except KeyError:
        raise HTTPException(404, f"No active session '{session_id}'.") from None


def subject_of(entry: ActiveSession) -> Optional[str]:
    c = entry.session.consent
    return c.subject_id if c else None
