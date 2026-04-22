"""
audio_analysis.py — Real-time audio feature extraction and anomaly detection for Sparky.

Key components:
  - compute_audio_features()    : Per-chunk RMS, ZCR, and pitch estimation
  - RMSCalibrator               : 5-second baseline calibration to eliminate false-positive "inaudible"
  - detect_nervousness()        : 0.0–1.0 nervousness score from ZCR variance + energy spikes
  - detect_acoustic_anomalies() : Hysteresis-gated anomaly detection with structured output
"""

import numpy as np
from typing import List


# ═══════════════════════════════════════════════════════════════════════════════
# Audio Feature Extraction
# ═══════════════════════════════════════════════════════════════════════════════

def compute_audio_features(pcm_bytes: bytes, rate: int = 24000) -> dict:
    """
    Returns a dict with:
        rms_energy         (float): Loudness. Higher = louder.
        zero_crossing_rate (float): Voice texture. High = shaky/harsh, Low = smooth.
        pitch_estimate_hz  (float): Fundamental frequency in Hz. 0.0 if silence.
    """
    if len(pcm_bytes) == 0:
        return {"rms_energy": 0.0, "zero_crossing_rate": 0.0, "pitch_estimate_hz": 0.0}

    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    if len(samples) == 0:
        return {"rms_energy": 0.0, "zero_crossing_rate": 0.0, "pitch_estimate_hz": 0.0}

    rms = float(np.sqrt(np.mean(samples ** 2)))

    zero_crossings = np.sum(np.abs(np.diff(np.sign(samples)))) / 2
    zcr = float(zero_crossings / len(samples))

    pitch_hz = _estimate_pitch_autocorr(samples, rate)

    return {
        "rms_energy": rms,
        "zero_crossing_rate": zcr,
        "pitch_estimate_hz": pitch_hz,
    }


def _estimate_pitch_autocorr(samples: np.ndarray, rate: int) -> float:
    """
    Estimates fundamental frequency using normalized autocorrelation.
    Returns 0.0 if signal is too quiet or no clear pitch is found.
    Search range: 80–450 Hz (full human speaking voice range).
    """
    rms = np.sqrt(np.mean(samples ** 2))
    if rms < 0.01:
        return 0.0

    correlation = np.correlate(samples, samples, mode='full')
    correlation = correlation[len(correlation) // 2:]

    min_lag = int(rate / 450)
    max_lag = int(rate / 80)

    if max_lag >= len(correlation) or min_lag >= max_lag:
        return 0.0

    search_region = correlation[min_lag:max_lag]
    peak_lag = int(np.argmax(search_region)) + min_lag

    if peak_lag == 0:
        return 0.0

    return float(rate / peak_lag)


# ═══════════════════════════════════════════════════════════════════════════════
# RMS Calibrator (fixes false-positive "inaudible" for quiet mics)
# ═══════════════════════════════════════════════════════════════════════════════

class RMSCalibrator:
    """
    Measures a 5-second RMS baseline at pitch start and sets the inaudible threshold
    per-session, eliminating false positives caused by naturally quiet microphones.

    Usage:
        calibrator = RMSCalibrator()
        calibrator.add_sample(rms_value)  # called on every audio chunk during calibration
        if calibrator.is_ready():
            threshold = calibrator.inaudible_threshold
    """

    CALIBRATION_FRAMES    = 100   # ~5s at 20 frames/s (50ms chunks)
    SCALE_FACTOR          = 0.25  # inaudible_threshold = median_rms * 0.25
    FLOOR                 = 0.002 # Never go below this (prevents threshold=0 edge case)
    CEILING               = 0.015 # Never go above this (sane upper bound)
    DEFAULT_THRESHOLD     = 0.004 # Fallback if calibration fails

    def __init__(self):
        self._samples: List[float] = []
        self.inaudible_threshold: float = self.DEFAULT_THRESHOLD
        self._calibrated = False

    def add_sample(self, rms: float):
        if not self._calibrated:
            self._samples.append(rms)
            if len(self._samples) >= self.CALIBRATION_FRAMES:
                self._compute()

    def _compute(self):
        arr = np.array(self._samples)
        # Only use non-silent frames for baseline (exclude near-zero values)
        active = arr[arr > 0.001]
        if len(active) < 10:
            # Room is nearly silent — use default
            self.inaudible_threshold = self.DEFAULT_THRESHOLD
        else:
            median_rms = float(np.median(active))
            raw = median_rms * self.SCALE_FACTOR
            self.inaudible_threshold = float(np.clip(raw, self.FLOOR, self.CEILING))
        self._calibrated = True

    def is_ready(self) -> bool:
        return self._calibrated

    def force_complete(self):
        """Call this if the pitch starts before calibration finishes (graceful fallback)."""
        if not self._calibrated:
            if self._samples:
                self._compute()
            else:
                self._calibrated = True


# ═══════════════════════════════════════════════════════════════════════════════
# Nervousness Detection
# ═══════════════════════════════════════════════════════════════════════════════

def detect_nervousness(feature_history: List[dict]) -> float:
    """
    Returns a 0.0–1.0 nervousness score based on:
      - ZCR variance (shaky voice texture)
      - Energy spike rate (stuttering / stopping-starting)
      - Pitch trend (ris
      ing pitch = increasing anxiety)
    """
    if len(feature_history) < 5:
        return 0.0

    zcr_values    = [f["zero_crossing_rate"] for f in feature_history]
    energy_values = [f["rms_energy"] for f in feature_history]
    pitch_values  = [f["pitch_estimate_hz"] for f in feature_history if f["pitch_estimate_hz"] > 0]

    score = 0.0

    zcr_std   = float(np.std(zcr_values))
    score    += 0.4 * min(zcr_std / 0.1, 1.0)

    spike_count = sum(
        1 for i in range(1, len(energy_values))
        if energy_values[i - 1] - energy_values[i] > 0.05
    )
    spike_rate = spike_count / max(len(energy_values) - 1, 1)
    score     += 0.4 * min(spike_rate / 0.5, 1.0)

    if len(pitch_values) >= 4:
        x     = np.arange(len(pitch_values), dtype=float)
        slope = float(np.polyfit(x, pitch_values, 1)[0])
        score += 0.2 * min(max(slope, 0.0) / 5.0, 1.0)

    return float(min(max(score, 0.0), 1.0))


# ═══════════════════════════════════════════════════════════════════════════════
# Acoustic Anomaly Detection (Hysteresis-Gated)
# ═══════════════════════════════════════════════════════════════════════════════

# Hysteresis gate: anomaly must persist for this many consecutive frames before firing.
# At 50ms per frame, 14 frames = 700ms — prevents single-frame spikes from triggering.
HYSTERESIS_FRAMES = 14


def detect_acoustic_anomalies(
    feature_history: List[dict],
    inaudible_threshold: float = 0.004,
) -> dict | None:
    """
    Checks for extreme acoustic conditions using a hysteresis gate so single-frame
    spikes don't trigger false alerts.

    Returns a structured dict on anomaly:
        {
            "type": "acoustic",
            "reason": "inaudible" | "shouting" | "background_noise",
            "is_critical": True,
            "error_type": "Acoustic Anomaly",
            "evidence": ["avg_rms=0.001", "threshold=0.004"],
            "detail": "...",
            "recommended_interrupt": "..."
        }

    Returns None if no anomaly.
    """
    if len(feature_history) < HYSTERESIS_FRAMES:
        return None

    # Use the most recent HYSTERESIS_FRAMES frames for a stable reading
    recent  = feature_history[-HYSTERESIS_FRAMES:]
    avg_rms = float(np.mean([f["rms_energy"] for f in recent]))
    avg_zcr = float(np.mean([f["zero_crossing_rate"] for f in recent]))

    # ── Shouting / Clipping ────────────────────────────────────────────────────
    if avg_rms > 0.4:
        return {
            "type": "acoustic",
            "reason": "shouting",
            "is_critical": True,
            "error_type": "Acoustic Anomaly",
            "evidence": [f"avg_rms={avg_rms:.4f} > 0.4 (clipping threshold)"],
            "detail": "You are speaking far too loudly — the audio is clipping.",
            "recommended_interrupt": "You're clipping my mic. Speak at a normal volume."
        }

    # ── Background Hissing / Noise ─────────────────────────────────────────────
    if avg_zcr > 0.4 and avg_rms > 0.01:
        return {
            "type": "acoustic",
            "reason": "background_noise",
            "is_critical": True,
            "error_type": "Acoustic Anomaly",
            "evidence": [f"avg_zcr={avg_zcr:.4f} > 0.4", f"avg_rms={avg_rms:.4f}"],
            "detail": "There is heavy background noise obscuring your microphone.",
            "recommended_interrupt": "There's too much background noise. Move somewhere quieter."
        }

    # ── Inaudible (calibrated threshold + hysteresis) ─────────────────────────
    # Require non-zero ZCR so we don't fire when the mic is simply off
    if avg_rms < inaudible_threshold and avg_zcr > 0.02:
        return {
            "type": "acoustic",
            "reason": "inaudible",
            "is_critical": True,
            "error_type": "Acoustic Anomaly",
            "evidence": [
                f"avg_rms={avg_rms:.4f} < threshold={inaudible_threshold:.4f}",
                f"avg_zcr={avg_zcr:.4f}"
            ],
            "detail": "Your microphone volume is too low — you are inaudible.",
            "recommended_interrupt": "I can't hear you. Fix your mic or speak louder."
        }

    return None
