"""
src/reporting/fhir_export.py
----------------------------
Export CONFIRMED observations as an HL7 FHIR R4 Bundle (type "collection")
of Observation resources, for organisations that want to import them into
their own records.

Important: Observation.code carries TEXT ONLY. NeuroSync does not claim any
LOINC or SNOMED CT code for its observations – the receiving organisation
must map them to its own terminology. Status is "preliminary" because the
observations come from a software-assisted review, not a clinical test.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.config import settings
from src.core.session import Session


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def to_fhir_bundle(session: Session) -> dict:
    base = session.started_at or 0.0
    subject = session.consent.subject_id if session.consent else "unknown"
    entries = []
    for e in session.confirmed():
        obs = {
            "resourceType": "Observation",
            "id": str(uuid.uuid4()),
            "status": "preliminary",
            "code": {"text": "Observed behaviour during session (NeuroSync)"},
            "subject": {"display": f"pseudonym {subject}"},
            "effectivePeriod": {"start": _iso(base + e.start), "end": _iso(base + e.end)},
            "valueString": e.label,
            "component": [
                {"code": {"text": "Duration"},
                 "valueQuantity": {"value": round(e.duration, 1), "unit": "s",
                                   "system": "http://unitsofmeasure.org", "code": "s"}},
                {"code": {"text": "Detector confidence"},
                 "valueQuantity": {"value": round(e.confidence, 3), "unit": "1",
                                   "system": "http://unitsofmeasure.org", "code": "1"}},
            ],
            "note": [{"text": settings.app.disclaimer}],
        }
        if e.note:
            obs["note"].append({"text": f"Reviewer note: {e.note}"})
        entries.append({"fullUrl": f"urn:uuid:{obs['id']}", "resource": obs})
    return {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "type": "collection",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entry": entries,
    }
