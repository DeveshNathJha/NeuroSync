# file: requirements.txt

## 1. File Overview
**Purpose**: Defines the **Software Supply Chain**. It lists all Python libraries required to run the application.
**Role**: `pip` reads this file to install dependencies.

## 2. Code Breakdown

### Core AI (Lines 4-6)
-   `opencv-python`: For `src/sensors/camera.py`. Provides `cv2`.
-   `mediapipe`: Google's library for Face Mesh and Pose estimation. Used in `src/agents/vision_agent.py`.
-   `numpy`: Foundational math library. Used everywhere for array manipulation.

### Generative AI (Lines 10)
-   `llama-cpp-python`: The engine that runs the `Phi-3` LLM locally on CPU/GPU. Used in `src/orchestration/reasoner.py`.

### Audio (Lines 15-17)
-   `sounddevice`: Modern, non-blocking audio capture. Used in `src/agents/audio_agent.py`.
-   `scipy`: Used for signal processing (Low-pass filters) on audio data.

### Dashboard (Lines 21-24)
-   `streamlit`: The web UI framework.
-   `plotly`: For the interactive medical charts in `history.py`.
-   `pandas`: For data manipulation of log files.

### Utilities (Lines 28-32)
-   `fpdf2`: Creates the PDF medical reports.
-   `pylsl`: Interface for research-grade EEG headsets (Muse, OpenBCI).
-   `cryptography`: Implements Fernet (AES) encryption for patient data.

## 3. Design Decisions
-   **Versioning**: Contains strict versions (e.g., `>=4.9.0.80`) to prevent "It works on my machine" bugs.
-   **Categorization**: The file is heavily commented and categorized (CORE, GEN AI, AUDIO) to help developers understand *why* a library is needed.

## 4. How to Modify
-   **Add Library**: Append `library_name>=version` to the bottom.
-   **Upgrade**: Change the version number. Beware of breaking changes in `mediapipe`.

## 5. Limitations
-   **Platform Specifics**: Some libraries (`llama-cpp-python`) compile C++ bindings. This can fail on machines without `gcc` or `cmake`.
