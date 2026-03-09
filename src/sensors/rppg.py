import cv2
import numpy as np
import time
from scipy import signal
from src.utils.logger import logger

class RemotePPG:
    """
    ENTERPRISE VISION-BASED VITALS (rPPG)
    -------------------------------------
    Extracts heart rate from webcam video by analyzing subtle color changes 
    (blood volume pulse) in the user's face.
    
    Technique:
    1. Detect Face (using Haar Cascade for speed or MediaPipe if available)
    2. Extract Green Channel (strongest BVP signal)
    3. Signal Processing (Detrend -> Bandpass Filter -> FFT)
    """

    def __init__(self, fps=30, buffer_size=300):
        self.fps = fps
        self.buffer_size = buffer_size
        self.data_buffer = []
        self.times = []
        self.bpm = 0.0
        self.confidence = 0.0
        
        # Signal Processing Filters
        # Heart rate usually between 0.7Hz (42 BPM) and 4.0Hz (240 BPM)
        self.min_hz = 0.75
        self.max_hz = 3.5 
        
        # Face Detector (Haar Cascade is light and fast for this)
        # We assume face is already localized by VisionAgent, but we add a failsafe here.
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        
        self.last_clean_time = time.time()

    def process_frame(self, frame, face_roi=None):
        """
        Ingests a frame, extracts BVP signal, and updates BPM.
        Args:
            frame: BGR image from webcam.
            face_roi: Optional tuple (x, y, w, h) from VisionAgent.
        """
        curr_time = time.time()
        
        # 1. ROI Extraction
        if face_roi:
            x, y, w, h = face_roi
            # Focus on the forehead/cheeks (center 60% of face box)
            roi_x = int(x + w * 0.2)
            roi_y = int(y + h * 0.1)
            roi_w = int(w * 0.6)
            roi_h = int(h * 0.5)
            roi = frame[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]
        else:
            # Fallback detection
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
            if len(faces) > 0:
                x, y, w, h = faces[0]
                roi = frame[y:y+h, x:x+w]
            else:
                # signal lost
                return self.bpm, 0.0, None

        # 2. Extract Green Channel Mean
        # Green light assumes best absorption by hemoglobin
        if roi.size == 0: return self.bpm, 0.0, None
        
        avg_green = np.mean(roi[:, :, 1])
        
        self.data_buffer.append(avg_green)
        self.times.append(curr_time)
        
        # Maintain Buffer Size
        if len(self.data_buffer) > self.buffer_size:
            self.data_buffer.pop(0)
            self.times.pop(0)

        # 3. Process Signal (Every 15 frames to save CPU)
        if len(self.data_buffer) >= self.buffer_size and (len(self.data_buffer) % 15 == 0):
            self._update_bpm()

        return self.bpm, self.confidence, (x, y, w, h) if face_roi or len(faces) > 0 else None

    def _update_bpm(self):
        """Perform FFT/Signal Analysis on the buffer."""
        try:
            # A. Detrending (Remove light changes/movement drifts)
            data = np.array(self.data_buffer)
            # Simple detrend: subtract mean or use scipy.detrend
            detrended = signal.detrend(data)
            
            # B. Windowing (Hamming to reduce spectral leakage)
            L = len(detrended)
            window = np.hamming(L)
            
            # C. FFT
            # Interpolate to even sampling rate if timestamps are jittery? 
            # For now, assume relatively constant FPS.
            raw_fft = np.fft.rfft(detrended * window)
            freqs = np.fft.rfftfreq(L, 1.0/self.fps)
            
            # D. Bandpass Filter (Keep only physiological range)
            valid_idx = np.where((freqs >= self.min_hz) & (freqs <= self.max_hz))
            valid_freqs = freqs[valid_idx]
            valid_fft = np.abs(raw_fft[valid_idx])
            
            # E. Peak Detection
            if len(valid_fft) == 0: return
            
            peak_idx = np.argmax(valid_fft)
            peak_freq = valid_freqs[peak_idx]
            
            new_bpm = peak_freq * 60.0
            
            # F. Smoothing (Moving Average)
            alpha = 0.2
            if self.bpm == 0: self.bpm = new_bpm
            else: self.bpm = self.bpm * (1 - alpha) + new_bpm * alpha
            
            # G. Confidence Metric (Peak-to-Noise Ratio)
            peak_power = valid_fft[peak_idx]
            avg_power = np.mean(valid_fft)
            self.confidence = min(peak_power / (avg_power * 3), 1.0) # Heuristic

        except Exception as e:
            logger.error(f"rPPG Error: {e}")
