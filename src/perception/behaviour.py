"""
src/perception/behaviour.py
---------------------------
Turns per-frame landmarks into suggested behaviour events.

Three observable patterns (never a clinical interpretation):

  repetitive_hand_movement  a wrist oscillates relative to the shoulders at
                            flapping_band_hz (default 2–6 Hz) with enough
                            amplitude, and that band holds most of the motion
                            energy. Raising a hand, waving once or clapping
                            once does not qualify – the old "hands above the
                            shoulders" rule did.
  repetitive_head_movement  the nose oscillates vertically in head_band_hz.
  head_turned_away          the nose stays off the ear midpoint by more than
                            head_turn_ratio face widths for head_turn_min_s.
                            (This is head orientation, not eye gaze.)

Signals are normalised by body size (shoulder width / face width) so the
distance to the camera doesn't matter, and resampled onto a uniform time grid
before the FFT so irregular webcam frame rates and short gaps are handled.

Every event's confidence is computed from how far the evidence exceeds the
thresholds (0.5 = just at the threshold, 1.0 = far above); nothing is
hard-coded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from src.config import settings
from src.core.events import Event, merge_events
from src.perception.landmarks import FrameLandmarks

MAX_GAP_S = 0.5          # longer gaps without landmarks make a window unusable
MIN_FREQ_HZ = 0.3        # ignore drift below this when computing the energy share


@dataclass
class Oscillation:
    freq_hz: float
    amplitude: float      # peak-to-peak estimate (IQR·√2) of the detrended signal (body-size units)
    power_ratio: float    # share of motion energy inside the band


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(min(max(x, lo), hi))


def analyse_oscillation(t: np.ndarray, x: np.ndarray, band: tuple[float, float], window_s: float,
                        fs: float = 30.0) -> Optional[Oscillation]:
    """
    Dominant oscillation of signal x(t) over the last `window_s` seconds.
    Returns None if the samples don't cover the window (too few / long gaps).
    """
    if len(t) < 4:
        return None
    t_end = t[-1]
    t_start = t_end - window_s
    if t[0] > t_start + 0.2 * window_s:
        return None                          # window not yet covered
    sel = t >= t_start - 1.0 / fs
    tt, xx = t[sel], x[sel]
    if len(tt) < 4 or np.max(np.diff(tt)) > MAX_GAP_S:
        return None

    n = max(int(window_s * fs), 8)
    grid = np.linspace(t_start, t_end, n)
    y = np.interp(grid, tt, xx)
    y = y - np.polyval(np.polyfit(grid, y, 1), grid)          # remove drift / posture change
    # Peak-to-peak estimate from the interquartile range (IQR·√2 = 2A for a sine filling the
    # window). Being IQR-based, it needs about half of the window to be moving, so detection
    # starts/stops about window_s/2 after the movement does – BehaviourDetector corrects for that.
    amplitude = float((np.percentile(y, 75) - np.percentile(y, 25)) * np.sqrt(2))

    spec = np.abs(np.fft.rfft(y * np.hanning(n))) ** 2
    freqs = np.fft.rfftfreq(n, d=(grid[1] - grid[0]))
    motion = freqs >= MIN_FREQ_HZ
    in_band = (freqs >= band[0]) & (freqs <= band[1])
    total = spec[motion].sum()
    if total <= 0 or not in_band.any():
        return Oscillation(0.0, amplitude, 0.0)
    band_power = spec[in_band].sum()
    peak = freqs[in_band][np.argmax(spec[in_band])]
    return Oscillation(float(peak), amplitude, float(band_power / total))


def oscillation_score(osc: Optional[Oscillation], min_amp: float, min_ratio: float) -> tuple[float, bool]:
    """
    (score, active). score < 0.5 below threshold, 0.5..1 when the pattern is
    present: 0.5 + half the mean margin above the amplitude / energy thresholds.
    """
    if osc is None:
        return 0.0, False
    amp_part = osc.amplitude / min_amp
    ratio_part = osc.power_ratio / min_ratio
    active = amp_part >= 1.0 and ratio_part >= 1.0
    if not active:
        return 0.5 * _clamp(amp_part) * _clamp(ratio_part), False
    amp_margin = _clamp(amp_part - 1.0)                                  # 2× threshold -> 1
    ratio_margin = _clamp((osc.power_ratio - min_ratio) / max(1e-6, 1 - min_ratio))
    return 0.5 + 0.5 * (amp_margin + ratio_margin) / 2, True


@dataclass
class _Track:
    """Open/close state for one event kind."""
    kind: str
    source: str = "vision"
    lag_s: float = 0.0               # detection delay to subtract from start/end (window_s/2 for oscillations)
    start: Optional[float] = None
    last_active: Optional[float] = None
    scores: list[float] = field(default_factory=list)
    best_evidence: dict = field(default_factory=dict)
    best_score: float = 0.0

    def activate(self, t: float, start_t: float, score: float, evidence: dict) -> None:
        if self.start is None:
            self.start = start_t
        self.last_active = t
        self.scores.append(score)
        if score >= self.best_score:
            self.best_score, self.best_evidence = score, evidence

    def close(self, min_event_s: float) -> Optional[Event]:
        ev = None
        if self.start is not None and self.last_active is not None:
            start = max(0.0, self.start - self.lag_s)
            end = max(start, self.last_active - self.lag_s)
            if end - start >= min_event_s:
                ev = Event(kind=self.kind, start=round(start, 2), end=round(end, 2),
                           confidence=float(np.mean(self.scores)), source=self.source,
                           evidence={k: round(v, 3) if isinstance(v, float) else v
                                     for k, v in self.best_evidence.items()})
        self.start = self.last_active = None
        self.scores, self.best_evidence, self.best_score = [], {}, 0.0
        return ev


class BehaviourDetector:
    """
    Feed one FrameLandmarks per frame (t = seconds since session start).
    update() returns events that have just finished; flush() closes the rest.
    """

    def __init__(self, cfg=None, fps: float = 30.0):
        self.cfg = cfg if cfg is not None else settings.behaviour
        self.fps = max(float(fps), 2.5 * float(self.cfg.flapping_band_hz[1]))
        keep = self.cfg.window_s + 1.0
        self._keep_s = keep
        self._hand: dict[str, list[tuple[float, float]]] = {k: [] for k in ("lx", "ly", "rx", "ry")}
        self._head: list[tuple[float, float]] = []
        lag = self.cfg.window_s / 2
        self._tracks = {
            "repetitive_hand_movement": _Track("repetitive_hand_movement", lag_s=lag),
            "repetitive_head_movement": _Track("repetitive_head_movement", lag_s=lag),
            "head_turned_away": _Track("head_turned_away"),       # run start/end are measured directly
        }
        self._scores = {k: 0.0 for k in self._tracks}
        self._turn_run_start: Optional[float] = None
        self._turn_ratios: list[float] = []
        self._last_face_t: Optional[float] = None

    # ------------------------------------------------------------------ helpers
    def _trim(self, series: list[tuple[float, float]], t: float) -> None:
        while series and series[0][0] < t - self._keep_s:
            series.pop(0)

    @staticmethod
    def _arrays(series: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
        if not series:
            return np.empty(0), np.empty(0)
        a = np.asarray(series, dtype=float)
        return a[:, 0], a[:, 1]

    def _finalise_idle(self, t: float) -> list[Event]:
        out = []
        for tr in self._tracks.values():
            if tr.last_active is not None and t - tr.last_active > self.cfg.merge_gap_s:
                ev = tr.close(self.cfg.min_event_s)
                if ev:
                    out.append(ev)
        return out

    # ------------------------------------------------------------------ main
    def update(self, lm: FrameLandmarks) -> list[Event]:
        t = lm.t
        cfg = self.cfg

        # --- hands: wrist position relative to the shoulder midpoint, in shoulder widths
        if lm.has_pose:
            ls, rs = np.array(lm.left_shoulder), np.array(lm.right_shoulder)
            sw = float(np.hypot(*(ls - rs)))
            if sw > 1e-3:
                mid = (ls + rs) / 2
                lw = (np.array(lm.left_wrist) - mid) / sw
                rw = (np.array(lm.right_wrist) - mid) / sw
                for key, val in (("lx", lw[0]), ("ly", lw[1]), ("rx", rw[0]), ("ry", rw[1])):
                    self._hand[key].append((t, float(val)))
        for series in self._hand.values():
            self._trim(series, t)

        best_hand = (0.0, False, {})
        for key, series in self._hand.items():
            ts, xs = self._arrays(series)
            osc = analyse_oscillation(ts, xs, tuple(cfg.flapping_band_hz), cfg.window_s, self.fps)
            score, active = oscillation_score(osc, cfg.flapping_min_amplitude, cfg.flapping_min_power_ratio)
            if score > best_hand[0]:
                ev = {"freq_hz": osc.freq_hz, "amplitude": osc.amplitude, "power_ratio": osc.power_ratio,
                      "wrist": "left" if key[0] == "l" else "right", "axis": key[1]} if osc else {}
                best_hand = (score, active, ev)
        self._scores["repetitive_hand_movement"] = best_hand[0]
        if best_hand[1]:
            self._tracks["repetitive_hand_movement"].activate(t, t, *best_hand[0::2])

        # --- head: vertical nose movement in face widths; head orientation
        face_width = None
        if lm.has_face:
            face_width = abs(lm.right_ear[0] - lm.left_ear[0])
        if face_width and face_width > 1e-3:
            self._head.append((t, lm.nose[1] / face_width))
            self._last_face_t = t
        self._trim(self._head, t)
        ts, ys = self._arrays(self._head)
        osc = analyse_oscillation(ts, ys, tuple(cfg.head_band_hz), cfg.window_s, self.fps)
        score, active = oscillation_score(osc, cfg.head_min_amplitude, cfg.head_min_power_ratio)
        self._scores["repetitive_head_movement"] = score
        if active:
            self._tracks["repetitive_head_movement"].activate(
                t, t, score,
                {"freq_hz": osc.freq_hz, "amplitude": osc.amplitude, "power_ratio": osc.power_ratio})

        self._update_head_turn(lm, face_width)
        return self._finalise_idle(t)

    def _update_head_turn(self, lm: FrameLandmarks, face_width: Optional[float]) -> None:
        cfg = self.cfg
        t = lm.t
        tr = self._tracks["head_turned_away"]
        if face_width and face_width > 1e-3:
            mid_x = (lm.left_ear[0] + lm.right_ear[0]) / 2
            ratio = abs(lm.nose[0] - mid_x) / face_width
            turned = ratio > cfg.head_turn_ratio
        else:
            # face not visible: short gaps keep the current run, longer ones end it
            if self._turn_run_start is not None and self._last_face_t is not None \
                    and t - self._last_face_t <= MAX_GAP_S:
                return
            ratio, turned = 0.0, False

        if turned:
            if self._turn_run_start is None:
                self._turn_run_start = t
                self._turn_ratios = []
            self._turn_ratios.append(ratio)
            duration = t - self._turn_run_start
            ratio_margin = _clamp((float(np.mean(self._turn_ratios)) - cfg.head_turn_ratio) / cfg.head_turn_ratio)
            if duration >= cfg.head_turn_min_s:
                dur_margin = _clamp(duration / cfg.head_turn_min_s - 1.0)
                conf = 0.5 + 0.5 * (ratio_margin + dur_margin) / 2
                tr.activate(t, self._turn_run_start, conf,
                            {"offset_ratio": float(np.mean(self._turn_ratios)), "duration_s": duration})
                self._scores["head_turned_away"] = conf
            else:
                self._scores["head_turned_away"] = 0.5 * _clamp(duration / cfg.head_turn_min_s)
        else:
            self._turn_run_start = None
            self._turn_ratios = []
            self._scores["head_turned_away"] = 0.5 * _clamp(ratio / cfg.head_turn_ratio) * 0.5

    def flush(self, t: float) -> list[Event]:
        out = [ev for tr in self._tracks.values() if (ev := tr.close(self.cfg.min_event_s))]
        self._turn_run_start = None
        return merge_events(out, self.cfg.merge_gap_s)

    def live_state(self) -> dict[str, float]:
        """Current score per kind (0..1; >= 0.5 means the pattern is currently detected)."""
        return {k: round(v, 3) for k, v in self._scores.items()}
