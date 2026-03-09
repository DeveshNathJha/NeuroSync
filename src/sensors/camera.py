import cv2
import time
import threading
import numpy as np
from src.utils.logger import logger

class CameraSensor:
    """
    ENTERPRISE CAMERA DRIVER (HAL)
    ------------------------------
    Abstracts the video source (Webcam or Video File).
    
    Features:
    - Error Handling: Prevents app crashes on hardware failure.
    - Resource Management: Auto-releases memory on stop.
    - Abstraction: Unified interface for Live/Upload modes.
    """

    def __init__(self, source=0):
        """
        Args:
            source: 0 for Webcam, or 'path/to/video.mp4' for file.
        """
        self.source = source
        self.cap = None
        self.running = False
        self.frame_width = 0
        self.frame_height = 0

    def start(self) -> bool:
        """Initializes the camera hardware safely."""
        try:
            # Release existing resources if restarting
            if self.cap is not None:
                self.stop()

            # Initialize Hardware
            self.cap = cv2.VideoCapture(self.source)
            
            # Validation
            if not self.cap.isOpened():
                raise RuntimeError(f"Critical Failure: Could not open source {self.source}")
            
            # Get Hardware Specs
            self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.running = True
            
            logger.info(f"Hardware initialized: {self.source} ({self.frame_width}x{self.frame_height})")
            return True

        except Exception as e:
            logger.error(f"Error initializing: {e}")
            self.running = False
            return False

    def get_frame(self):
        """
        Reads a single frame. 
        Returns: (success, frame)
        """
        if self.running and self.cap:
            ret, frame = self.cap.read()
            if not ret:
                logger.warning("Stream ended or disconnected.")
                self.stop()
                return False, None
            return True, frame
        return False, None

    def stop(self):
        """Safely releases hardware resources."""
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        logger.info("Hardware released.")

# --- UNIT TEST ---
if __name__ == "__main__":
    logger.info("Testing Camera Driver...")
    # Test with Webcam (0)
    cam = CameraSensor(0) 
    if cam.start():
        ret, frame = cam.get_frame()
        if ret:
            logger.info(f"Success! Frame captured. Shape: {frame.shape}")
        cam.stop()
    else:
        logger.error("Test Failed: Camera not found.")