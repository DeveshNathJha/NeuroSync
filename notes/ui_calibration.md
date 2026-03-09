# file: src/ui/calibration.py

## 1. File Overview
**Purpose**: Handles **Patient-Specific Baseline Calibration**.
**Role**: Before starting a session, the system needs to know what "Normal" looks like for *this* specific child. This module records 30 seconds of resting data to set custom thresholds.
**Architecture Fit**: Integrated via `neuroapp.py`. Updates `st.session_state.patient_config`.

## 2. Code Breakdown

### UI Logic (Lines 15-42)
-   Displays instructions.
-   Uses `st.session_state.is_calibrating` to toggle between the "Start" button and the "Cancel" button.

### Calibration Loop (Lines 44-80)
-   Similar to `dashboard.py`, it opens the camera and runs a loop.
-   **Difference**: It does *not* detect meltdowns. It simply *records* raw metrics:
    -   `motion_x` / `motion_y`: How much does the child fidget?
    -   `heart_rate`: What is their resting HR?

### Calculation (Lines 84-100)
```python
mean_motion = df['motion_x'].abs().mean()
std_motion = df['motion_x'].abs().std()
motion_thresh = mean_motion + (3 * std_motion)
```
-   **Algorithm**: Uses the **3-Sigma Rule** (Mean + 3 Standard Deviations).
-   **Logic**: If the child's movement exceeds 99.7% of their resting movement distribution, it counts as an "Anomaly" (Hyperactivity).

### Persistence (Lines 95-103)
-   Saves the results to `st.session_state.patient_config`.
-   In a future version, this should save to `PatientDB`.

## 3. Data Flow
1.  **User**: Clicks "Start".
2.  **Sensors**: Capture 30s of data.
3.  **Math**: Pandas calculates Mean/StdDev.
4.  **Config**: Thresholds are updated in memory.
5.  **Next Session**: `VisionAgent` (theoretically) reads these thresholds to tune sensitivity.

## 4. Design Decisions
-   **30 Seconds**: Chosen as a trade-off between accuracy and patience (autistic children may not sit still for longer).
-   **3-Sigma**: Standard statistical method for outlier detection.

## 5. How to Modify
-   **Change Duration**: Edit `duration = 30`.
-   **Save to Disk**: Add `json.dump(config, open('patient_config.json', 'w'))` at the end.

## 6. Limitations
-   **Not Wired Up**: The calculate thresholds are saved to `session_state`, but `VisionAgent` currently uses hardcoded defaults (`settings.py`). This module is a "Proof of Concept" pending integration.

## 7. Future Improvements
-   **Dynamic Update**: Make `VisionAgent` accept a `config` object in its `process_frame` method to use these custom thresholds.
