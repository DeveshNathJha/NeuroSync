"""
scripts/evaluate_rppg_ubfc.py
-----------------------------
Measures the webcam heart-rate estimator against a pulse oximeter, using the
UBFC-rPPG dataset (Bobbia et al., 2019; research use, request/download from
https://sites.google.com/view/ybenezeth/ubfcrppg).

Expected layout (one folder per subject):
    <root>/subject1/vid.avi
    <root>/subject1/ground_truth.txt

ground_truth.txt is assumed to hold three whitespace-separated rows:
    line 1 = PPG waveform, line 2 = heart rate (BPM), line 3 = timestamps (s)
This is the layout described for the DATASET_2 release; VERIFY IT AGAINST
THE DATASET'S OWN README before trusting the numbers (DATASET_1 differs).

For every estimate the script compares RPPGEstimator's BPM with the mean
ground-truth HR over the same window and reports MAE, RMSE, Pearson r and
the share of estimates within 5 BPM – overall and for reliable estimates.

    python scripts/evaluate_rppg_ubfc.py --root D:/data/UBFC_DATASET_2 [--max-subjects 5] [--method pos]

Results: reports/rppg_ubfc.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import AttrDict, settings  # noqa: E402
from src.perception.rppg import RPPGEstimator  # noqa: E402


def read_ground_truth(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """(timestamps_s, hr_bpm) from a UBFC ground_truth.txt (see module docstring)."""
    rows = [np.array(line.split(), dtype=float) for line in path.read_text().splitlines() if line.strip()]
    if len(rows) < 3:
        raise ValueError(f"{path}: expected 3 rows (PPG, HR, time), got {len(rows)}")
    hr, ts = rows[1], rows[2]
    n = min(len(hr), len(ts))
    return ts[:n], hr[:n]


def metrics(est: np.ndarray, ref: np.ndarray) -> dict:
    if len(est) == 0:
        return {"n": 0}
    err = est - ref
    r = float(np.corrcoef(est, ref)[0, 1]) if len(est) > 2 and np.std(est) > 0 and np.std(ref) > 0 else None
    return {
        "n": int(len(est)),
        "mae_bpm": round(float(np.mean(np.abs(err))), 2),
        "rmse_bpm": round(float(np.sqrt(np.mean(err ** 2))), 2),
        "pearson_r": round(r, 3) if r is not None else None,
        "within_5_bpm": round(float(np.mean(np.abs(err) <= 5)), 3),
    }


def face_box_detector():
    """Face box per frame via MediaPipe FaceLandmarker (same as the app)."""
    from src.perception.landmarks import LandmarkExtractor
    ext = LandmarkExtractor()
    return lambda frame, t: ext.process(frame, t).face_box


def evaluate_subject(folder: Path, cfg, detect_face) -> list[tuple[float, float, bool]]:
    import cv2
    ts_gt, hr_gt = read_ground_truth(folder / "ground_truth.txt")
    cap = cv2.VideoCapture(str(folder / "vid.avi"))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    est = RPPGEstimator(cfg)
    rows, i = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        i += 1
        reading = est.update(t, frame, detect_face(frame, t))
        if reading is None or reading.bpm <= 0:
            continue
        sel = (ts_gt >= t - cfg.window_s) & (ts_gt <= t)
        if sel.any():
            rows.append((reading.bpm, float(np.mean(hr_gt[sel])), reading.reliable))
    cap.release()
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description="Evaluate webcam heart rate on UBFC-rPPG.")
    p.add_argument("--root", required=True, help="folder containing subject*/ folders")
    p.add_argument("--max-subjects", type=int, default=None)
    p.add_argument("--method", choices=["pos", "green"], default=None)
    p.add_argument("--out", default=str(PROJECT_ROOT / "reports" / "rppg_ubfc.json"))
    a = p.parse_args()

    cfg = AttrDict(dict(settings.rppg))
    if a.method:
        cfg.method = a.method
    subjects = sorted(d for d in Path(a.root).iterdir()
                      if (d / "vid.avi").exists() and (d / "ground_truth.txt").exists())
    if a.max_subjects:
        subjects = subjects[:a.max_subjects]
    if not subjects:
        print(f"No subject folders with vid.avi + ground_truth.txt under {a.root}")
        return 1

    detect_face = face_box_detector()
    per_subject, all_rows = {}, []
    for s in subjects:
        rows = evaluate_subject(s, cfg, detect_face)
        all_rows += rows
        arr = np.array([(e, g) for e, g, _ in rows]) if rows else np.empty((0, 2))
        per_subject[s.name] = metrics(arr[:, 0], arr[:, 1]) if len(arr) else {"n": 0}
        print(f"{s.name}: {per_subject[s.name]}")

    est = np.array([r[0] for r in all_rows])
    ref = np.array([r[1] for r in all_rows])
    rel = np.array([r[2] for r in all_rows], dtype=bool)
    result = {
        "dataset": "UBFC-rPPG (verify ground_truth.txt format against the dataset readme)",
        "method": cfg.method, "window_s": cfg.window_s, "subjects": len(subjects),
        "all_estimates": metrics(est, ref),
        "reliable_only": metrics(est[rel], ref[rel]) if rel.any() else {"n": 0},
        "share_reliable": round(float(rel.mean()), 3) if len(rel) else None,
        "per_subject": per_subject,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "per_subject"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
