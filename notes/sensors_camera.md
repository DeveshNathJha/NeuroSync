# file: src/sensors/camera.py

## 1. File Overview
**Purpose**: **Hardware Abstraction Layer (HAL)** for Video Input.
**Role**: Provides a safe, consistent interface to the Webcam or Video File.
**Why**: `cv2.VideoCapture` is "low-level" and prone to errors. This class wraps it with error handling and resource management.

## 2. Code Breakdown

### Init (Lines 19-28)
-   Accepts `source`: Can be an Integer (0, 1 for webcams) or String ("file.mp4").

### `start()` (Lines 30-50)
-   **Safety**: Explicitly checks `if not self.cap.isOpened()`.
-   **Specs**: Reads the actual width/height from the hardware to log it.

### `get_frame()` (Lines 57-69)
-   **Wrapper**: Calls `cap.read()`.
-   **Disconnect Detection**: If `ret` is False, it assumes the camera was unplugged or the video file ended, and calls `stop()`.

## 3. Design Decisions
-   **Thread Safety**: Currently NOT thread-safe. Only one agent should own the camera.
-   **Blocking**: `read()` is a blocking call.

## 4. How to Modify
-   **Change Resolution**: Add `self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)` in `start()`.
-   **FPS Control**: Add `self.cap.set(cv2.CAP_PROP_FPS, 60)`.

## 5. Limitations
-   **USB Bandwidth**: If you try to open two cameras (0 and 1) on the same USB hub, `start()` might fail.
-   **File Looping**: Does not auto-loop video files.

## 6. Future Improvements
-   **Async Reader**: Move `cap.read()` to a separate thread that constantly updates a `latest_frame` buffer. This prevents the UI from lagging if the camera is slow.
