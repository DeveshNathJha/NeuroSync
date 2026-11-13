"""
src/perception/rppg.py
----------------------
Contactless heart-rate estimation from webcam video (remote photo-
plethysmography), plus a monitor that suggests "heart rate above personal
baseline" events.

Pipeline (one estimate every `update_every_s`, over the last `window_s`):
  1. mean R, G, B of a skin region inside the face box (cheeks/forehead)
  2. resample onto a uniform 30 Hz grid using the frame TIMESTAMPS
     (webcam frame rates are irregular; the old code assumed a fixed fps)
  3. POS projection (Wang et al., 2017, "Algorithmic Principles of Remote
     PPG") – or the plain green channel if cfg.method == "green"
  4. detrend + Butterworth band-pass (cfg.band_hz, 45–180 BPM)
  5. zero-padded FFT, peak with parabolic interpolation -> BPM
  6. SNR in dB: power within ±0.1 Hz of the peak vs the rest of the band;
     an estimate is `reliable` only if snr_db >= cfg.min_snr_db

rPPG is sensitive to lighting and movement. Unreliable estimates are
reported as such and never produce events. Accuracy has to be measured on a
dataset with ground truth (scripts/evaluate_rppg_ubfc.py).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import signal

from src.config import settings
from src.core.events import Event

RESAMPLE_HZ = 30.0
MAX_GAP_S = 0.5
PEAK_HALF_WIDTH_HZ = 0.1


@dataclass
class HRReading:
    t: float
    bpm: float
    snr_db: float
    reliable: bool


def skin_roi(face_box: tuple[int, int, int, int], frame_shape) -> Optional[tuple[slice, slice]]:
    """Cheeks + lower forehead: the central part of the face box (avoids hair, eyes' blinking edges)."""
    x, y, w, h = face_box
    H, W = frame_shape[:2]
    x0, x1 = int(x + 0.2 * w), int(x + 0.8 * w)
    y0, y1 = int(y + 0.15 * h), int(y + 0.65 * h)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 - x0 < 3 or y1 - y0 < 3:
        return None
    return slice(y0, y1), slice(x0, x1)


def pos_signal(rgb: np.ndarray, fs: float) -> np.ndarray:
    """POS (Plane-Orthogonal-to-Skin) pulse signal from an (N, 3) RGB trace."""
    n = len(rgb)
    win = max(int(1.6 * fs), 2)
    proj = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])
    out = np.zeros(n)
    for start in range(0, n - win + 1):
        c = rgb[start:start + win].T                       # 3 x win
        mean = c.mean(axis=1, keepdims=True)
        if np.any(mean <= 0):
            continue
        s = proj @ (c / mean)
        std1 = s[1].std()
        h = s[0] + (s[0].std() / std1 if std1 > 1e-12 else 0.0) * s[1]
        out[start:start + win] += h - h.mean()
    return out


def estimate_bpm(trace: np.ndarray, fs: float, band: tuple[float, float]) -> tuple[float, float]:
    """(bpm, snr_db) of a pulse trace sampled at fs."""
    x = signal.detrend(trace)
    nyq = fs / 2
    b, a = signal.butter(3, [band[0] / nyq, min(band[1] / nyq, 0.99)], btype="band")
    x = signal.filtfilt(b, a, x)
    n_fft = int(2 ** np.ceil(np.log2(len(x) * 8)))
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), n=n_fft)) ** 2
    freqs = np.fft.rfftfreq(n_fft, 1 / fs)
    in_band = (freqs >= band[0]) & (freqs <= band[1])
    if not in_band.any() or spec[in_band].sum() <= 0:
        return 0.0, -np.inf
    idx_band = np.flatnonzero(in_band)
    k = idx_band[np.argmax(spec[idx_band])]
    # parabolic interpolation around the peak bin
    if 0 < k < len(spec) - 1:
        y0, y1, y2 = np.log(spec[k - 1] + 1e-20), np.log(spec[k] + 1e-20), np.log(spec[k + 1] + 1e-20)
        denom = y0 - 2 * y1 + y2
        delta = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-12 else 0.0
    else:
        delta = 0.0
    f_peak = freqs[k] + delta * (freqs[1] - freqs[0])
    near = in_band & (np.abs(freqs - f_peak) <= PEAK_HALF_WIDTH_HZ)
    signal_power = spec[near].sum()
    noise_power = spec[in_band & ~near].sum()
    snr_db = 10 * np.log10(signal_power / noise_power) if noise_power > 0 else np.inf
    return float(f_peak * 60.0), float(snr_db)


class RPPGEstimator:
    def __init__(self, cfg=None):
        self.cfg = cfg if cfg is not None else settings.rppg
        self._t: list[float] = []
        self._rgb: list[tuple[float, float, float]] = []
        self._last_emit: Optional[float] = None

    def reset(self) -> None:
        self._t, self._rgb, self._last_emit = [], [], None

    def add_sample(self, t: float, rgb_mean: tuple[float, float, float]) -> None:
        """Add a pre-computed mean skin colour (R, G, B). Used by tests and evaluation."""
        self._t.append(float(t))
        self._rgb.append(tuple(float(v) for v in rgb_mean))
        keep_from = t - self.cfg.window_s - 1.0
        while self._t and self._t[0] < keep_from:
            self._t.pop(0)
            self._rgb.pop(0)

    def update(self, t: float, frame_bgr: Optional[np.ndarray],
               face_box: Optional[tuple[int, int, int, int]]) -> Optional[HRReading]:
        if frame_bgr is not None and face_box is not None:
            roi = skin_roi(face_box, frame_bgr.shape)
            if roi is not None:
                patch = frame_bgr[roi]
                b, g, r = patch.reshape(-1, 3).mean(axis=0)
                self.add_sample(t, (r, g, b))
        return self.estimate(t)

    def estimate(self, t: float) -> Optional[HRReading]:
        cfg = self.cfg
        if self._last_emit is not None and t - self._last_emit < cfg.update_every_s:
            return None
        if not self._t:
            return None
        ts = np.asarray(self._t)
        t_end = ts[-1]
        t_start = t_end - cfg.window_s
        if ts[0] > t_start + 0.1 * cfg.window_s:
            return None                                   # not enough history yet
        sel = ts >= t_start - 1 / RESAMPLE_HZ
        ts_w = ts[sel]
        if len(ts_w) < 10 or np.max(np.diff(ts_w)) > MAX_GAP_S or t - t_end > MAX_GAP_S:
            return None                                   # face lost / big gap
        rgb = np.asarray(self._rgb)[sel]
        grid = np.arange(t_start, t_end, 1 / RESAMPLE_HZ)
        uniform = np.column_stack([np.interp(grid, ts_w, rgb[:, c]) for c in range(3)])

        trace = uniform[:, 1] if cfg.method == "green" else pos_signal(uniform, RESAMPLE_HZ)
        if np.allclose(trace, trace[0]):
            return None
        bpm, snr_db = estimate_bpm(trace, RESAMPLE_HZ, tuple(cfg.band_hz))
        self._last_emit = t
        return HRReading(t=round(t, 2), bpm=round(bpm, 1), snr_db=round(snr_db, 2),
                         reliable=bool(np.isfinite(snr_db) and snr_db >= cfg.min_snr_db and bpm > 0))


def estimate_baseline(readings: Iterable[HRReading]) -> Optional[float]:
    """Personal resting baseline: median of the reliable readings (None if there are none)."""
    vals = [r.bpm for r in readings if r.reliable and r.bpm > 0]
    return round(float(np.median(vals)), 1) if vals else None


class HeartRateMonitor:
    """
    Suggests 'elevated_heart_rate' events: reliable readings at least
    `elevated_above_baseline_bpm` above the person's own baseline for at least
    `elevated_min_s`. Without a baseline (calibration) it suggests nothing –
    population thresholds would be meaningless for children.
    """

    END_AFTER_UNRELIABLE_S = 3.0

    def __init__(self, cfg=None):
        self.cfg = cfg if cfg is not None else settings.rppg
        self.baseline: Optional[float] = None
        self._run: list[HRReading] = []
        self._last_reliable_t: Optional[float] = None

    estimate_baseline = staticmethod(estimate_baseline)

    def set_baseline(self, bpm: Optional[float]) -> None:
        self.baseline = float(bpm) if bpm else None

    @property
    def threshold(self) -> Optional[float]:
        return None if self.baseline is None else self.baseline + self.cfg.elevated_above_baseline_bpm

    def _close(self) -> list[Event]:
        run, self._run = self._run, []
        if not run or run[-1].t - run[0].t < self.cfg.elevated_min_s:
            return []
        mean_bpm = float(np.mean([r.bpm for r in run]))
        mean_snr = float(np.mean([r.snr_db for r in run]))
        bpm_margin = min(max((mean_bpm - self.threshold) / self.cfg.elevated_above_baseline_bpm, 0), 1)
        snr_margin = min(max((mean_snr - self.cfg.min_snr_db) / 10.0, 0), 1)
        return [Event(kind="elevated_heart_rate", start=run[0].t, end=run[-1].t,
                      confidence=0.5 + 0.5 * (bpm_margin + snr_margin) / 2, source="rppg",
                      evidence={"mean_bpm": round(mean_bpm, 1), "baseline_bpm": self.baseline,
                                "mean_snr_db": round(mean_snr, 2)})]

    def update(self, reading: Optional[HRReading]) -> list[Event]:
        if reading is None or self.threshold is None:
            return []
        if not reading.reliable:
            if self._run and reading.t - self._run[-1].t > self.END_AFTER_UNRELIABLE_S:
                return self._close()
            return []
        if reading.bpm >= self.threshold:
            self._run.append(reading)
            return []
        return self._close()

    def flush(self) -> list[Event]:
        return self._close()
