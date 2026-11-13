"""
FastAPI backend: consent, live sessions (fake camera), video analysis, review,
save, notes, exports, stored sessions and data rights. No camera, microphone
or model files are needed: the camera, landmark extractor and microphone are fakes.
"""

import json
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.config import data_dir, settings
from src.perception.landmarks import FrameLandmarks
from src.pipeline import SessionPipeline
from src.reporting import guard
from src.reporting.reasoner import ReportGenerator
from src.storage.audit import AuditLog
from src.storage.keystore import KeyStore
from src.storage.store import SessionStore

CONSENT = {"subject_id": "S-0042", "given_by": "parent/guardian", "recorded_by": "therapist-1",
           "purpose": "Session observation notes"}


# ----------------------------------------------------------------------------- fakes
class FakeExtractor:
    """Wrists oscillate at 3 Hz between 2 s and 7 s of session time (one 'repetitive hand movement')."""

    def process(self, frame, t):
        dy = 0.06 * np.sin(2 * np.pi * 3 * t) if 2 < t < 7 else 0.0
        return FrameLandmarks(t=t, nose=(0.5, 0.3), left_ear=(0.45, 0.3), right_ear=(0.55, 0.3),
                              left_shoulder=(0.4, 0.5), right_shoulder=(0.6, 0.5),
                              left_wrist=(0.38, 0.7 + dy), right_wrist=(0.62, 0.7), face_box=None)

    def draw(self, frame, lm):
        return frame


class FakeCamera:
    """Synthetic frames with timestamps. finite: n frames as fast as possible; endless: paced until stopped."""

    def __init__(self, n_frames=330, fps=30.0, endless=False, opens=True):
        self.n, self.fps, self.endless, self.opens = n_frames, fps, endless, opens
        self.i, self.t0, self.running, self.stopped = 0, None, False, False

    def start(self):
        self.running = self.opens
        return self.opens

    def get_frame(self):
        if not self.running or (not self.endless and self.i >= self.n):
            return False, None, 0.0
        if self.t0 is None:
            self.t0 = time.time()
        if self.endless:
            time.sleep(0.005)
        frame = np.full((48, 64, 3), 90, np.uint8)
        t = self.t0 + self.i / self.fps
        self.i += 1
        return True, frame, t

    def stop(self):
        self.running = False
        self.stopped = True


class NoMic:
    available = False


class FakeMic:
    available = True

    def __init__(self):
        self.started = self.stopped = False

    def start(self, session_t0=0.0):
        self.started = True
        return True

    def poll(self, t):
        return -35.0, []

    def flush(self, t):
        return []

    def stop(self):
        self.stopped = True


# ----------------------------------------------------------------------------- fixtures
@pytest.fixture
def make_client(tmp_path):
    clients = []

    def make(camera=None, audio=None, web_dir=None):
        audit = AuditLog(root=tmp_path / "audit")
        store = SessionStore(root=tmp_path / "sessions", keystore=KeyStore(root=tmp_path / "keys"), audit=audit)
        cams = []

        def camera_factory():
            cam = camera() if callable(camera) else FakeCamera()
            cams.append(cam)
            return cam

        app = create_app(
            store=store, audit=audit,
            reporter=ReportGenerator(llm_path=tmp_path / "missing-model.gguf"),
            camera_factory=camera_factory,
            pipeline_factory=lambda s: SessionPipeline(s, extractor=FakeExtractor()),
            audio_factory=audio or NoMic,
            extractor_factory=FakeExtractor,
            web_dir=web_dir if web_dir is not None else tmp_path / "no-web",
        )
        client = TestClient(app)
        client.cameras = cams
        client.store, client.audit = store, audit
        clients.append(client)
        return client

    yield make
    for c in clients:                       # never leave a live runner thread behind
        runner = c.app.state.services.registry.live_runner
        if runner is not None and runner.running:
            runner.stop()
        c.close()


@pytest.fixture
def client(make_client):
    return make_client()


def create(client, mode="live", consent=None, confirmed=True):
    r = client.post("/api/sessions", json={"mode": mode, "consent": consent or CONSENT,
                                           "consent_confirmed": confirmed})
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def wait_state(client, sid, state="stopped", timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        s = client.get(f"/api/sessions/{sid}").json()
        if s["state"] == state:
            return s
        time.sleep(0.05)
    raise AssertionError(f"session did not reach state {state!r}")


def recorded_session(client):
    """Live session over 11 s of synthetic frames -> stopped, with pending suggestions."""
    sid = create(client)
    assert client.post(f"/api/sessions/{sid}/live/start").status_code == 200
    wait_state(client, sid)
    return sid, client.post(f"/api/sessions/{sid}/live/stop").json()


def make_video(path, seconds=10, fps=30):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (64, 48))
    for i in range(seconds * fps):
        w.write(np.full((48, 64, 3), (i * 3) % 255, np.uint8))
    w.release()
    return path


# ----------------------------------------------------------------------------- system
def test_health_and_config(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["notes_mode"] == "template"
    assert h["mic_available"] is False and h["camera_busy"] is False
    assert isinstance(h["models_present"], bool)
    c = client.get("/api/config").json()
    assert "does not diagnose" in c["disclaimer"]
    assert set(c["event_labels"]) >= {"repetitive_hand_movement", "loud_vocalisation"}
    assert c["max_duration_min"] == settings.session.max_duration_min


def test_root_without_web_points_to_docs(client):
    assert client.get("/").json()["docs"] == "/docs"
    assert client.get("/docs").status_code == 200


def test_static_web_ui_is_served(make_client, tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><body>NeuroSync UI</body></html>", encoding="utf-8")
    c = make_client(web_dir=web)
    r = c.get("/")
    assert r.status_code == 200 and "NeuroSync UI" in r.text
    assert c.get("/api/health").status_code == 200          # API still reachable next to the static UI


def test_data_info(client):
    info = client.get("/api/data/info").json()
    assert set(info) == {"data_dir", "key_path", "sessions_dir", "audit_path"}
    assert info["key_path"].endswith("neurosync.key")


# ----------------------------------------------------------------------------- consent
def test_session_requires_confirmed_consent(client):
    r = client.post("/api/sessions", json={"mode": "live", "consent": CONSENT, "consent_confirmed": False})
    assert r.status_code == 422
    missing = {k: v for k, v in CONSENT.items() if k != "given_by"}
    r = client.post("/api/sessions", json={"mode": "live", "consent": missing, "consent_confirmed": True})
    assert r.status_code == 422
    blank = {**CONSENT, "recorded_by": "   "}
    r = client.post("/api/sessions", json={"mode": "live", "consent": blank, "consent_confirmed": True})
    assert r.status_code == 422
    assert client.get("/api/sessions").json() == []


def test_name_like_subject_id_gets_warnings(client):
    r = client.post("/api/sessions", json={"mode": "live", "consent": {**CONSENT, "subject_id": "John Smith"},
                                           "consent_confirmed": True})
    assert r.status_code == 201 and r.json()["warnings"]
    r = client.post("/api/sessions", json={"mode": "live", "consent": CONSENT, "consent_confirmed": True})
    assert r.json()["warnings"] == []


def test_list_and_get_and_discard(client):
    sid = create(client)
    rows = client.get("/api/sessions").json()
    assert rows[0]["session_id"] == sid and rows[0]["state"] == "created" and rows[0]["subject_id"] == "S-0042"
    s = client.get(f"/api/sessions/{sid}").json()
    assert s["state"] == "created" and s["events"] == [] and s["consent"]["subject_id"] == "S-0042"
    assert client.get("/api/sessions/unknown123").status_code == 404
    assert client.delete(f"/api/sessions/{sid}").json() == {"discarded": True}
    assert client.get(f"/api/sessions/{sid}").status_code == 404


# ----------------------------------------------------------------------------- live
def test_live_session_produces_pending_suggestions(client):
    sid, s = recorded_session(client)
    assert s["state"] == "stopped"
    kinds = [e["kind"] for e in s["events"]]
    assert "repetitive_hand_movement" in kinds
    ev = s["events"][0]
    assert ev["status"] == "pending" and ev["label"] and "–" in ev["span"]
    assert client.cameras[0].stopped                         # camera released
    assert s["summary"]["confirmed_events"] == 0             # nothing confirmed without a reviewer


def test_live_state_while_running_and_stop(make_client):
    c = make_client(camera=lambda: FakeCamera(endless=True))
    sid = create(c)
    assert c.post(f"/api/sessions/{sid}/live/start").json() == {"state": "running"}
    time.sleep(0.3)
    st = c.get(f"/api/sessions/{sid}/live/state").json()
    expected = {"running", "elapsed_s", "max_s", "behaviour_scores", "heart_rate", "hr_reliable", "hr_snr_db",
                "baseline_hr", "baseline_measuring", "baseline_remaining_s", "loudness_dbfs", "face_visible",
                "body_visible", "suggested_events", "recent_events", "time_limit_reached", "error"}
    assert set(st) == expected
    assert st["running"] is True and st["heart_rate"] is None            # no face -> no invented heart rate
    assert st["max_s"] == settings.session.max_duration_min * 60
    assert c.get("/api/health").json()["camera_busy"] is True
    s = c.post(f"/api/sessions/{sid}/live/stop").json()
    assert s["state"] == "stopped" and c.cameras[0].stopped
    assert c.get("/api/health").json()["camera_busy"] is False


def test_only_one_live_session_at_a_time(make_client):
    c = make_client(camera=lambda: FakeCamera(endless=True))
    a, b = create(c), create(c)
    assert c.post(f"/api/sessions/{a}/live/start").status_code == 200
    r = c.post(f"/api/sessions/{b}/live/start")
    assert r.status_code == 409 and "Another live session" in r.json()["detail"]
    c.post(f"/api/sessions/{a}/live/stop")
    assert c.post(f"/api/sessions/{a}/live/start").status_code == 409     # already recorded


def test_camera_unavailable_is_409(make_client):
    c = make_client(camera=lambda: FakeCamera(opens=False))
    sid = create(c)
    r = c.post(f"/api/sessions/{sid}/live/start")
    assert r.status_code == 409 and "Camera" in r.json()["detail"]
    assert c.get(f"/api/sessions/{sid}").json()["state"] == "created"


def test_live_start_on_video_session_is_400(client):
    sid = create(client, mode="video")
    assert client.post(f"/api/sessions/{sid}/live/start").status_code == 400


def test_microphone_is_started_and_released(make_client):
    mics = []

    def mic_factory():
        m = FakeMic()
        mics.append(m)
        return m

    c = make_client(audio=mic_factory)
    assert c.get("/api/health").json()["mic_available"] is True
    sid, _ = recorded_session(c)
    live_mic = mics[-1]
    assert live_mic.started and live_mic.stopped


def test_baseline_without_reliable_heart_rate_is_not_invented(make_client, monkeypatch):
    monkeypatch.setitem(settings.session, "baseline_s", 0.2)
    c = make_client(camera=lambda: FakeCamera(endless=True))
    sid = create(c)
    c.post(f"/api/sessions/{sid}/live/start")
    r = c.post(f"/api/sessions/{sid}/live/baseline")
    assert r.status_code == 200 and r.json()["baseline_measuring"] is True
    end = time.time() + 5
    st = {}
    while time.time() < end:
        st = c.get(f"/api/sessions/{sid}/live/state").json()
        if not st["baseline_measuring"]:
            break
        time.sleep(0.05)
    assert st["baseline_measuring"] is False
    assert st["baseline_hr"] is None and "Baseline could not be measured" in st["error"]
    c.post(f"/api/sessions/{sid}/live/stop")


def test_live_websocket_pushes_state(make_client):
    c = make_client(camera=lambda: FakeCamera(endless=True))
    sid = create(c)
    c.post(f"/api/sessions/{sid}/live/start")
    with c.websocket_connect(f"/api/sessions/{sid}/live/ws") as ws:
        msg = ws.receive_json()
        assert msg["running"] is True and "behaviour_scores" in msg
    c.post(f"/api/sessions/{sid}/live/stop")


def test_mjpeg_stream(make_client):
    c = make_client(camera=lambda: FakeCamera(endless=True))
    assert c.get("/api/live/stream.mjpg").status_code == 204          # nothing running
    sid = create(c)
    c.post(f"/api/sessions/{sid}/live/start")
    with c.stream("GET", "/api/live/stream.mjpg") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("multipart/x-mixed-replace")
        chunk = next(r.iter_bytes())
        assert b"--frame" in chunk and b"image/jpeg" in chunk
        c.post(f"/api/sessions/{sid}/live/stop")


def test_review_blocked_while_running(make_client):
    c = make_client(camera=lambda: FakeCamera(endless=True))
    sid = create(c)
    c.post(f"/api/sessions/{sid}/live/start")
    r = c.post(f"/api/sessions/{sid}/events/bulk", json={"status": "confirmed", "event_ids": None})
    assert r.status_code == 409
    assert c.post(f"/api/sessions/{sid}/save").status_code == 409
    c.post(f"/api/sessions/{sid}/live/stop")


# ----------------------------------------------------------------------------- video
def test_video_upload_analysis_and_temp_file_deleted(client, tmp_path):
    video = make_video(tmp_path / "session.avi")
    sid = create(client, mode="video")
    with open(video, "rb") as f:
        r = client.post(f"/api/sessions/{sid}/video", files={"file": ("session.avi", f, "video/x-msvideo")})
    assert r.status_code == 202 and r.json() == {"state": "analysing"}
    s = wait_state(client, sid)
    status = client.get(f"/api/sessions/{sid}/video/status").json()
    assert status["error"] is None and status["progress"] == 1.0 and status["video_kept"] is False
    assert "repetitive_hand_movement" in [e["kind"] for e in s["events"]]
    assert 9 <= s["elapsed_s"] <= 11                                   # video time, not processing time
    assert list((data_dir() / "tmp").glob(f"{sid}_*")) == []           # upload deleted after analysis


def test_video_kept_only_with_consent_and_policy(client, tmp_path, monkeypatch):
    monkeypatch.setitem(settings.storage, "delete_video_after_analysis", False)
    video = make_video(tmp_path / "keep.avi", seconds=3)
    sid = create(client, mode="video", consent={**CONSENT, "video_stored": True})
    with open(video, "rb") as f:
        client.post(f"/api/sessions/{sid}/video", files={"file": ("keep.avi", f, "video/x-msvideo")})
    wait_state(client, sid)
    assert client.get(f"/api/sessions/{sid}/video/status").json()["video_kept"] is True
    client.delete(f"/api/sessions/{sid}")                              # discarding removes the kept file
    assert list((data_dir() / "tmp").glob(f"{sid}_*")) == []


def test_video_rejects_wrong_type_and_mode(client, tmp_path):
    vid = create(client, mode="video")
    r = client.post(f"/api/sessions/{vid}/video", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    live = create(client, mode="live")
    r = client.post(f"/api/sessions/{live}/video", files={"file": ("a.mp4", b"x", "video/mp4")})
    assert r.status_code == 400


# ----------------------------------------------------------------------------- review / save / notes / export
def test_review_patch_and_bulk(client):
    sid, s = recorded_session(client)
    eid = s["events"][0]["id"]
    r = client.patch(f"/api/sessions/{sid}/events/{eid}", json={"status": "confirmed", "note": "seen by me"})
    assert r.status_code == 200 and r.json()["status"] == "confirmed" and r.json()["note"] == "seen by me"
    r = client.patch(f"/api/sessions/{sid}/events/{eid}", json={"status": "confirmed"})
    assert r.json()["note"] == "seen by me"                             # note kept when not sent
    assert client.patch(f"/api/sessions/{sid}/events/nope", json={"status": "rejected"}).status_code == 404
    assert client.patch(f"/api/sessions/{sid}/events/{eid}", json={"status": "maybe"}).status_code == 422
    pending = sum(e["status"] == "pending" for e in client.get(f"/api/sessions/{sid}").json()["events"])
    r = client.post(f"/api/sessions/{sid}/events/bulk", json={"status": "rejected", "event_ids": None})
    assert r.json() == {"updated": pending}
    r = client.post(f"/api/sessions/{sid}/events/bulk", json={"status": "pending", "event_ids": [eid]})
    assert r.json() == {"updated": 1}


def _confirm_first(client, sid):
    s = client.get(f"/api/sessions/{sid}").json()
    eid = s["events"][0]["id"]
    client.patch(f"/api/sessions/{sid}/events/{eid}", json={"status": "confirmed", "note": "private note"})
    return s["events"][0]


def test_notes_are_non_diagnostic_with_disclaimer(client):
    sid, _ = recorded_session(client)
    _confirm_first(client, sid)
    for audience in ("professional", "family"):
        notes = client.post(f"/api/sessions/{sid}/notes", json={"audience": audience}).json()
        assert notes["mode"] == "template"
        assert settings.app.disclaimer in notes["text"]
        body = notes["text"].replace(settings.app.disclaimer, "")
        assert guard.check(body) == []
    assert client.post(f"/api/sessions/{sid}/notes", json={"audience": "doctor"}).status_code == 422


def test_exports_contain_confirmed_events_only(client):
    sid, s = recorded_session(client)
    first = _confirm_first(client, sid)
    pdf = client.get(f"/api/sessions/{sid}/export/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]
    csv_text = client.get(f"/api/sessions/{sid}/export/csv").text
    assert len(csv_text.strip().splitlines()) == 2 and first["label"] in csv_text      # header + 1 confirmed
    bundle = client.get(f"/api/sessions/{sid}/export/fhir").json()
    assert bundle["resourceType"] == "Bundle" and len(bundle["entry"]) == 1
    assert client.get(f"/api/sessions/{sid}/export/docx").status_code == 404


def test_save_history_and_trends_confirmed_only(client):
    sid, s = recorded_session(client)
    _confirm_first(client, sid)
    r = client.post(f"/api/sessions/{sid}/save").json()
    assert r["saved"] is True and r["path"].endswith(".enc")
    assert client.get("/api/subjects").json() == ["S-0042"]
    rows = client.get("/api/subjects/S-0042/sessions").json()
    assert rows[0]["session_id"] == sid and rows[0]["confirmed_events"] == 1
    trend = client.get("/api/subjects/S-0042/trends").json()
    assert trend[0]["confirmed_events"] == 1 and sum(trend[0][k] for k in s["summary"]["counts_by_kind"]) <= 1
    assert client.get("/api/sessions").json()[0]["saved"] is True


def test_save_before_recording_is_409(client):
    sid = create(client)
    assert client.post(f"/api/sessions/{sid}/save").status_code == 409


def test_stored_view_export_delete(client):
    sid, _ = recorded_session(client)
    _confirm_first(client, sid)
    client.post(f"/api/sessions/{sid}/save")
    client.delete(f"/api/sessions/{sid}")                              # working copy gone, stored copy stays
    stored = client.get(f"/api/stored/{sid}").json()
    assert stored["state"] == "stored" and stored["summary"]["confirmed_events"] == 1
    assert client.get(f"/api/stored/{sid}/export/csv").status_code == 200
    assert client.get(f"/api/stored/{sid}/export/pdf").content.startswith(b"%PDF")
    assert client.get("/api/stored/doesnotexist").status_code == 404
    assert client.get("/api/stored/bad-id!").status_code in (400, 404)
    assert client.delete(f"/api/stored/{sid}").json() == {"deleted": True}
    assert client.get(f"/api/stored/{sid}").status_code == 404


def test_subject_export_and_erasure_requires_confirmation(client):
    sid, _ = recorded_session(client)
    client.post(f"/api/sessions/{sid}/save")
    exp = client.get("/api/subjects/S-0042/export")
    assert exp.status_code == 200 and json.loads(exp.content)["subject_id"] == "S-0042"
    assert client.delete("/api/subjects/S-0042", params={"confirm": "S-9999"}).status_code == 400
    assert client.get("/api/subjects").json() == ["S-0042"]
    assert client.delete("/api/subjects/S-0042", params={"confirm": "S-0042"}).json() == {"deleted": 1}
    assert client.get("/api/subjects").json() == []


def test_purge_uses_retention(client, monkeypatch):
    sid, _ = recorded_session(client)
    client.post(f"/api/sessions/{sid}/save")
    assert client.post("/api/data/purge").json()["purged"] == 0
    monkeypatch.setitem(settings.storage, "retention_days", -1)        # everything is "older than" the cutoff
    assert client.post("/api/data/purge").json()["purged"] == 1


def test_audit_log_is_intact_and_has_no_free_text(client):
    sid, _ = recorded_session(client)
    _confirm_first(client, sid)
    client.post(f"/api/sessions/{sid}/notes", json={"audience": "professional"})
    client.post(f"/api/sessions/{sid}/save", headers={"X-Actor": "therapist-1"})
    entries = client.get("/api/audit").json()
    actions = [e["action"] for e in entries]
    assert {"consent_recorded", "live_start", "live_stop", "generate_notes", "save_session"} <= set(actions)
    assert any(e["actor"] == "therapist-1" for e in entries)
    assert "private note" not in json.dumps(entries)                    # reviewer notes never reach the audit log
    assert client.get("/api/audit/verify").json() == {"intact": True}
    assert len(client.get("/api/audit", params={"limit": 2}).json()) == 2
