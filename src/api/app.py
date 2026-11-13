"""
src/api/app.py
--------------
FastAPI application: a local REST + WebSocket API for NeuroSync, which also
serves the static web UI from web/ (if present). Any other front-end, such as
a React or mobile app, can use the same API; OpenAPI docs are at /docs.

    python -m src.api            # http://127.0.0.1:8000

The server binds to 127.0.0.1 by default (settings.api.host): session data and
the live camera stream are only reachable from this computer.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import data as data_routes
from src.api.routes import live as live_routes
from src.api.routes import sessions as session_routes
from src.api.routes import system as system_routes
from src.api.routes import video as video_routes
from src.api.state import Services
from src.config import PROJECT_ROOT, settings
from src.core.session import SessionError
from src.storage.keystore import KeyStoreError
from src.storage.store import StoreError

WEB_DIR = PROJECT_ROOT / "web"


def _default_camera():
    from src.sensors.camera import CameraSensor
    v = settings.video
    return CameraSensor(int(v.camera_index), width=int(v.width), height=int(v.height))


def _default_pipeline(session):
    from src.pipeline import SessionPipeline
    return SessionPipeline(session)


def _default_audio():
    from src.perception.audio import LiveAudio
    return LiveAudio()


def create_app(store=None, audit=None, reporter=None, camera_factory=None, pipeline_factory=None,
               audio_factory=None, extractor_factory=None, web_dir=None) -> FastAPI:
    """Build the app. Every dependency can be injected (tests use fakes: no camera, mic or models)."""
    from src.reporting.reasoner import ReportGenerator
    from src.storage.audit import AuditLog
    from src.storage.store import SessionStore

    audit = audit if audit is not None else AuditLog()
    store = store if store is not None else SessionStore(audit=audit)
    services = Services(
        store=store,
        audit=audit,
        reporter=reporter if reporter is not None else ReportGenerator(),
        camera_factory=camera_factory or _default_camera,
        pipeline_factory=pipeline_factory or _default_pipeline,
        audio_factory=audio_factory or _default_audio,
        extractor_factory=extractor_factory,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        runner = services.registry.live_runner   # never leave the camera or microphone open
        if runner is not None and runner.running:
            runner.stop()

    app = FastAPI(
        lifespan=lifespan,
        title="NeuroSync API",
        version=str(settings.app.version),
        description=("Local API of NeuroSync, a privacy-first, non-diagnostic session-observation assistant. "
                     + str(settings.app.disclaimer)),
    )
    app.state.services = services

    origins = list(settings.api.get("cors_origins") or [])
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(StoreError)
    async def _store_error(request: Request, exc: StoreError):
        status = 400 if "invalid session id" in str(exc) else 500
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    @app.exception_handler(KeyStoreError)
    async def _key_error(request: Request, exc: KeyStoreError):
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(SessionError)
    async def _session_error(request: Request, exc: SessionError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    for module in (system_routes, session_routes, live_routes, video_routes, data_routes):
        app.include_router(module.router)

    web = WEB_DIR if web_dir is None else web_dir
    if web is not None and (web / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(web), html=True), name="web")
    else:
        @app.get("/", include_in_schema=False)
        def _root():
            return {"name": "NeuroSync API", "docs": "/docs", "ui": "web/ folder not found"}

    return app


def get_app() -> FastAPI:
    """Factory for `uvicorn --factory src.api.app:get_app`."""
    return create_app()


app: Optional[FastAPI] = None   # created lazily by __main__ / get_app (avoids side effects on import)
