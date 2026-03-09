# file: src/orchestration/fusion_engine.py

## 1. File Overview
**Purpose**: The **Multimodal Synchronizer**. It is the "Cerebellum" of the AI.
**Role**: It takes independent signals (Vision says "Hand Flapping", Bio says "High Heart Rate") and checks if they happen *at the same time*.
**Key Concept**: "Temporal Correlation". A behavior is only clinical if it correlates with physiological stress.

## 2. Code Breakdown

### The `ingest_bio_event` Method (Lines 25-35)
-   Stores the timestamp of the last "Stress Spike" (High HR/Low HRV).
-   Acts as a memory buffer for the physiological state.

### The `correlate` Method (Lines 36-75)
-   **Input**: `vision_data` (Current frame).
-   **Step 1**: Checks if any visual symptoms are active (Flapping, Spinning, Banging).
-   **Step 2 (The Fusion)**:
    ```python
    time_diff = abs(current_time - self.last_bio_spike_time)
    if self.last_bio_stress_state or (time_diff <= self.window):
        # MATCH FOUND
    ```
-   **Logic**:
    -   If the child is Stimming AND the Heart Rate is high...
    -   OR if the Heart Rate spiked less than 1.0 second ago (LAG)...
    -   THEN it confirms a "Neuro-Behavioral Match".

## 3. Data Flow
1.  **BioAgent** pushes data -> `ingest_bio_event`.
2.  **VisionAgent** pushes data -> `correlate`.
3.  **FusionEngine** returns `Event` object or `None`.
4.  **Dashboard** logs the event if not None.

## 4. Design Decisions
-   **1.0 Second Window**: Chosen because physiological arousal (sympathetic nervous system) often precedes or follows behavior by a split second. A hard "exact timestamp match" would miss many events due to sensor latency.
-   **Unidirectional**: Vision polls Bio. Bio does not know about Vision. This prevents circular dependencies.

## 5. How to Modify
-   **Widen Window**: Change `self.window = 2.0` to be more lenient.
-   **Add Audio**: Currently, it only correlates Vision+Bio. To add Audio:
    1.  Add `ingest_audio_event`.
    2.  Check `if self.last_audio_scream_time` in `correlate`.

## 6. Limitations
-   **Memory**: It only remembers the *last* bio event. If multiple spikes happen, previous ones are overwritten.
-   **Simple Boolean**: It treats "Stress" as True/False. It doesn't use the magnitude (e.g., "HR is 180 vs 110").

## 7. Future Improvements
-   **Complex Event Processing (CEP)**: Use a proper library like `RxPy` to handle streams of events instead of manual if-statements.
