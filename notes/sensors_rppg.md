# file: src/sensors/rppg.py

## 1. File Overview
**Purpose**: **Remote Photoplethysmography (rPPG)** Engine.
**Role**: Extracts Heart Rate from a video feed without contact.
**Science**: When the heart beats, blood volume in the face increases, slightly changing the skin's light absorption (making it greener). This sensor detects that sub-pixel color shift.

## 2. Code Breakdown

### signal Processing params (Lines 20-32)
-   `buffer_size = 300`: At 30 FPS, this is a 10-second window. We need at least 5-10 seconds to detect a rhythmic pulse.
-   `min_hz` / `max_hz`: Bandpass filter limits (42-240 BPM).

### `process_frame` (Lines 39-86)
1.  **ROI**: If `VisionAgent` provides a face box (`face_roi`), we use it. If not, we use a built-in Haar Cascade (fallback).
2.  **Extraction**: We crop to the **Center 60%** of the face (Cheeks/Forehead) to avoid background noise.
3.  **Green Channel**: `avg_green = np.mean(roi[:, :, 1])`. Green light penetrates skin best to see blood.
4.  **Buffer**: Append mean value to `data_buffer`.

### `_update_bpm` (Lines 88-131)
**The Algorithm**:
1.  **Detrend**: Removes slow changes (e.g., sun going behind a cloud, person moving head).
2.  **Window**: Applies Hamming window to smooth edges.
3.  **FFT (Fast Fourier Transform)**: Converts Time-Domain signal to Frequency-Domain.
4.  **Peak Finding**: Looks for the strongest frequency in the valid heart rate range.
5.  **Smoothing**: `bpm = old * 0.8 + new * 0.2`. Prevents jumpy numbers.

## 3. Data Flow
1.  **Input**: Image Frame.
2.  **Process**: Extract Green -> Accumulate 300 frames -> FFT.
3.  **Output**: `bpm` (Float) and `confidence` (Float).

## 4. Internal Dependencies
-   `scipy.signal`: For Detrending.
-   `numpy.fft`: For Fourier Transform.

## 5. Design Decisions
-   **Green Channel Only**: Simple and fast. More complex methods ("CHROM", "POS") use RGB combinations but are slower.
-   **15-Frame Update**: We only re-calculate the FFT every 0.5s (15 frames) to save CPU.

## 6. How to Modify
-   **Improve Accuracy**: Implement "Plane-Orthogonal-to-Skin (POS)" algorithm. It is more robust to motion.
-   **Change RAM Usage**: Reduce `buffer_size` to 150 (5 seconds) for faster response, but less accuracy.

## 7. Limitations
-   **Lighting**: Fails in dark rooms.
-   **Skin Tone**: Less accurate on darker skin tones (melanin absorbs light).
-   **Motion**: Any head movement creates "noise" much stronger than the heartbeat signal.

## 8. Future Improvements
-   **Blind Source Separation (ICA)**: Use Independent Component Analysis to separate the heart signal from motion noise.
