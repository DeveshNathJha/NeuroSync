import unittest
import numpy as np
import sys
import os
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock cv2 and logger
sys.modules['cv2'] = MagicMock()
from src.sensors.rppg import RemotePPG

class TestRemotePPG(unittest.TestCase):
    def setUp(self):
        self.rppg = RemotePPG(fps=30, buffer_size=30)
        
    def test_init(self):
        self.assertEqual(self.rppg.fps, 30)
        self.assertEqual(self.rppg.buffer_size, 30)
        self.assertEqual(self.rppg.bpm, 0.0)

    def test_process_frame_no_roi(self):
        # Create a dummy frame (green channel variations)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        # BGR: Green is index 1
        frame[:, :, 1] = 128 
        
        bpm, conf, roi = self.rppg.process_frame(frame, face_roi=None)
        
        # Should return default values if no face detected (mocked cascade returns nothing by default)
        self.assertEqual(bpm, 0.0)
        
    def test_buffer_update(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        # Simulate a face ROI
        roi = (10, 10, 50, 50) 
        
        # Fill buffer
        for i in range(35):
            intensity = 100 + 10 * np.sin(i) # Synthetic pulse
            frame[:, :, 1] = int(intensity)
            self.rppg.process_frame(frame, face_roi=roi)
            
        self.assertEqual(len(self.rppg.data_buffer), 30) # Capped at buffer size

if __name__ == '__main__':
    unittest.main()
