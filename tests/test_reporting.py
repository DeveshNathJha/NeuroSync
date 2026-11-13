"""Tests for report generation, the PDF and the FHIR export."""

from pathlib import Path

import pytest

from src.config import settings
from src.core.events import Event
from src.core.session import Consent, Session
from src.reporting import guard
from src.reporting.fhir_export import to_fhir_bundle
from src.reporting.pdf_report import render_pdf
from src.reporting.reasoner import ReportGenerator, mmss


def session_with_events():
    s = Session(Consent(subject_id="S-07", given_by="parent/guardian", recorded_by="therapist"))
    s.start()
    hand = Event(kind="repetitive_hand_movement", start=65, end=70, confidence=0.9, source="vision")
    hr = Event(kind="elevated_heart_rate", start=64, end=75, confidence=0.6, source="rppg")
    loud = Event(kind="loud_vocalisation", start=200, end=201, confidence=0.7, source="audio")
    hand.linked = [hr.id]
    s.add_events([hand, hr, loud])
    s.review(hand.id, "confirmed", note="during transition")
    s.review(hr.id, "confirmed")
    s.review(loud.id, "rejected")
    s.heart_rate = [(60.0, 88.0, 6.0), (70.0, 110.0, 5.0)]
    s.baseline_hr = 85.0
    s.stop()
    return s, hand, hr, loud


def no_llm(tmp_path):
    return ReportGenerator(llm_path=tmp_path / "missing.gguf")


def test_mmss():
    assert mmss(0) == "00:00" and mmss(65.4) == "01:05" and mmss(-3) == "00:00"


def test_template_uses_confirmed_events_only(tmp_path):
    s, hand, hr, loud = session_with_events()
    rep = no_llm(tmp_path).generate(s)
    assert rep["mode"] == "template"
    assert "Repetitive hand/arm movement" in rep["text"] and "01:05" in rep["text"]
    assert "Loud vocalisation" not in rep["text"]          # rejected event excluded
    assert "heart rate above personal baseline" in rep["text"]  # co-occurrence as timing only
    assert rep["text"].rstrip().endswith(settings.app.disclaimer)
    assert rep["guard_removed"] == []


def test_template_family_audience_and_empty_session(tmp_path):
    s = Session(Consent(subject_id="S-1", given_by="parent", recorded_by="t"))
    s.start()
    s.stop()
    rep = no_llm(tmp_path).generate(s, audience="family")
    assert "No observations were confirmed" in rep["text"]
    with pytest.raises(ValueError):
        no_llm(tmp_path).generate(s, audience="doctor")


def test_llm_output_is_guarded_and_prompt_has_confirmed_facts_only():
    s, *_ = session_with_events()
    seen = {}

    def fake_llm(prompt):
        seen["prompt"] = prompt
        return "Repetitive hand movement at 01:05. This is a typical symptom of autism."

    rep = ReportGenerator(llm=fake_llm).generate(s)
    assert rep["mode"] == "llm"
    assert "autism" not in rep["text"].lower().replace(settings.app.disclaimer.lower(), "")
    assert guard.REPLACEMENT in rep["text"]
    assert {t.lower() for t in rep["guard_removed"]} >= {"symptom", "autism"}
    assert "Repetitive hand/arm movement" in seen["prompt"]
    assert "Loud vocalisation" not in seen["prompt"]
    assert "Do not interpret, diagnose" in seen["prompt"]


def test_llm_failure_falls_back_to_template():
    s, *_ = session_with_events()

    def broken(prompt):
        raise RuntimeError("model crashed")

    rep = ReportGenerator(llm=broken).generate(s)
    assert rep["mode"] == "template" and "Repetitive hand/arm movement" in rep["text"]


def test_missing_model_means_template_mode(tmp_path):
    assert no_llm(tmp_path).available_mode == "template"


def test_pdf_renders(tmp_path):
    s, *_ = session_with_events()
    rep = no_llm(tmp_path).generate(s)
    out = render_pdf(s, rep, tmp_path / "out" / "notes.pdf")
    assert isinstance(out, Path) and out.exists()
    assert out.read_bytes()[:4] == b"%PDF" and out.stat().st_size > 1000


def test_fhir_bundle_confirmed_only_and_no_code_claims():
    s, hand, hr, loud = session_with_events()
    bundle = to_fhir_bundle(s)
    assert bundle["resourceType"] == "Bundle" and bundle["type"] == "collection"
    obs = [e["resource"] for e in bundle["entry"]]
    assert sorted(o["valueString"] for o in obs) == sorted([hand.label, hr.label])
    for o in obs:
        assert o["status"] == "preliminary"
        assert "coding" not in o["code"]                     # text only, no LOINC/SNOMED claims
        assert o["effectivePeriod"]["start"] < o["effectivePeriod"]["end"]
    hand_obs = next(o for o in obs if o["valueString"] == hand.label)
    assert any("Reviewer note" in n["text"] for n in hand_obs["note"])
