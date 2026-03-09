# file: src/agents/vision_agent.py

## 1. File Overview
**Purpose**: This is the **Visual Perception Engine**. It analyzes video frames to detect autistic behaviors (Stimming).
**Role**: It uses Computer Vision (MediaPipe) to track body landmarks and applies heuristic logic to identify specific movement patterns:
-   Hand Flapping
-   Head Banging
-   Spinning
-   Gaze Aversion
**Architecture Fit**: It is the heaviest computational component. It runs on every video frame in the main UI loop.

## 2. Code Breakdown

### Init & Resilience (Lines 16-33)
```python
try:
    self.mp_holistic = mp.solutions.holistic
    # ...
except:
    self.vision_available = False
```
-   **Safety**: Recently patched to handle `AttributeError` if MediaPipe is incompatible with Python 3.12. If it fails, `vision_available` is set to `False`, allowing the app to run in "Blind Mode".

### State Buffers (Lines 39-44)
```python
self.spin_buffer = []
self.bang_buffer = []
```
-   **Why**: We cannot detect "Spinning" from a single frame. We need *temporal context*. These lists store the boolean result of the last N frames to check for consistency.

### Core Logic: `process_frame` (Lines 45-166)

#### A. Pre-Processing
-   Converts BGR (OpenCV) to RGB (MediaPipe).
-   Checks `vision_available`. Returns empty data if disabled.

#### B. Normalization (Lines 80-83)
```python
face_width = abs(right_ear.x - left_ear.x)
```
-   **Crucial Step**: It calculates the pixel width of the face. All velocity thresholds are divided by this.
-   **Why**: Without this, moving closer to the camera (face gets bigger) would be interpreted as "Fast Motion" because the pixels change faster. Normalization makes the logic **Scale Invariant**.

#### C. Gross Motor Logic (Spinning/Banging)
-   Refers to `nose.x` and `nose.y` velocity.
-   If `velocity > threshold` for 3 consecutive frames (buffer sum), it triggers.

#### D. Fine Motor Logic (Gaze)
-   **Suppression**: `if not output["spinning"]...`
-   **Why**: If a child is spinning, their eyes naturally move. We shouldn't flag "Gaze Aversion" during gross motor activity. This is a "Hierarchical Rule".

#### E. Body Logic (Flapping)
-   Checks if wrists are above shoulders (`y` coordinate).
-   Checks if wrists are close to each other (Clapping motion).
-   **Metric**: Normalized by `shoulder_width`.

## 3. Functions Explanation
-   `process_frame(frame)`: Takes one image. Returns specific behaviors (`dict`) and the annotated image (`numpy array`) with skeleton lines drawn on it.

## 4. Data Flow
1.  **Input**: Raw Image (480x640 array).
2.  **Model**: MediaPipe Holistic infers 543 landmarks (x, y, z).
3.  **Logic**: Python scripts analyze the relationship between landmarks (Distance, Velocity).
4.  **Output**:
    ```json
    {
      "detected": True,
      "hand_flapping": True,
      "head_banging": False,
      # ...
    }
    ```

## 5. Internal Dependencies
-   **MediaPipe**: The heavy lifter for skeleton tracking.
-   **OpenCV**: For color conversion and image resizing.

## 6. Design Decisions
-   **Rule-Based AI**: We use explicit math (`if hand_y < head_y`) instead of a Deep Learning Classifier (`ResNet`).
    -   **Pros**: Fast, Explainable (White-box), No training data needed initially.
    -   **Cons**: Rigid. Can be fooled by similar gestures (e.g., Waving hello vs Flapping).

## 7. How to Modify
-   **New Gesture**: To detect "Covering Ears" (sensory overload):
    1.  Get coordinates of `hands` and `ears`.
    2.  Calculate distance.
    3.  If `dist < threshold`, set `output['covering_ears'] = True`.
-   **Tune Sensitivity**: Lower the velocity thresholds (e.g., `2.5` to `2.0`) to detect subtle spinning.

## 8. Limitations
-   **Occlusion**: If the child turns their back, MediaPipe loses the face, and detection stops.
-   **Multi-Person**: MediaPipe Holistic only tracks **one person**. It will get confused if a parent enters the frame.

## 9. Future Improvements
-   **Temporal Model**: Replace the `buffer` logic with an LSTM or Transformer (e.g., VideoMAE) that takes 30 frames as input and classifies the action. This would be much more robust than frame-by-frame rules.
