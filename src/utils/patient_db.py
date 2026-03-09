import json
import os
import time
from typing import List, Dict, Any
from config.settings import settings
from src.utils.logger import logger

class PatientDB:
    """
    LOCAL-FIRST PATIENT DATABASE (No Cloud)
    ---------------------------------------
    Manages a lightweight JSON index of all patient sessions.
    Allows for fast trend analysis without decrypting every single file on load.
    """
    
    def __init__(self):
        self.db_path = "data/patient_db.json"
        self._ensure_db()
        
    def _ensure_db(self):
        if not os.path.exists(self.db_path):
            with open(self.db_path, "w") as f:
                json.dump({"patients": {}}, f)
                
    def _load_db(self) -> Dict[str, Any]:
        try:
            with open(self.db_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"DB Load Error: {e}")
            return {"patients": {}}
            
    def _save_db(self, db: Dict[str, Any]):
        with open(self.db_path, "w") as f:
            json.dump(db, f, indent=2)

    def register_session(self, patient_id: str, session_file: str, summary: Dict[str, Any]):
        """
        Registers a new session in the local index.
        Called by LoggerAgent after saving a session.
        """
        db = self._load_db()
        
        if patient_id not in db["patients"]:
            db["patients"][patient_id] = {
                "sessions": [],
                "created_at": time.time(),
                "last_seen": time.time()
            }
            
        # Store metadata for quick access (Graphing)
        session_meta = {
            "file": session_file,
            "timestamp": time.time(),
            "duration_sec": summary.get("duration", 0),
            "event_count": summary.get("event_count", 0),
            "avg_hr": summary.get("avg_hr", 0),
            "avg_engagement": summary.get("avg_engagement", 0),
            "dominant_symptom": summary.get("dominant_symptom", "None")
        }
        
        db["patients"][patient_id]["sessions"].append(session_meta)
        db["patients"][patient_id]["last_seen"] = time.time()
        
        self._save_db(db)
        logger.info(f"Session registered in PatientDB for {patient_id}")

    def get_patient_trends(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Returns chronological list of session stats for graphing.
        """
        db = self._load_db()
        if patient_id not in db["patients"]:
            return []
            
        return sorted(db["patients"][patient_id]["sessions"], key=lambda x: x["timestamp"])

    def rebuild_index(self):
        """
        Scans data/patient_logs and rebuilds the JSON index.
        Useful if the DB file is deleted or out of sync.
        CAUTION: This is slow because it decrypts every file.
        """
        # Implementation for later robustness
        pass
