"""
scripts/download_models.py
--------------------------
Downloads the two MediaPipe Tasks models NeuroSync needs into models/
(skips files that already exist). They are published by Google under the
Apache 2.0 licence and are not committed to the repository.

    python scripts/download_models.py
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "pose_landmarker_lite.task":
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/"
        "pose_landmarker_lite.task",
    "face_landmarker.task":
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/"
        "face_landmarker.task",
}


def main(target: Path = PROJECT_ROOT / "models") -> int:
    target.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        path = target / name
        if path.exists() and path.stat().st_size > 0:
            print(f"ok       {path}")
            continue
        print(f"download {name} ...")
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(path)
        print(f"saved    {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
