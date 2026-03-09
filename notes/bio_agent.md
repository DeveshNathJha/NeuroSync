# file: src/agents/bio_agent.py

## 1. File Overview
**Purpose**: This agent serves as the **Physiological Gateway**. It abstracts the source of bio-signals (Heart Rate, EEG).
**Role**: It ensures the system always has bio-data to work with, whether it comes from a $500 EEG headset, a standard Webcam (rPPG), or a Digital Twin simulation.
**Key Concept**: "Sensor Fusion Layer" - it unifies three different data sources into a single standard format.

## 2. Code Breakdown

### Imports & LSL (Lines 1-16)
```python
try:
    from pylsl import StreamInlet, resolve_stream
    LSL_AVAILABLE = True
except ImportError: ...
```
-   **LSL (Lab Streaming Layer)**: The industry standard protocol for connecting research hardware (Muse, OpenBCI, NeuroSky) to Python.
-   **Safety**: Wraps import in try-except to prevent crashes on machines without the LSL library (e.g., Windows without DLLs).

### Initialization (Lines 27-44)
-   `self.mode`: Can be `MODE_WEBCAM`, `MODE_HARDWARE`, or `MODE_TWIN`. Defaults to TWIN (Simulation) for safety.
-   `self.rppg`: Instance of `RemotePPG` logic.
-   `self.inlet`: The connection object to physical hardware.

### rPPG Integration (Lines 51-56)
```python
def update_rppg(self, frame, face_roi=None):
    if self.mode == "MODE_WEBCAM":
        bpm, conf, _ = self.rppg.process_frame(frame, face_roi)
        # ...
```
-   **Data Flow**: The `VisionAgent` (in another thread/loop) captures a frame. It passes it *here*. `BioAgent` calculates the heart rate from color changes in the face (rPPG).

### Data Packet Generation (Lines 83-127)
This is the **Core Logic**. It decides which data to return based on the active mode.

#### A. Webcam Mode
-   Uses `self.rppg_data['bpm']`.
-   **Heuristic**: Calculates HRV (Heart Rate Variability) as an inverse function of Heart Rate (`100 - (HR - 60)`). *Note: This is a synthetic approximation for demo purposes since true HRV requires millisecond-accurate ECG.*

#### B. Hardware Mode
-   `self.inlet.pull_sample()`: Reads real voltage data from the EEG headset.
-   **Normalization**: Maps raw EEG microvolts to 0.0-1.0 `alpha`/`beta` waves.

#### C. Twin Mode (Simulation)
-   **Logic**: If no sensors are available, it generates random numbers that *look* like bio-data.
-   **Stress Trigger**: If `force_stress=True` (triggered by the Dashboard), it shifts the random distribution to higher HR (115-140) and lower HRV to simulate a meltdown.
-   **Simulation Settings**: Recently added support for `sim_settings` to allow manual slider control from the UI.

## 3. Functions Explanation
-   `connect_hardware()`: Scans the local network/USB for an LSL stream. Returns True if found.
-   `get_reading()`: The main public API. Called by `neuroapp.py` or `dashboard.py` once per frame.

## 4. Data Flow
1.  **Input**:
    -   Video Frame (Webcam Mode)
    -   OR LSL Stream (Hardware Mode)
    -   OR Random Seed (Twin Mode)
2.  **Processing**:
    -   rPPG Algorithm (Signal Processing)
    -   OR Normalization (Hardware)
    -   OR Random Generation (Twin)
3.  **Output**: Standardized Dictionary:
    ```json
    {
      "timestamp": 123456789,
      "source": "VISION_RPPG",
      "heart_rate": 75.5,
      "eeg_alpha": 0.8,
      "stress_detected": False
    }
    ```

## 5. Internal Dependencies
-   `src.sensors.rppg`: The computer vision logic for heart rate.
-   `pylsl`: External driver.

## 6. Design Decisions
-   **Digital Twin Fallback**: Crucial for development. It allows developers to test the UI and Logic without needing to wear a headset or set up a camera every time.
-   **Abstraction**: The rest of the app doesn't care *where* the heart rate comes from. It just asks `bio.get_reading()`.

## 7. How to Modify
-   **Add New Sensor**:
    1.  Add `MODE_APPLE_WATCH`.
    2.  In `get_reading`, add an `elif self.mode == "MODE_APPLE_WATCH":` block.
    3.  Implement the API call to fetch data from the watch.
-   **Improve rPPG**: Replace the heuristic HRV calculation with a real FFT-based analysis of the pulse wave in `src/sensors/rppg.py`.

## 8. Limitations
-   **rPPG Accuracy**: Webcam heart rate is sensitive to lighting and motion. It fails if the subject moves too much (common in autism).
-   **Synthesis**: The "Synthetic EEG" in Webcam mode is purely inferred from Heart Rate. It is not real brainwave data.

## 9. Future Improvements
-   **Kalman Filter**: Implement a Kalman filter to fuse Webcam data + Hardware data (if both available) for a "Super-Resolution" reading.
