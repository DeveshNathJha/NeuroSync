# file: src/utils/data_logger.py

## 1. File Overview
**Purpose**: **Electronic Health Record (EHR) Handler**.
**Role**: Manages the persistent storage of clinical sessions. It is the bridge between the in-memory `session_state` and the encrypted file system.
**Architecture Fit**: Used by `dashboard.py` (to save) and `history.py` (to load).

## 2. Code Breakdown

### `save_session` (Lines 26-84)
-   **Step 1: Anonymization**: Hashes the `patient_id` (SHA256). We never use real names in filenames.
-   **Step 2: Metadata**: Adds `software_version` and `timestamp`.
-   **Step 3: Encryption**: Calls `self.crypto.encrypt_data`.
-   **Step 4: Storage**: Writes to `data/patient_logs/ANON_xxxx.enc`.
-   **Step 5: Indexing**: Calls `patient_db.register_session` to update the fast-lookup index.

### `load_history` (Lines 86-121)
-   **Goal**: Return full details for a *specific* patient.
-   **Logic**:
    1.  Re-calculates the Hash of the requested ID.
    2.  Scans the directory for filenames matching `ANON_{hash}`.
    3.  Decrypts each file one by one.
-   **Performance**: This is slow (O(N) * Decryption Time). It should only be used when deep-diving into a specific patient.

### `get_patient_trends` (Lines 123-129)
-   **Goal**: Fast stats for graphing.
-   **Optimization**: Instead of decrypting files, it asks `PatientDB` (the local JSON index) for the pre-calculated summaries. This makes the `History` page load instantly.

## 3. Functions Explanation
-   `save_session`: Returns the filepath upon success.
-   `load_history`: Returns a list of full session dictionaries.

## 4. Internal Dependencies
-   `CryptoManager`: For security.
-   `PatientDB`: For indexing.

## 5. Design Decisions
-   **JSON Format**: Flexible schema. We can add new sensors/metrics without breaking old files.
-   **Dual Storage**: We store the *Full Data* (Encrypted) and a *Summary* (Index). This gives us both security and performance.

## 6. How to Modify
-   **Change Directory**: Edit `settings.PATIENT_LOGS_DIR`.

## 7. Limitations
-   **File Count**: If a patient has 10,000 sessions, `os.listdir` might get slow.
-   **Conflict**: No file locking. If two app instances write to the same patient at once, data might corrupt (unlikely in this single-user app).

## 8. Future Improvements
-   **SQLite**: Move from JSON files to an encrypted `SQLCipher` database for better querying capabilities.
