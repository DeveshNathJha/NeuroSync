# file: config/settings.py & config/settings.yaml

## 1. File Overview
**Purpose**: These files define the **Configuration Layer**.
-   `settings.py`: The Pythonic interface that the app imports throughout the code (`from config.settings import settings`).
-   `settings.yaml`: A human-readable configuration file for easy tuning (thresholds, model paths) without touching code.
**Role**: Centralizes all "Magical Constants". Instead of hardcoding `FPS=30` in 10 different files, it is defined once here.

## 2. Code Breakdown (`settings.py`)

### Dataclasses (Lines 4-28)
```python
@dataclass
class AudioSettings:
    RATE: int = 44100
    SCREAM_THRESH: float = 20.0

@dataclass
class VideoSettings:
    FRAME_WIDTH: int = 640
    # ...
```
-   **Structure**: Uses Python `dataclasses` to group settings logically (`AUDIO`, `VIDEO`, `MODEL`, `UI`).
-   **Why**: Provides auto-completion and type checking in the IDE.

### Main Settings Class (Lines 29-47)
```python
class Settings:
    AUDIO = AudioSettings()
    # ...
    BASE_DIR = ...
    DATA_DIR = ...
    
    @classmethod
    def ensure_dirs(cls):
        os.makedirs(cls.LOG_DIR, exist_ok=True)
```
-   **Paths**: automatically calculates absolute paths (`BASE_DIR`, `LOG_DIR`) relative to the file location. This ensures the app works no matter where you run it from.
-   **Initialization**: The last two lines instantiate the class and create the necessary log directories immediately. This prevents "Directory Not Found" errors later.

## 3. Usage in Other Files
**Example**:
```python
from config.settings import settings

# Accessing a value
if volume > settings.AUDIO.SCREAM_THRESH:
    trigger_alert()
```

## 4. Design Decisions
-   **Hybrid Approach**: Currently, `settings.py` has *defaults* hardcoded. The `settings.yaml` exists but isn't fully wired up to override `settings.py` dynamically in the provided code snippet. Steps should be taken to merge them.
-   **Hardcoded Defaults**: Chosen for stability. Even if the config file is missing, the app runs with safe defaults.

## 5. How to Modify
-   **Change Thresholds**: Edit the default values in `settings.py` (e.g., change `SCREAM_THRESH = 20.0` to `15.0` for higher sensitivity).
-   **Add New Section**:
    1.  Define a new `@dataclass class NetworkSettings: ...`
    2.  Add `NETWORK = NetworkSettings()` to the `Settings` class.

## 6. Limitations
-   **Static**: Requiring a code change to update settings is not ideal for deployment.
-   **YAML Integration**: The `settings.yaml` file is currently a "Passive Artifact". The code in `settings.py` does not strictly read and apply values from `settings.yaml` yet. This is a known Todo.

## 7. Future Improvements
-   **Dynamic Loading**: Update `settings.py`'s `__init__` to read `settings.yaml` and overwrite the dataclass fields. This would allow changing thresholds without restarting the server.
