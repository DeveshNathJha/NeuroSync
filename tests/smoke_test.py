import unittest
import sys
import os
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock cv2 and mediapipe if not available
sys.modules['cv2'] = MagicMock()
sys.modules['mediapipe'] = MagicMock()
sys.modules['mediapipe.solutions'] = MagicMock()
sys.modules['mediapipe.solutions.holistic'] = MagicMock()
sys.modules['mediapipe.solutions.drawing_utils'] = MagicMock()

from src.agents.audio_agent import AudioAgent
from src.agents.bio_agent import BioAgent
from src.agents.vision_agent import NeuroVision
from src.orchestration.fusion_engine import FusionEngine
from src.utils.data_logger import DataLogger
from src.sensors.camera import CameraSensor

class TestSystemComponents(unittest.TestCase):
    def test_audio_agent_init(self):
        agent = AudioAgent()
        self.assertIsNotNone(agent)
        self.assertFalse(agent.running)

    def test_bio_agent_init(self):
        agent = BioAgent()
        self.assertIsNotNone(agent)
        self.assertEqual(agent.mode, "SYNTHETIC_TWIN")

    def test_vision_agent_init(self):
        agent = NeuroVision()
        self.assertIsNotNone(agent)

    def test_fusion_engine_init(self):
        engine = FusionEngine()
        self.assertIsNotNone(engine)

    def test_data_logger_init(self):
        logger = DataLogger()
        self.assertIsNotNone(logger)

    def test_camera_sensor_init(self):
        cam = CameraSensor(0)
        self.assertIsNotNone(cam)

if __name__ == '__main__':
    unittest.main()
