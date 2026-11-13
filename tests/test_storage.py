"""Tests for the key store and the encrypted session store."""

import json

import pytest

from src.config import PROJECT_ROOT
from src.core.events import Event
from src.core.session import Consent, Session
from src.storage.audit import AuditLog
from src.storage.keystore import KeyStore, KeyStoreError
from src.storage.store import SessionStore, StoreError


def make_session(subject="S-01", started=None, confirm=True):
    s = Session(Consent(subject_id=subject, given_by="parent/guardian", recorded_by="therapist"))
    s.start()
    if started is not None:
        s.started_at = started
    hand = Event(kind="repetitive_hand_movement", start=1, end=4, confidence=0.9, source="vision")
    loud = Event(kind="loud_vocalisation", start=6, end=7, confidence=0.7, source="audio")
    s.add_events([hand, loud])
    if confirm:
        s.review(hand.id, "confirmed")
    s.review(loud.id, "rejected")
    s.heart_rate = [(1.0, 90.0, 8.0), (2.0, 94.0, 7.0)]
    s.stop()
    return s


@pytest.fixture
def store(tmp_path):
    return SessionStore(root=tmp_path / "sessions", keystore=KeyStore(tmp_path / "keys"),
                        audit=AuditLog(tmp_path))


# ----------------------------------------------------------------- key store
def test_key_created_once_outside_project(tmp_path):
    ks = KeyStore(tmp_path / "keys")
    k1 = ks.get_key()
    assert ks.path.exists() and ks.get_key() == k1
    assert not str(ks.path.resolve()).startswith(str(PROJECT_ROOT))


def test_key_refused_inside_project():
    with pytest.raises(KeyStoreError):
        KeyStore(PROJECT_ROOT / "config")


# ----------------------------------------------------------------- store
def test_save_load_roundtrip_and_files_are_encrypted(store):
    s = make_session()
    path = store.save(s, actor="therapist")
    raw = path.read_bytes()
    assert b"S-01" not in raw and b"repetitive" not in raw
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    assert b"S-01" not in (store.root / "index.enc").read_bytes()
    loaded = store.load(s.id, actor="therapist")
    assert loaded.to_dict() == s.to_dict()


def test_wrong_key_cannot_read(store, tmp_path):
    s = make_session()
    store.save(s, actor="t")
    other = SessionStore(root=store.root, keystore=KeyStore(tmp_path / "other-keys"), audit=store.audit)
    with pytest.raises(StoreError):
        other.load(s.id, actor="t")


def test_list_subjects_and_trends_confirmed_only(store):
    a = make_session("S-01", started=1000.0)
    b = make_session("S-01", started=2000.0, confirm=False)
    c = make_session("S-02", started=1500.0)
    for s in (a, b, c):
        store.save(s, actor="t")
    assert store.subjects() == ["S-01", "S-02"]
    rows = store.list_sessions("S-01")
    assert [r["session_id"] for r in rows] == [b.id, a.id]  # newest first
    trends = store.trends("S-01")
    assert [t["session_id"] for t in trends] == [a.id, b.id]  # chronological
    assert trends[0]["repetitive_hand_movement"] == 1 and trends[0]["loud_vocalisation"] == 0
    assert trends[1]["confirmed_events"] == 0
    assert trends[0]["mean_heart_rate"] == 92.0


def test_delete_session_and_subject(store):
    a, b, c = make_session("S-01"), make_session("S-01"), make_session("S-02")
    for s in (a, b, c):
        store.save(s, actor="t")
    assert store.delete_session(a.id, actor="t") is True
    assert store.delete_session(a.id, actor="t") is False
    assert store.delete_subject("S-01", actor="t") == 1
    assert not (store.root / f"{b.id}.enc").exists()
    assert store.subjects() == ["S-02"]
    assert [r["session_id"] for r in store.list_sessions()] == [c.id]
    with pytest.raises(KeyError):
        store.load(b.id, actor="t")


def test_export_subject(store):
    a = make_session("S-01")
    store.save(a, actor="t")
    store.save(make_session("S-02"), actor="t")
    data = json.loads(store.export_subject("S-01", actor="family"))
    assert data["subject_id"] == "S-01"
    assert [s["id"] for s in data["sessions"]] == [a.id]


def test_purge_older_than(store):
    old = make_session(started=1_000.0)
    new = make_session(started=1_000_000.0)
    store.save(old, actor="t")
    store.save(new, actor="t")
    assert store.purge_older_than(days=1, actor="t", now=1_000_000.0 + 3600) == 1
    assert [r["session_id"] for r in store.list_sessions()] == [new.id]


def test_rotate_key_keeps_data_readable(store):
    s = make_session()
    store.save(s, actor="t")
    old_key = store.keystore.get_key()
    assert store.rotate_key(actor="admin") == 2  # session + index
    assert store.keystore.get_key() != old_key
    assert store.load(s.id, actor="t").id == s.id


def test_store_actions_are_audited(store):
    s = make_session()
    store.save(s, actor="therapist")
    store.load(s.id, actor="therapist")
    store.export_subject("S-01", actor="family")
    store.delete_subject("S-01", actor="admin")
    actions = [e["action"] for e in store.audit.read()]
    assert actions == ["delete_subject", "export_subject", "view_session", "save_session"]
    assert store.audit.verify()


def test_invalid_session_id_rejected(store):
    with pytest.raises(StoreError):
        store.load("../secret", actor="t")
