import json
import uuid
from datetime import datetime
from typing import List, Dict

class FHIRExporter:
    """
    ENTERPRISE COMPLIANCE MODULE (HL7 FHIR R4)
    ------------------------------------------
    Converts NeuroSync internal event logs into hospital-ready JSON.
    Standard: HL7 FHIR 'Observation' Resource.
    
    Why this matters:
    Real medical AI cannot just dump CSVs. It must speak the language
    of Electronic Health Records (EHR).
    """

    @staticmethod
    def create_observation(patient_id: str, events: List[Dict]) -> Dict:
        """
        Generates a valid FHIR Bundle containing clinical observations.
        """
        # 1. Create the Bundle Header (The "Envelope")
        fhir_bundle = {
            "resourceType": "Bundle",
            "id": str(uuid.uuid4()),
            "type": "collection",
            "timestamp": datetime.now().isoformat(),
            "entry": []
        }

        # 2. Convert each fusion event into a FHIR Observation
        for event in events:
            # Check if this is a "Match" or just a raw log
            # We map specific symptoms to LOINC codes (Logical Observation Identifiers Names and Codes)
            
            symptom_display = ", ".join(event.get('symptoms', ['Unspecified Behavior']))
            
            observation = {
                "resourceType": "Observation",
                "status": "final",
                "category": [{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "exam",
                        "display": "Exam"
                    }]
                }],
                "code": {
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": "88031-0", 
                        "display": "Autism spectrum disorder behavior screening"
                    }]
                },
                "subject": {
                    "reference": f"Patient/{patient_id}"
                },
                "effectiveDateTime": datetime.fromtimestamp(event.get('timestamp', 0)).isoformat(),
                "component": [
                    {
                        "code": {"text": "Behavior Detected"},
                        "valueString": symptom_display
                    },
                    {
                        "code": {"text": "Neurological Correlation"},
                        "valueString": "Confirmed" if "MATCH" in event.get('event_type', '') else "Uncorrelated"
                    },
                    {
                        "code": {"text": "Confidence Score"},
                        "valueQuantity": {
                            "value": event.get('confidence', 0.0),
                            "unit": "%"
                        }
                    }
                ],
                "interpretation": [
                    {"text": event.get('details', 'No details provided')}
                ]
            }
            
            # Add to bundle
            fhir_bundle['entry'].append({"resource": observation})
            
        return fhir_bundle

    @staticmethod
    def save_to_file(data: Dict, filepath: str):
        """Saves the JSON bundle to disk."""
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"[FHIR] Report successfully exported to {filepath}")
        except Exception as e:
            print(f"[FHIR] Error exporting report: {e}")