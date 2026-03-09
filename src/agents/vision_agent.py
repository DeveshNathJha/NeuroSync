import cv2
import mediapipe as mp
import numpy as np
import time
from typing import Dict, Any, Tuple
from src.utils.logger import logger

class NeuroVision:
    """
    ENTERPRISE VISION AGENT (v3.0 - Hierarchical Logic)
    ---------------------------------------------------
    Implements State-Based Detection with Vector Normalization.
    Prioritizes Gross Motor (Body) actions over Fine Motor (Face) actions.
    """

    def __init__(self):
        # Stable Python 3.10 Imports
        try:
            self.mp_holistic = mp.solutions.holistic
            self.mp_drawing = mp.solutions.drawing_utils
            
            # Initialize Holistic Model
            self.holistic = self.mp_holistic.Holistic(
                min_detection_confidence=0.6,
                min_tracking_confidence=0.6,
                refine_face_landmarks=True
            )
            self.vision_available = True
        except (AttributeError, ImportError, RuntimeError) as e:
            logger.error(f"MediaPipe Init Failed: {e}. Vision features disabled.")
            self.vision_available = False
            self.holistic = None
        
        # Tracking Vectors
        self.prev_time = time.time()
        self.prev_nose_x = 0.5
        self.prev_nose_y = 0.5
        
        # Temporal Buffers (State Machines)
        self.history_len = 5
        self.spin_buffer = []
        self.bang_buffer = []
        self.flap_buffer = []

    def process_frame(self, frame: np.ndarray) -> Tuple[Dict[str, Any], np.ndarray]:
        current_time = time.time()
        
        # Default Output
        output = {
            "timestamp": current_time,
            "detected": False,
            "gaze_aversion": False,
            "hand_flapping": False,
            "head_banging": False,
            "spinning": False,
            "processing_latency_ms": 0
        }

        # Safety Check
        if not getattr(self, "vision_available", True):
            # Return original frame + empty data
            return output, frame
            
        dt = current_time - self.prev_time
        self.prev_time = current_time
        
        # Pre-process
        frame.flags.writeable = False
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.holistic.process(frame_rgb)
        frame.flags.writeable = True

        # --- EXTRACT LANDMARKS ---
        if results.face_landmarks:
            output["detected"] = True
            nose = results.face_landmarks.landmark[1]
            left_ear = results.face_landmarks.landmark[234] 
            right_ear = results.face_landmarks.landmark[454]
            
            # 1. Calculate Face Scale (Normalization Factor)
            # All movements are relative to how big the face appears
            face_width = abs(right_ear.x - left_ear.x)
            if face_width == 0: face_width = 0.1 # Safety
            
            # --- GROSS MOTOR DETECTION (Body/Head Dynamics) ---
            
            # A. SPINNING LOGIC (Horizontal Velocity > Threshold)
            # Normalized velocity: How many "face widths" did the nose move per second?
            nose_dx = (nose.x - self.prev_nose_x)
            norm_vel_x = abs(nose_dx) / (face_width * (dt + 1e-5))
            
            is_spinning_frame = norm_vel_x > 2.5 # High threshold for rotation
            self.spin_buffer.append(is_spinning_frame)
            if len(self.spin_buffer) > self.history_len: self.spin_buffer.pop(0)
            
            # Trigger only if consistent motion detected
            if sum(self.spin_buffer) >= 3:
                output["spinning"] = True

            # B. HEAD BANGING LOGIC (Vertical Velocity)
            nose_dy = (nose.y - self.prev_nose_y)
            norm_vel_y = abs(nose_dy) / (face_width * (dt + 1e-5))
            
            is_banging_frame = norm_vel_y > 1.8
            self.bang_buffer.append(is_banging_frame)
            if len(self.bang_buffer) > self.history_len: self.bang_buffer.pop(0)
            
            if sum(self.bang_buffer) >= 3:
                output["head_banging"] = True

            # --- FINE MOTOR DETECTION (Face) ---
            
            # C. GAZE LOGIC (Hierarchical Suppression)
            # CRITICAL FIX: If Spinning or Banging, IGNORE Gaze.
            if not output["spinning"] and not output["head_banging"]:
                # Standard Ratio Logic
                nose_rel = (nose.x - left_ear.x) / face_width
                # Stricter bounds: 0.3 to 0.7 is normal
                if nose_rel < 0.3 or nose_rel > 0.7:
                    output["gaze_aversion"] = True

            # Update History
            self.prev_nose_x = nose.x
            self.prev_nose_y = nose.y

        # --- BODY LOGIC (Flapping) ---
        if results.pose_landmarks:
            lm = results.pose_landmarks.landmark
            l_wrist, r_wrist = lm[15], lm[16]
            l_shoulder, r_shoulder = lm[11], lm[12]
            
            # Feature 1: Elevation (Hands near head/shoulders)
            # In image coords, y decreases upwards.
            # "Above shoulders" means wrist.y < shoulder.y
            wrists_elevated = (l_wrist.y < l_shoulder.y) or (r_wrist.y < r_shoulder.y)
            
            # Feature 2: Proximity (Repetitive Clapping/Flapping)
            # CRITICAL FIX: Normalize by Body Scale (Shoulder Width)
            shoulder_width = abs(l_shoulder.x - r_shoulder.x)
            if shoulder_width == 0: shoulder_width = 0.1
            
            wrist_dist_raw = np.sqrt((l_wrist.x - r_wrist.x)**2 + (l_wrist.y - r_wrist.y)**2)
            wrist_dist_norm = wrist_dist_raw / shoulder_width
            
            # Threshold: If wrists are within 1.5x shoulder width (Flapping range)
            # AND moving fast (requires temporal, but for now we use elevation + jitter proxy)
            # Simplification for v1: Hands near each other OR hands up
            
            is_flapping = False
            if wrists_elevated:
                is_flapping = True
            elif wrist_dist_norm < 0.8: # Hands collected in front of chest
                is_flapping = True
                
            output["hand_flapping"] = is_flapping

        # --- VISUALIZATION ---
        if results.pose_landmarks:
            self.mp_drawing.draw_landmarks(
                frame, results.pose_landmarks, self.mp_holistic.POSE_CONNECTIONS,
                self.mp_drawing.DrawingSpec(color=(0,255,0), thickness=2, circle_radius=1),
                self.mp_drawing.DrawingSpec(color=(0,0,255), thickness=1, circle_radius=1)
            )

        output["processing_latency_ms"] = round((time.time() - current_time) * 1000, 2)
        return output, frame