import os
from dataclasses import dataclass

@dataclass
class AudioSettings:
    RATE: int = 44100
    CHUNK: int = 1024
    SILENCE_THRESH: float = 1.0
    SCREAM_THRESH: float = 20.0

@dataclass
class VideoSettings:
    FRAME_WIDTH: int = 640
    FRAME_HEIGHT: int = 480
    FPS: int = 30

@dataclass
class ModelSettings:
    PHI3_PATH: str = "models/Phi-3-mini-4k-instruct.Q4_K_M.gguf"
    USE_GPU: bool = False

@dataclass
class UISettings:
    THEME_COLOR: str = "#00A3E0"
    BACKGROUND_COLOR: str = "#0e1117"
    PAGE_TITLE: str = "NeuroSync"
    PAGE_ICON: str = "🧠"

class Settings:
    AUDIO = AudioSettings()
    VIDEO = VideoSettings()
    MODEL = ModelSettings()
    UI = UISettings()
    
    # Paths
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    LOG_DIR = os.path.join(DATA_DIR, "logs")
    PATIENT_LOGS_DIR = os.path.join(DATA_DIR, "patient_logs")

    @classmethod
    def ensure_dirs(cls):
        os.makedirs(cls.LOG_DIR, exist_ok=True)
        os.makedirs(cls.PATIENT_LOGS_DIR, exist_ok=True)

settings = Settings()
settings.ensure_dirs()
