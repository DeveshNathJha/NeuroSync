# file: src/utils/patient_db.py

## 1. File Overview
**Purpose**: **Local Indexing Service**.
**Role**: Maintains a lightweight summary of all patient data in `data/patient_db.json`.
**Why**: Decrypting 100 session files to draw a simple line graph is too slow. This DB stores the *metadata* (Date, Avg HR, Event Count) in plaintext (or lightly protected) JSON for instant access.

## 2. Code Breakdown

### Storage Structure (Lines 44-50)
```json
"patients": {
  "HASH_123": {
    "sessions": [
      {"timestamp": ..., "avg_hr": 80, ...},
      {"timestamp": ..., "avg_hr": 82, ...}
    ]
  }
}
```

### `register_session` (Lines 37-66)
-   Called every time a session is saved.
-   Appends a summary object to the patient's list.
-   **Concurrency Risk**: It reads-modifies-writes the whole JSON file. High risk of race conditions if multiple threads call this (but Streamlit is single-user).

### `get_patient_trends` (Lines 68-76)
-   Returns the `sessions` list sorted by time.
-   Used by `history.py` to plot charts.

## 3. Design Decisions
-   **No SQL**: We avoided SQLite here to keep the project "copy-paste friendly" (Just a folder of files).
-   **Redundancy**: This data is technically redundant (it exists in the `.enc` files). But the speed gain is worth it.

## 4. Limitations
-   **Scalability**: If the JSON file grows to 100MB, reading/writing it every time will become slow.
-   **Sync**: If a user manually deletes an `.enc` file, this DB will point to a non-existent file ("Ghost Record"). `rebuild_index()` (Line 78) is defined but not implemented.

## 5. Future Improvements
-   **Implement Rebuild**: Validates that every file in the index actually exists on disk.
