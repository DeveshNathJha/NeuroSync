# file: neuroapp.py

## 1. File Overview
**Purpose**: This is the **Application Entry Point**. It serves as the orchestrator for the entire NeuroSync Clinical system.
**Role**: It initializes all subsystems (Agents, Hardware Drivers, UI State), handles global error catching during startup, and routes the user to the correct UI module (Dashboard, History, etc.) based on sidebar selection.
**Architecture Fit**: It sits at the top of the stack. `run_app.sh` executes this file. This file then imports and orchestrates `src/ui/*`, `src/agents/*`, and `src/orchestration/*`.

## 2. Code Breakdown

### Imports (Lines 1-15)
```python
import streamlit as st
import time
from config.settings import settings
from src.utils.logger import logger
from src.ui import layout, dashboard, history
# ... Agents and Engines ...
```
-   **Standard Libs**: `streamlit` for the web framework, `time` as a dependency.
-   **Config/Logger**: Loads system-wide settings and the logging backend immediately.
-   **UI Modules**: Imports the three main screens.
-   **Core Logic**: Imports the AI Agents (Vision, Audio, Bio) and Orchestrators (Fusion, Reasoner).

### Session State Management (Lines 19-27)
```python
if 'bio_data' not in st.session_state: st.session_state.bio_data = [] 
# ... other states ...
```
-   **Why**: Streamlit reruns the entire script on every button click. To persist data (like the heart rate buffer `bio_data` or the list of detected events `fusion_events`), we must use `st.session_state`.
-   **Key States**:
    -   `bio_data`: Buffer for physiological signals.
    -   `fusion_events`: List of detected clinical events (e.g., "Hand Flapping" confirmed by Vision + Bio).
    -   `start_time`: Tracks session duration.

### System Loading (Lines 30-48)
```python
@st.cache_resource
def load_system():
    # ... initializes Vision, Audio, Bio, Fusion, Reasoner ...
    return instances
```
-   **Logic**: Uses `@st.cache_resource`. This is CRITICAL. It ensures that heavy AI models (MediaPipe, Phi-3, Audio drivers) are loaded **only once** when the server starts, not every time the user clicks a button.
-   **Error Handling**: Contains a `try-except` block specifically for the `ClinicalReasoner` (LLM), as loading a 4GB model might fail on low-RAM machines. It allows the app to start even if the "Brain" fails.

### Routing (Lines 53-65)
```python
app_mode = layout.render_sidebar()

if app_mode == "New Assessment":
    dashboard.render_dashboard(...)
elif app_mode == "Patient History":
    history.render_history(...)
```
-   **Logic**: Uses the `layout` module to draw the sidebar and get the user's selection (`app_mode`).
-   **Action**: Delegates the actual rendering to specific modules (`dashboard`, `history`, `calibration`). This keeps the main file clean.

## 3. Functions Explanation

### `load_system()`
-   **Purpose**: Singleton factory for all backend components.
-   **Returns**: Tuple of `(vision, audio, bio, fusion, reasoner, logger_agent)`.
-   **Key Detail**: Calls `audio.start_stream()` to activate the microphone thread immediately upon launch.

## 4. Data Flow
1.  **Launch**: User runs `run_app.sh`.
2.  **Init**: `neuroapp.py` loads. Global config and Logger start.
3.  **State**: Session state definitions ensure empty buffers exist.
4.  **Load**: `load_system()` triggers. AI models load into RAM. Hardware (Mic/Cam) warms up.
5.  **Render**: `layout.render_sidebar()` draws navigation.
6.  **Route**: User is shown the "New Assessment" dashboard by default.
7.  **Loop**: The `dashboard.render_dashboard` function (called here) contains the main `while` loop that processes frames.

## 5. Internal Dependencies
-   **Imports**:
    -   `src.agents.*`: The sensors.
    -   `src.orchestration.*`: The brain.
    -   `src.ui.*`: The look and feel.
    -   `src.utils.*`: Logging and Data storage.

## 6. Design Decisions
-   **Streamlit**: Chosen for rapid prototyping of UI + Data Science. It allows writing UI in pure Python.
-   **Session State**: Necessary evil of Streamlit.
-   **@cache_resource**: Vital optimization. Without this, the app would reload the AI models (taking 10s) every second.

## 7. How to Modify
-   **Add a New Page**:
    1.  Create `src/ui/new_page.py`.
    2.  Import it here.
    3.  Add the page name to `layout.render_sidebar` options.
    4.  Add an `elif app_mode == "New Page":` block here.
-   **Change Startup Logic**:
    -   Modify `load_system` if you need to initialize a new hardware driver (e.g., a Thermal Camera) once at startup.

## 8. Limitations
-   **Single Threaded UI**: Streamlit is single-threaded. If the `dashboard` loop blocks, the UI freezes.
-   **Global State**: Passing `vision`, `audio`, etc., as arguments is clean but can get unwieldy if we add 10 more agents.

## 9. Future Improvements
-   **Dependency Injection**: Use a `Context` container object instead of passing 6 separate arguments to `render_dashboard`.
-   **Async UI**: Move to a React/FastAPI architecture for better responsiveness in a production hospital setting.
