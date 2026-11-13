# Architecture

## Data flow (live session)

```
camera ──frame, t──► LandmarkExtractor (MediaPipe Tasks: PoseLandmarker + FaceLandmarker, VIDEO mode)
                         │ FrameLandmarks (nose, ears, wrists, shoulders, face box)
                         ├──► BehaviourDetector ── sliding 2 s window, resampled to a uniform grid,
                         │      FFT per signal → repetitive hand / head movement, head turned away
                         └──► RPPGEstimator (face box) ── RGB means → POS → band-pass 0.75–3 Hz →
                                peak + SNR → HRReading(bpm, snr_db, reliable)
                                   └──► HeartRateMonitor ── vs personal baseline → elevated HR events
microphone ──blocks──► LoudnessDetector (dBFS, hysteresis) → loud-sound events

all events (pending) ──► fusion.link_co_occurring (timing only) ──► Session.events
Session ──review (human)──► confirmed events ──► notes (template | local LLM → guard) · PDF · CSV · FHIR
Session ──► SessionStore (Fernet-encrypted, key outside repo) + AuditLog (hash chain)
```

Recorded video uses the same `SessionPipeline` through `analyse_video()`, with video time instead
of wall-clock time, and audio decoded with the bundled ffmpeg (`imageio-ffmpeg`).

## Design decisions

| Decision | Why |
|---|---|
| **Events as suggestions** (`pending → confirmed/rejected`) | A detector error should cost the reviewer a click, never end up in a person's record. |
| **Frequency-domain rules on landmark time-series** | "Repetitive" means periodic: an FFT peak in a band, with amplitude and band-power thresholds, separates flapping from a raised hand or slow movement. Rules are transparent and need no training data; a learned model is the next step once consented, annotated data exists. |
| **Normalisation by body size** | Wrist motion in shoulder widths and head motion in face widths makes thresholds independent of distance to the camera. |
| **Uniform resampling before FFT** | Webcam frame rates jitter; interpolating onto a fixed grid keeps frequency estimates correct. |
| **POS for rPPG, with an SNR gate** | POS (Wang et al., 2017) is more robust to lighting and motion than the plain green channel; low-SNR readings are labelled unreliable and excluded from events and averages. |
| **Personal baseline** | "Elevated" heart rate is relative to a resting measurement from the same session, not a population threshold. |
| **Co-occurrence by timing only** | Linking two events says they happened together, nothing about cause. |
| **MediaPipe Tasks API** | `mp.solutions` no longer exists in current MediaPipe releases; v1 failed silently because of this. |
| **Local Fernet store + hash-chained audit** | Simple, auditable, no server; enough for a single-machine prototype (see PRIVACY_AND_SAFETY.md for what production needs). |
| **FastAPI + static web UI instead of Streamlit** | The UI is one client of a documented API, so other clients (mobile, React, clinic systems) can reuse the backend; the live loop runs in a server thread instead of blocking a UI script; binds to 127.0.0.1 by default. |
| **Template notes by default, LLM optional** | Deterministic output is testable and never invents facts; the LLM only rewords the same facts and its output passes through the guard. |

## Module map

| Module | Responsibility |
|---|---|
| `src/config.py` | load `config/settings.yaml`; data directory resolution |
| `src/core/events.py`, `src/core/session.py` | data model, consent, lifecycle, review, summary |
| `src/sensors/camera.py`, `src/sensors/mic.py` | webcam / video file reading with timestamps; input devices |
| `src/perception/` | landmarks, behaviour, rPPG + heart-rate monitor, audio loudness |
| `src/analysis/fusion.py` | co-occurrence links |
| `src/pipeline.py` | `SessionPipeline`, `analyse_video` |
| `src/storage/` | `KeyStore`, `SessionStore`, `AuditLog` |
| `src/reporting/` | `ReportGenerator`, `guard`, `render_pdf`, `to_fhir_bundle` |
| `src/core/formatting.py` | pure helpers (mm:ss, CSV, identifier warnings, video retention rule) |
| `src/api/` | FastAPI app: REST, WebSocket live state, MJPEG preview, background video analysis; serves `web/` |
| `web/` | offline single-page UI (vanilla JS modules, no external requests; strict Content-Security-Policy) |
| `scripts/download_models.py` | fetch MediaPipe model files |
| `scripts/evaluate_rppg_ubfc.py` | MAE / RMSE / Pearson r on UBFC-rPPG |

## Changes from v1

v1 presented itself as an "autism assessment" system. Its behaviour signals came from a
**random-number simulator**: the webcam heart-rate path was an unfinished placeholder, and
"EEG" values were synthetic. Its encryption key was committed to the repository, the vision
module silently stopped working with current MediaPipe, and a fusion confidence of 0.98 was
hard-coded. v2 removes the simulator and all medical claims. It replaces "hands up = flapping"
with frequency analysis, wires the real webcam heart rate with a quality gate, moves the key
out of the repository, replaces the Streamlit loop with a FastAPI backend and an offline web UI, and adds consent, human review, erasure, audit and 128 tests.
