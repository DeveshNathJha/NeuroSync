"""
Live session control: start / baseline / stop, live state (REST + WebSocket)
and the annotated camera stream (MJPEG). One live session at a time.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse

from src.api.deps import active, actor, services, subject_of
from src.api.live import CameraUnavailable, LiveRunner, wait_for_frame
from src.api.serializers import session_json
from src.api.state import Services
from src.config import settings

router = APIRouter(prefix="/api", tags=["live"])

BOUNDARY = "frame"
WS_INTERVAL_S = 0.3


def _runner_for(svc: Services, session_id: str) -> LiveRunner:
    runner = svc.registry.live_runner
    if runner is None or runner.session.id != session_id:
        raise HTTPException(409, "This session has no live recording. Start it first.")
    return runner


@router.post("/sessions/{session_id}/live/start")
def live_start(session_id: str, svc: Services = Depends(services), who: str = Depends(actor)):
    entry = active(svc, session_id)
    if entry.session.mode != "live":
        raise HTTPException(400, "This session was created for video analysis, not for a live recording.")
    if entry.session.started_at is not None:
        raise HTTPException(409, "This session has already been recorded. Create a new session.")
    if svc.registry.camera_busy:
        raise HTTPException(409, "Another live session is running. Stop it before starting a new one.")
    runner = LiveRunner(entry, svc.camera_factory, svc.pipeline_factory, svc.audio_factory,
                        baseline_s=float(settings.session.baseline_s))
    try:
        runner.start()
    except CameraUnavailable as exc:
        raise HTTPException(409, str(exc)) from None
    svc.registry.live_runner = runner
    svc.audit.log("live_start", who, subject_id=subject_of(entry), session_id=session_id)
    return {"state": "running"}


@router.post("/sessions/{session_id}/live/baseline")
def live_baseline(session_id: str, svc: Services = Depends(services)):
    runner = _runner_for(svc, session_id)
    try:
        runner.start_baseline()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"baseline_measuring": True, "baseline_s": runner.baseline_s}


@router.post("/sessions/{session_id}/live/stop")
async def live_stop(session_id: str, svc: Services = Depends(services), who: str = Depends(actor)):
    entry = active(svc, session_id)
    runner = _runner_for(svc, session_id)
    await run_in_threadpool(runner.stop)
    svc.audit.log("live_stop", who, subject_id=subject_of(entry), session_id=session_id,
                  details=f"reason={runner.end_reason} suggested={len(entry.session.events)}")
    return session_json(entry.session, entry.state)


@router.get("/sessions/{session_id}/live/state")
def live_state(session_id: str, svc: Services = Depends(services)):
    active(svc, session_id)
    return _runner_for(svc, session_id).state()


@router.websocket("/sessions/{session_id}/live/ws")
async def live_ws(websocket: WebSocket, session_id: str):
    svc: Services = websocket.app.state.services
    runner = svc.registry.live_runner
    if runner is None or runner.session.id != session_id:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    try:
        while True:
            state = runner.state()
            await websocket.send_json(state)
            if not state["running"]:
                break
            await asyncio.sleep(WS_INTERVAL_S)
    except WebSocketDisconnect:
        return
    await websocket.close()


@router.get("/live/stream.mjpg")
def live_stream(request: Request, svc: Services = Depends(services)):
    """Annotated frames of the running live session as MJPEG (kept in memory only)."""
    runner = svc.registry.live_runner
    if runner is None or not runner.running:
        return Response(status_code=204)

    def frames():
        last = 0
        while True:
            n, jpeg = wait_for_frame(runner, last)
            if jpeg is not None and n > last:
                last = n
                yield (f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n"
                       .encode("ascii") + jpeg + b"\r\n")
            if not runner.running:
                return

    return StreamingResponse(frames(), media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
                             headers={"Cache-Control": "no-store"})
