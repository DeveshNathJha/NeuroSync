import numpy as np
import threading
import queue
from config.settings import settings
from src.utils.logger import logger

# Try importing sounddevice for Live Mode
# Try importing sounddevice for Live Mode
try:
    import sounddevice as sd
    LIVE_AUDIO_AVAILABLE = True
except (ImportError, OSError):
    LIVE_AUDIO_AVAILABLE = False
    logger.warning("sounddevice/PortAudio not found. Live audio disabled.")

# Try importing MoviePy for File Upload Mode
try:
    from moviepy.editor import VideoFileClip
    FILE_AUDIO_AVAILABLE = True
except ImportError:
    FILE_AUDIO_AVAILABLE = False
    logger.warning("MoviePy not found. File audio analysis disabled.")

class AudioAgent:
    """
    ENTERPRISE AUDIO AGENT (v5.0)
    -----------------------------
    Dual-Mode Analysis:
    1. Live Stream: Real-time processing via Microphone.
    2. File Upload: Pre-processing of MP4 audio tracks.
    """

    def __init__(self, rate=settings.AUDIO.RATE, chunk=settings.AUDIO.CHUNK):
        self.rate = rate
        self.chunk = chunk
        self.q = queue.Queue()
        self.running = False
        
        # State
        self.current_volume = 0.0
        self.is_speaking = False
        self.silence_start = None
        self.silence_duration = 0.0
        
        # Thresholds
        self.SILENCE_THRESH = settings.AUDIO.SILENCE_THRESH
        self.SCREAM_THRESH = settings.AUDIO.SCREAM_THRESH

    # --- MODE 1: LIVE MICROPHONE ---
    def audio_callback(self, indata, frames, time, status):
        """Callback for live microphone stream."""
        if status:
            logger.warning(f"Audio Callback Status: {status}")
        vol = np.linalg.norm(indata) * 10
        self.q.put(vol)

    def start_stream(self):
        if not LIVE_AUDIO_AVAILABLE:
            logger.error("Cannot start stream: SoundDevice not found.")
            return
            
        self.running = True
        # We start a background thread for the stream
        self.stream_thread = threading.Thread(target=self._run_live_stream)
        self.stream_thread.daemon = True
        self.stream_thread.start()
        logger.info("Live Microphone Listening...")

    def _run_live_stream(self):
        with sd.InputStream(callback=self.audio_callback, channels=1, samplerate=self.rate):
            while self.running:
                sd.sleep(100)

    # --- MODE 2: FILE ANALYSIS (NEW) ---
    def analyze_video_file(self, video_path):
        """
        Extracts audio from video and returns a 'Stress Timeline'.
        Returns: List of timestamps [sec] where screaming/loud noise occurs.
        """
        if not FILE_AUDIO_AVAILABLE:
            logger.error("Cannot analyze video: MoviePy not found.")
            return []

        logger.info(f"Extracting audio from: {video_path}")
        try:
            video = VideoFileClip(video_path)
            if video.audio is None:
                logger.warning("Video has no audio track.")
                return []

            # Extract audio as a numpy array
            # We take 1 sample per second for speed (hz=10) logic
            audio_array = video.audio.to_soundarray(fps=10) 
            
            # Calculate volume profile
            # audio_array is (N, 2) for stereo. Combine channels.
            volume_profile = np.linalg.norm(audio_array, axis=1) * 10
            
            # Identify Stress Points (Times where volume > Scream Threshold)
            stress_timestamps = []
            for i, vol in enumerate(volume_profile):
                if vol > self.SCREAM_THRESH:
                    timestamp = i / 10.0 # because fps=10
                    stress_timestamps.append(timestamp)
            
            logger.info(f"File Analysis Complete. Found {len(stress_timestamps)} loud events.")
            return stress_timestamps
            
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            return []

    # --- COMMON INTERFACE ---
    def process_chunk(self):
        """
        Returns the current live metrics.
        Called by app.py in the loop.
        """
        try:
            # Get latest volume from queue (if live)
            while not self.q.empty():
                self.current_volume = self.q.get_nowait()
        except queue.Empty:
            pass

        # Logic
        if self.current_volume > self.SILENCE_THRESH:
            self.is_speaking = True
            self.silence_start = None
            self.silence_duration = 0.0
        else:
            self.is_speaking = False
            if self.silence_start is None:
                # Import time here to avoid global scope issues in threads
                import time 
                self.silence_start = time.time()
            else:
                import time
                self.silence_duration = time.time() - self.silence_start

        return {
            "volume": self.current_volume,
            "is_speaking": self.is_speaking,
            "silence_latency_sec": round(self.silence_duration, 1)
        }