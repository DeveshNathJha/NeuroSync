"""Tests for the tamper-evident audit log."""

import json

from src.storage.audit import AuditLog


def test_log_read_newest_first_and_verify(tmp_path):
    log = AuditLog(tmp_path)
    log.log("save_session", "therapist", subject_id="S-01", session_id="abc")
    log.log("view_session", "therapist", session_id="abc")
    entries = log.read()
    assert [e["action"] for e in entries] == ["view_session", "save_session"]
    assert entries[1]["prev_hash"] == "0" * 64
    assert entries[0]["prev_hash"] == entries[1]["hash"]
    assert log.verify()
    assert log.read(limit=1)[0]["action"] == "view_session"


def test_empty_log_verifies(tmp_path):
    assert AuditLog(tmp_path).verify() and AuditLog(tmp_path).read() == []


def test_tampering_is_detected(tmp_path):
    log = AuditLog(tmp_path)
    for i in range(3):
        log.log("view_session", "therapist", session_id=f"s{i}")
    lines = log.path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    entry["actor"] = "someone-else"
    lines[1] = json.dumps(entry, sort_keys=True)
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not log.verify()


def test_deleting_a_line_is_detected(tmp_path):
    log = AuditLog(tmp_path)
    for i in range(3):
        log.log("view_session", "t", session_id=f"s{i}")
    lines = log.path.read_text(encoding="utf-8").splitlines()
    log.path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    assert not log.verify()
