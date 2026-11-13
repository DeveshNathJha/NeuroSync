"""
src/sensors/mic.py
------------------
Microphone access lives in src.perception.audio.LiveAudio (sounddevice
InputStream feeding a queue). This module re-exports it and offers a helper
to list input devices for the settings page.
"""

from __future__ import annotations

from src.perception.audio import LiveAudio

__all__ = ["LiveAudio", "list_input_devices"]


def list_input_devices() -> list[str]:
    """Names of available microphones ([] if sounddevice or a device is missing)."""
    try:
        import sounddevice as sd
        return [d["name"] for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    except Exception:
        return []
