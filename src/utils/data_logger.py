import json
import os
import time
from datetime import datetime
from typing import Dict, List, Any
from config.settings import settings
from src.utils.logger import logger
from src.utils.crypto_manager import CryptoManager
from src.utils.patient_db import PatientDB

class DataLogger:
    """
    ENTERPRISE DATA HANDLER
    -----------------------
    Manages the storage and retrieval of patient session logs.
    Acts as the 'Electronic Health Record' (EHR) interface.
    """

    def __init__(self, base_dir: str = settings.PATIENT_LOGS_DIR):
        self.base_dir = base_dir
        self.last_filename = "" 
        self.crypto = CryptoManager() # Load Encryption Engine
        self.patient_db = PatientDB() # Load Local Index
        os.makedirs(self.base_dir, exist_ok=True)

    def save_session(self, patient_id: str, session_data: Dict[str, Any]) -> str:
        """
        Saves a full clinical session to disk (ENCRYPTED) and updates Trend DB.
        Returns the file path for confirmation.
        """
        # 1. Anonymize ID (Simple Hash for Privacy)
        import hashlib
        import numpy as np
        anon_id = hashlib.sha256(patient_id.encode()).hexdigest()[:8]
        
        # 2. Generate Unique Filename
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ANON_{anon_id}_SESSION_{timestamp_str}.enc" 
        filepath = os.path.join(self.base_dir, filename)

        # 3. Add Metadata
        final_record = {
            "meta": {
                "patient_hash": anon_id,
                "recorded_at": datetime.now().isoformat(),
                "software_version": "NeuroSync v5.3 (Secure)",
                "clinic_id": "TATA-ELXSI-LAB-01"
            },
            "session": session_data
        }

        # 4. Encrypt & Write to Disk
        try:
            json_str = json.dumps(final_record)
            encrypted_data = self.crypto.encrypt_data(json_str)
            
            with open(filepath, 'wb') as f: 
                f.write(encrypted_data)
            
            self.last_filename = filename 
            logger.info(f"Session encrypted & saved: {filepath}")
            
            # 5. [NEW] Update Trend Database (Indexing)
            # Calculate summary stats from the raw session data
            bio_log = session_data.get("bio_summary", [])
            events = session_data.get("fusion_events", [])
            
            avg_hr = 0
            if bio_log:
                avg_hr = float(np.mean([b['heart_rate'] for b in bio_log if b['heart_rate'] > 0]))
            
            summary = {
                "duration": len(bio_log) / 30.0 if bio_log else 0, # Approx 30fps
                "event_count": len(events),
                "avg_hr": round(avg_hr, 1),
                "dominant_symptom": events[0]['symptoms'][0] if events else "None"
            }
            
            self.patient_db.register_session(anon_id, filename, summary)
            
            return filepath
        except Exception as e:
            logger.error(f"CRITICAL ERROR: Could not save log. {e}")
            return ""

    def load_history(self, patient_id: str) -> List[Dict]:
        """
        Retrieves past sessions (Decryption on the fly).
        """
        history = []
        try:
            # 1. Compute Hash to match filenames
            import hashlib
            anon_id = hashlib.sha256(patient_id.encode()).hexdigest()[:8]
            search_prefix = f"ANON_{anon_id}"
            
            # Scan directory for files 
            for f in os.listdir(self.base_dir):
                if f.startswith(search_prefix) and (f.endswith(".json") or f.endswith(".enc")):
                    path = os.path.join(self.base_dir, f)
                    
                    try:
                        # Handle Legacy JSON
                        if f.endswith(".json"):
                            with open(path, 'r') as file:
                                data = json.load(file)
                                history.append(data)
                        # Handle Secure Encrypted Files
                        elif f.endswith(".enc"):
                            with open(path, 'rb') as file:
                                encrypted_data = file.read()
                                json_str = self.crypto.decrypt_data(encrypted_data)
                                data = json.loads(json_str)
                                history.append(data)
                    except Exception as e:
                        logger.warning(f"Corrupt file {f}: {e}")
                        
            return history
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            return []

    def get_patient_trends(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Returns chronological trend data from local index.
        """
        import hashlib
        anon_id = hashlib.sha256(patient_id.encode()).hexdigest()[:8]
        return self.patient_db.get_patient_trends(anon_id)