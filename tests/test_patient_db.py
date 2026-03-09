import os
import shutil
import sys
# Add project root to path
sys.path.append(os.getcwd())

from src.utils.data_logger import DataLogger
from src.utils.patient_db import PatientDB

def test_patient_db_flow():
    print("--- Testing PatientDB Integration ---")
    
    # 1. Setup
    test_id = "TEST-CHILD-001"
    logger = DataLogger()
    
    # Clear old DB for test
    if os.path.exists("data/patient_db.json"):
        os.remove("data/patient_db.json")
    logger.patient_db = PatientDB() # Re-init to create file
    
    # 2. Simulate a Session
    dummy_session = {
        "fusion_events": [
            {"symptoms": ["Hand Flapping"], "timestamp": 1234567890}
        ],
        "bio_summary": [
            {"heart_rate": 80}, {"heart_rate": 90}, {"heart_rate": 85}
        ]
    }
    
    print(f"Saving session for {test_id}...")
    file_path = logger.save_session(test_id, dummy_session)
    print(f"Saved to: {file_path}")
    
    # 3. Verify DB Content
    trends = logger.get_patient_trends(test_id)
    print(f"Retrieved {len(trends)} trend records.")
    
    if len(trends) == 1:
        t = trends[0]
        print(f"Record Data: {t}")
        assert t['event_count'] == 1
        assert t['avg_hr'] == 85.0
        assert t['dominant_symptom'] == "Hand Flapping"
        print("SUCCESS: Data verification passed.")
    else:
        print("FAILURE: No trends found.")
        exit(1)

if __name__ == "__main__":
    test_patient_db_flow()
