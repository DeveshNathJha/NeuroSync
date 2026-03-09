# file: src/ui/dashboard.py

## 1. File Overview
**Purpose**: The **Command Center** of the application. It renders the "New Assessment" page.
**Role**: It integrates all the backend agents (Vision, Audio, Bio) into a unified real-time interface. It runs the main `while` loop that captures camera frames, runs inference, and updates the charts.
**Architecture Fit**: Called by `neuroapp.py`. It is the heaviest UI component.

## 2. Code Breakdown

### Configuration Sidebar (Lines 16-74)
-   **Input Source**: Allows switching between "Live Webcam" and "Upload Video".
-   **Bio-Interface**:
    -   *Vision AI*: Uses `bio.set_mode("MODE_WEBCAM")`.
    -   *Digital Twin*: Uses `bio.set_mode("MODE_TWIN")` and exposes sliders/checkboxes for manual simulation.
-   **Audio Monitor**: A visual progress bar showing volume levels.

### Main Layout (Lines 76-128)
-   **Columns**: Split into `Perception Layer` (Video Feed) and `Bio-Digital Twin` (Charts).
-   **State**: Uses `stop_clicked` to break the loop gracefully.

### The Runtime Loop (Lines 130-244)
This is the heart of the application.
1.  **Capture**: `cam.get_frame()` gets the latest image.
2.  **Vision**: `vision.process_frame(frame)` detects behaviors (Flapping, Spinning).
3.  **Simulation Injection**: If in Twin mode, it overrides the vision results with checkbox states (`st.session_state.sim_data`).
4.  **Audio**: `audio.process_chunk()` checks for screaming.
5.  **Logic (Fusion)**:
    -   aggregates all these into `force_stress`.
    -   `stress_active` state is updated.
6.  **Bio**: `bio.get_reading(force_stress)` uses the stress state to generate (or fetch) heart rate data.
7.  **Logging**: `fusion.correlate` checks if this combination of signals constitutes a clinical event.
8.  **Render**: Updates the video feed and the Real-time Charts (`chart_hr`, `chart_eeg`).

### Report Generation (Lines 252-280)
-   Triggered when the user clicks "End Session".
-   **Action**:
    -   Saves the session to disk (`logger_agent.save_session`).
    -   Calls the LLM (`reasoner.analyze_session`) to write a clinical narrative.
    -   Generates a PDF download.

## 3. Functions Explanation
-   `render_dashboard(...)`: The only public function. Takes all agent instances as arguments to avoid global state.

## 4. Data Flow
1.  **Sensors** -> **Agents** -> **Dashboard Loop**.
2.  **Dashboard Loop** -> **Fusion Engine** (Event Detection).
3.  **Dashboard Loop** -> **UI Elements** (60 FPS updates).
4.  **End Session** -> **DataLogger** (JSON) -> **Reasoner** (Text) -> **PDF**.

## 5. Internal Dependencies
-   **Agents**: Vision, Audio, Bio.
-   **Utils**: `pdf_generator`, `logger`.
-   **Sensors**: `CameraSensor` (Threaded wrapper for cv2).

## 6. Design Decisions
-   **Single Loop**: Streamlit updates the UI by re-running the script. However, inside `dashboard.py`, we use a `while` loop to update *placeholders* (`st.empty()`). This allows "Real-time" animation within a static web framework.
-   **Simulation Mode**: The `if "sim_data" in st.session_state` block allows doctors to demo the app without a patient present.

## 7. How to Modify
-   **Add New Chart**:
    1.  Create `chart_new = st.empty()`.
    2.  In the loop, update `df`.
    3.  Call `chart_new.line_chart(df['new_metric'])`.
-   **Change Report Trigger**: Move the "End Session" button to the sidebar.

## 8. Limitations
-   **Frame Rate**: The `time.sleep(0.03)` caps it at ~30 FPS. Complex processing (Vision + LLM) might drop this to 10 FPS.
-   **Memory**: Storing `bio_data` in session state can grow large. We pop old data (`if len > 60: pop(0)`) to keep it a rolling buffer.

## 9. Future Improvements
-   **WebRTC**: Replace the `cv2` loop with `streamlit-webrtc` for lower latency and better remote access support.
