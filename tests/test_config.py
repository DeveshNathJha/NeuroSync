import unittest
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import settings

class TestConfig(unittest.TestCase):
    def test_audio_settings(self):
        self.assertEqual(settings.AUDIO.RATE, 44100)
        self.assertGreater(settings.AUDIO.SCREAM_THRESH, settings.AUDIO.SILENCE_THRESH)

    def test_ui_settings(self):
        self.assertIsNotNone(settings.UI.THEME_COLOR)
        self.assertEqual(settings.UI.PAGE_TITLE, "NeuroSync")

    def test_paths(self):
        import os
        self.assertTrue(os.path.exists(settings.LOG_DIR))
        self.assertTrue(os.path.exists(settings.PATIENT_LOGS_DIR))

if __name__ == '__main__':
    unittest.main()
