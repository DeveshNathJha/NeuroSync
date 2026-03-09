import time
from typing import Dict, Any, Optional
from src.utils.logger import logger

class FusionEngine:
    """
    ENTERPRISE FUSION LAYER (v2.0)
    ------------------------------
    Orchestrates the synchronization between the 'Perception Layer' (Vision)
    and the 'Bio-Digital Twin' (Simulator).
    
    LOGIC:
    Uses a temporal sliding window to correlate:
    [Visual Symptom Timestamp] <== vs ==> [Neural Stress Timestamp]
    """

    def __init__(self, time_window_sec: float = 1.0):
        # The maximum allowed delay between a brain spike and visible behavior
        self.window = time_window_sec
        
        # State Tracking
        self.last_bio_spike_time = 0.0
        self.last_bio_stress_state = False

    def ingest_bio_event(self, bio_data: Dict[str, Any]):
        """
        Receives real-time telemetry from the Bio-Simulator.
        Updates the internal state of the 'Digital Patient Twin'.
        """
        if bio_data.get("stress_detected", False):
            self.last_bio_spike_time = bio_data["timestamp"]
            self.last_bio_stress_state = True
        else:
            self.last_bio_stress_state = False

    def correlate(self, vision_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        The Core Logic: Checks if a Visual Symptom matches a Neural Trigger.
        Returns a 'Fusion Event' dict if a correlation is found.
        """
        current_time = vision_data["timestamp"]
        
        # 1. Identify Visual Symptoms
        active_symptoms = []
        if vision_data.get("gaze_aversion", False): active_symptoms.append("Gaze Aversion")
        if vision_data.get("hand_flapping", False): active_symptoms.append("Hand Flapping")
        if vision_data.get("head_banging", False): active_symptoms.append("Head Banging")
        if vision_data.get("spinning", False): active_symptoms.append("Spinning")
        
        # If no visual symptom, there is nothing to correlate
        if not active_symptoms:
            return None

        # 2. Check Temporal Correlation (The "Fusion")
        # Did a stress spike happen recently? (within time_window)
        time_diff = abs(current_time - self.last_bio_spike_time)
        
        # CRITICAL: We correlate if Stress is CURRENTLY active OR happened very recently
        if self.last_bio_stress_state or (time_diff <= self.window):
            
            # 3. Construct the "Confirmed Event" Packet
            event = {
                "event_type": "NEURO_BEHAVIORAL_MATCH",
                "symptoms": active_symptoms,
                "timestamp": current_time,
                "confidence": 0.98, # High because multiple modalities agreed
                "details": f"{active_symptoms[0]} triggered during High Beta/Low Alpha state.",
                "severity": "HIGH",
                "fusion_latency": round(time_diff, 3)
            }
            logger.info(f"FUSION MATCH: {event['details']}")
            return event
        
        # Visual symptom existed, but NO biological stress matched it (Behavioral, not Neurological)
        return None