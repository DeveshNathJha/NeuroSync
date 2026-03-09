import time
import random
import threading
import numpy as np
from typing import Dict, Any
from src.utils.logger import logger
from src.sensors.rppg import RemotePPG

# ENTERPRISE HARDWARE LAYER (LSL Protocol)
try:
    from pylsl import StreamInlet, resolve_stream
    LSL_AVAILABLE = True
except ImportError:
    LSL_AVAILABLE = False
    logger.warning("LSL Library (pylsl) not found. Hardware mode disabled.")

class BioAgent:
    """
    NEURO-DIGITAL TWIN AGENT (v3.0)
    -------------------------------
    Manages physiological telemetry from three potential sources:
    1. MODE_WEBCAM (rPPG): Vision-based Heart Rate (Accessible/Mobile).
    2. MODE_HARDWARE (LSL): Real-time EEG/Heart Rate (Clinical).
    3. MODE_TWIN (Synthetic): Fallback simulation.
    """

    def __init__(self):
        self.running = False
        self.mode = "MODE_TWIN" 
        self.stress_trigger = False
        
        # rPPG Sensor
        self.rppg = RemotePPG()
        self.rppg_data = {"bpm": 0.0, "confidence": 0.0}
        
        # Internal State (Smoothing)
        self.hr = 80.0
        self.hrv = 60.0
        self.alpha = 0.8
        self.beta = 0.2
        
        # Hardware
        self.inlet = None
        self._lock = threading.Lock()

    def set_mode(self, mode_name: str):
        """Switch between WEBCAM, HARDWARE, and TWIN."""
        self.mode = mode_name
        logger.info(f"BioAgent switched to: {self.mode}")

    def update_rppg(self, frame, face_roi=None):
        """Called by the Vision loop to pass video frames for HR analysis."""
        if self.mode == "MODE_WEBCAM":
            bpm, conf, _ = self.rppg.process_frame(frame, face_roi)
            self.rppg_data["bpm"] = bpm
            self.rppg_data["confidence"] = conf

    def connect_hardware(self) -> bool:
        if not LSL_AVAILABLE:
            logger.info("LSL not available.")
            return False
        logger.info("Scanning for LSL EEG streams...")
        streams = resolve_stream('type', 'EEG') 
        if len(streams) > 0:
            try:
                self.inlet = StreamInlet(streams[0])
                self.set_mode("MODE_HARDWARE")
                logger.info(f"SUCCESS: Connected to {streams[0].name()}")
                return True
            except Exception as e:
                logger.error(f"Connection Failed: {e}")
                return False
        return False

    def start_stream(self):
        self.running = True
        logger.info(f"Bio Stream Active. Source: {self.mode}")

    def trigger_stress(self, active: bool):
        with self._lock:
            self.stress_trigger = active

    def get_reading(self, force_stress: bool = False, sim_settings: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Returns synchronized data packet.
        Prioritizes the active SOURCE mode.
        """
        # ... [Existing code for WEBCAM/HARDWARE] ...

        # 3. SYNTHETIC TWIN PATH (Fallback)
        # Only used if explicitly in SIMULATION mode
        if self.mode == "MODE_TWIN":
            is_stressed = force_stress or self.stress_trigger
            
            if sim_settings and "hr" in sim_settings:
                # Manual Override from Dashboard
                target_hr = sim_settings["hr"]
                # Infer other metrics from HR
                if target_hr > 100:
                    target_hrv = max(10, 60 - (target_hr - 80))
                    target_alpha = 0.2
                    target_beta = 0.8
                    is_stressed = True
                else:
                    target_hrv = 60
                    target_alpha = 0.8
                    target_beta = 0.2
            elif is_stressed:
                target_hr = random.uniform(115, 140)
                target_hrv = random.uniform(10, 25)
                target_alpha = random.uniform(0.1, 0.3)
                target_beta = random.uniform(0.75, 0.95)
            else:
                target_hr = random.uniform(70, 85)
                target_hrv = random.uniform(55, 75)
                target_alpha = random.uniform(0.75, 0.95)
                target_beta = random.uniform(0.2, 0.4)
    
            alpha_smooth = 0.15
            self.hr = self.hr * (1 - alpha_smooth) + target_hr * alpha_smooth
            self.hrv = self.hrv * (1 - alpha_smooth) + target_hrv * alpha_smooth
            self.alpha = self.alpha * (1 - alpha_smooth) + target_alpha * alpha_smooth
            self.beta = self.beta * (1 - alpha_smooth) + target_beta * alpha_smooth
    
            return self._pack_data(time.time(), source="DIGITAL_TWIN", stress_state=is_stressed)
            
        return self._pack_data(time.time(), source="NO_SOURCE", stress_state=False)

    def _pack_data(self, timestamp, source="DIGITAL_TWIN", stress_state=False):
        # Safety Check: If signal is lost, send zeros/NaNs to dashboard
        if source in ["NO_SIGNAL", "SIGNAL_LOST", "NO_SOURCE"]:
             return {
                "timestamp": timestamp,
                "source": source,
                "heart_rate": 0,
                "hrv_ms": 0,
                "eeg_alpha": 0,
                "eeg_beta": 0,
                "stress_detected": False,
                "quality_error": True # Flag for UI
            }
            
        return {
            "timestamp": timestamp,
            "source": source,
            "heart_rate": round(self.hr, 1),
            "hrv_ms": round(self.hrv, 1),
            "eeg_alpha": round(self.alpha, 2),
            "eeg_beta": round(self.beta, 2),
            "stress_detected": stress_state,
            "quality_error": False
        }