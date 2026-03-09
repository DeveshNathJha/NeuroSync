# file: src/agents/audio_agent.py

## 1. File Overview
**Purpose**: This agent handles **Auditory Perception**. It listens to the environment to detect vocalizations (screaming, speaking) and silence patterns.
**Role**: It provides the "Ears" of the system. It runs in a background thread to capture audio continuously without blocking the UI.
**Architecture Fit**: Instantiated by `neuroapp.py`. Its data is consumed by `dashboard.py` (visualizer) and `fusion_engine.py` (for correlating screams with meltdowns).

## 2. Code Breakdown

### Imports (Lines 1-6)
-   `numpy`: For calculating Root Mean Square (RMS) volume.
-   `threading/queue`: Essential for the Producer-Consumer pattern used here. The audio callback produces data; the main loop consumes it.

### Feature Detection (Lines 7-23)
```python
try:
    import sounddevice as sd
    LIVE_AUDIO_AVAILABLE = True
except ...
```
-   **Logic**: Graceful degradation. If `sounddevice` (PortAudio) is missing (common on cloud servers), it sets a flag `LIVE_AUDIO_AVAILABLE = False` instead of crashing. This facilitates "Safe Mode".

### Class Structure (Lines 24-48)
-   `self.q = queue.Queue()`: The thread-safe buffer.
-   `self.rate`, `self.chunk`: Standard audio settings (44.1kHz).

### Live Mode: The Callback (Lines 50-56)
```python
def audio_callback(self, indata, frames, time, status):
    vol = np.linalg.norm(indata) * 10
    self.q.put(vol)
```
-   **Logic**: This function is called by the OS *hundreds of times per second*. It must be extremely fast.
-   **Math**: Calculates the L2 Norm (Euclidean distance) of the audio waveform. This represents "Volume" or "Loudness".

### File Mode: `analyze_video_file` (Lines 75-107)
```python
def analyze_video_file(self, video_path):
    video = VideoFileClip(video_path)
    audio_array = video.audio.to_soundarray(fps=10)
    # ...
```
-   **Purpose**: Used when the user uploads an MP4 instead of using the webcam.
-   **Logic**: Uses `moviepy` to strip the audio track, resamples it to 10Hz (1 sample every 0.1s), and scans for peaks above `SCREAM_THRESH`.
-   **Return**: A list of timestamps (e.g., `[12.5, 12.6, 12.7]`) where loud noises occurred.

### Data Processing: `process_chunk` (Lines 114-145)
```python
def process_chunk(self):
    while not self.q.empty():
        self.current_volume = self.q.get_nowait()
    # ... logic to detect silence ...
```
-   **Logic**: Called by the Main Thread (UI loop). It drains the queue to get the *latest* volume.
-   **Silence Detection**:
    -   If volume < Input Threshold: Start a timer (`silence_start`).
    -   If volume > Input Threshold: Reset the timer.
    -   This allows measuring "Response Latency" (how long the child stays quiet).

## 3. Functions Explanation
-   `start_stream()`: Spawns the daemon thread `_run_live_stream`.
-   `_run_live_stream()`: The infinite loop that keeps the microphone open.

## 4. Data Flow
1.  **Input**: Physical Microphone (Sound Waves).
2.  **OS Driver**: Converts to PCM digital stream.
3.  **Callback**: Converts PCM chunk to single `float` (Volume). Puts into Queue.
4.  **Main Loop**:
    -   Reads Queue.
    -   Updates `current_volume`.
    -   Calculates `silence_latency_sec`.
5.  **Output**: Dictionary `{'volume': 0.5, 'is_speaking': True, ...}` sent to Fusion Engine.

## 5. Internal Dependencies
-   **External**: `sounddevice`, `numpy`, `moviepy`.
-   **Config**: Uses `settings.AUDIO.SCREAM_THRESH` to determine what counts as a "Meltdown".

## 6. Design Decisions
-   **Threading**: Audio processing *must* be threaded. Reading from a microphone is a blocking I/O operation. If done in the main Streamlit loop, the UI would freeze.
-   **Queue**: The safest way to pass data between threads in Python.

## 7. How to Modify
-   **Change Sensitivity**: Adjust `vol = np.linalg.norm(indata) * 10`. Change `* 10` to `* 20` to make it 2x more sensitive.
-   **Add Speech Recognition**:
    1.  Import `whisper` inside `process_chunk` (warning: slow).
    2.  Accumulate raw audio frames in a separate buffer.
    3.  Every 5 seconds, send the buffer to Whisper.

## 8. Limitations
-   **Volume Only**: It currently only detects *loudness*. It cannot distinguish between a "Scream" and a "Dog Barking" or "Door Slamming".
-   **Latency**: The Queue might build up latency if the UI loop runs too slowly (< 10 FPS).

## 9. Future Improvements
-   **Audio Classification**: Integrate a `YAMNet` or `VGGish` model to classify the *type* of sound (e.g., "Crying", "Laughing", "Speech").
