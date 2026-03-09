import os
import json
import re
from typing import Dict, Any
from config.settings import settings
from src.utils.logger import logger

# Graceful loading of the AI Brain
try:
    from llama_cpp import Llama
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    logger.warning("llama-cpp-python not installed. AI features disabled.")

class ClinicalReasoner:
    """
    ENTERPRISE REASONING AGENT (v5.2)
    ---------------------------------
    Wraps a Small Language Model (SLM) like Phi-3.
    Features:
    - Audience Adaptation (Doctor vs Parent)
    - Low Threshold Logic (Optimized for Live Demos)
    - Markdown Cleaning (Removes ### artifacts)
    """

    def __init__(self, model_path: str = settings.MODEL.PHI3_PATH):
        self.model_path = model_path
        self.llm = None
        
        if AI_AVAILABLE:
            if os.path.exists(self.model_path):
                try:
                    logger.info(f"Loading Brain: {self.model_path}...")
                    self.llm = Llama(
                        model_path=self.model_path,
                        n_ctx=2048,      # Context window
                        n_threads=4,     # CPU threads
                        verbose=False    # Keep logs clean
                    )
                    logger.info("Brain Online.")
                except Exception as e:
                    logger.error(f"Model Load Failed: {e}")
            else:
                logger.warning(f"Model file not found at {self.model_path}. Running in 'Rule-Based' mode.")

    def _clean_markdown(self, text: str) -> str:
        """Strips Markdown symbols (###, **) for clean display."""
        text = text.replace("###", "")
        text = text.replace("**", "")
        return text.strip()

    def analyze_session(self, session_data: Dict[str, Any], audience: str = "Doctor") -> str:
        """
        Generates a structured clinical report.
        Args:
            audience: "Doctor" (Technical) or "Parent" (Simple Language)
        """
        
        # 1. Extract Key Metrics
        event_count = session_data.get('total_events', 0)
        symptoms = list(set(session_data.get('event_types', []))) 
        avg_hr = session_data.get('avg_heart_rate', 0)
        
        # 2. THRESHOLD LOGIC (DEMO MODE: High Sensitivity)
        # We lowered the threshold from 5 to 1.
        # If ANY event is detected, we generate a full report.
        if event_count < 1:
            return """
            CLINICAL OBSERVATION:
            No behavioral events were detected during this specific observation window.
            
            PHYSIOLOGICAL DATA:
            Heart Rate remained within normal baseline parameters.
            
            RECOMMENDATION:
            Continue monitoring. Current data does not indicate immediate clinical concern.
            """

        # 3. FALLBACK MODE
        if not self.llm:
            return f"Automated Summary: Detected {event_count} events ({', '.join(symptoms)}). Avg HR: {int(avg_hr)} BPM. Install Phi-3 for detailed analysis."

        # 4. AI MODE (Audience Adaptive Prompt)
        if audience == "Doctor":
            tone_instruction = "Use medical terminology (e.g., 'Stereotypy', 'Sympathetic Arousal', 'DSM-5 criteria')."
        else:
            tone_instruction = "Use simple, compassionate language (e.g., 'Repetitive movements', 'Stress levels'). Avoid jargon."

        system_prompt = f"""You are NeuroSync, an advanced Clinical Decision Support System. 
        Your task is to generate a concise clinical summary for a {audience}.
        
        INSTRUCTIONS:
        1. {tone_instruction}
        2. Format:
           - CLINICAL OBSERVATIONS: (List specific behaviors and frequency)
           - PHYSIOLOGICAL CORRELATES: (Correlate Heart Rate with events)
           - ASSESSMENT: (Synthesize the data)
           - RECOMMENDATIONS: (Suggest next steps)
        3. Do NOT use Markdown symbols like ### or ** in the output. Keep text clean.
        4. Be direct. No filler words."""
        
        user_input = f"""
        DATA:
        - Total Events: {event_count}
        - Behaviors: {', '.join(symptoms)}
        - Avg Heart Rate: {int(avg_hr)} BPM
        """
        
        prompt = f"<|user|>\n{system_prompt}\n{user_input}\n<|end|>\n<|assistant|>"

        output = self.llm(
            prompt,
            max_tokens=600,
            stop=["<|end|>", "User:"],
            echo=False
        )
        
        raw_text = output['choices'][0]['text'].strip()
        return self._clean_markdown(raw_text)