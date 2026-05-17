"""
audio_analysis.py — Real-time audio feature extraction and anomaly detection for Sparky.

Enhanced with librosa (v0.10+) for improved signal analysis:
  • PYIN probabilistic pitch tracking  (replaces autocorrelation)
  • MFCCs (13 coefficients)            (vocal quality fingerprint)
  • Spectral centroid & rolloff        (vocal brightness / stress indicator)
  • Harmonic/Percussive separation     (precision noise floor detection)
  • Librosa RMS                        (proper windowed energy computation)

All librosa paths fall back to numpy equivalents if librosa is not installed.

Key components:
  - compute_audio_features()         : Per-chunk RMS, ZCR, pitch, MFCCs, spectral features
  - RMSCalibrator                    : 5-second baseline calibration
  - detect_nervousness()             : 0.0–1.0 score (ZCR + energy + pitch + MFCC delta)
  - detect_acoustic_anomalies()      : HPSS-gated anomaly detection
  - detect_monotone()                : Pitch variation assessment using PYIN values
  - detect_speaking_rate()           : Speech/silence ratio from feature history
  - detect_vocal_stress_trajectory() : Spectral centroid trend over session
"""

import numpy as np
from typing import List

try:
    import librosa
    _LIBROSA_AVAILABLE = True
except ImportError:
    _LIBROSA_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
# Audio Feature Extraction
# ═══════════════════════════════════════════════════════════════════════════════

def compute_audio_features(pcm_bytes: bytes, rate: int = 24000) -> dict:
    """
    Extracts per-chunk audio features from raw PCM bytes (int16, mono).

    Always returns:
        rms_energy          (float): Loudness 0–1. High = louder.
        zero_crossing_rate  (float): Voice texture. High = shaky/harsh.
        pitch_estimate_hz   (float): F0 in Hz (PYIN when librosa available). 0.0 = silence.

    Additional keys when librosa is installed:
        mfcc_mean           (list[float]): 13 MFCC coefficients averaged over chunk.
        spectral_centroid_hz(float): Spectral brightness in Hz.
        spectral_rolloff_hz (float): 85th-percentile rolloff frequency in Hz.
        harmonic_ratio      (float): Harmonic energy / total energy. Low value = noisy signal.
    """
    if len(pcm_bytes) == 0:
        return _zero_features()

    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    if len(samples) == 0:
        return _zero_features()

    # ── RMS Energy ────────────────────────────────────────────────────────────
    if _LIBROSA_AVAILABLE:
        frame_len = min(512, len(samples))
        hop_len   = min(256, len(samples))
        rms_arr   = librosa.feature.rms(y=samples, frame_length=frame_len, hop_length=hop_len)
        rms = float(rms_arr[0].mean()) if rms_arr.size > 0 else 0.0
    else:
        rms = float(np.sqrt(np.mean(samples ** 2)))

    # ── Zero Crossing Rate ────────────────────────────────────────────────────
    zero_crossings = np.sum(np.abs(np.diff(np.sign(samples)))) / 2
    zcr = float(zero_crossings / len(samples))

    # ── Pitch Estimation ──────────────────────────────────────────────────────
    if _LIBROSA_AVAILABLE:
        pitch_hz = _estimate_pitch_pyin(samples, rate)
    else:
        pitch_hz = _estimate_pitch_autocorr(samples, rate)

    result = {
        "rms_energy":         rms,
        "zero_crossing_rate": zcr,
        "pitch_estimate_hz":  pitch_hz,
    }

    # ── Extended Librosa Features ─────────────────────────────────────────────
    if _LIBROSA_AVAILABLE and len(samples) >= 512:
        try:
            n_fft      = min(512, len(samples))
            hop_length = n_fft // 4

            # MFCCs — 13 cepstral coefficients averaged over the chunk
            mfccs = librosa.feature.mfcc(
                y=samples, sr=rate, n_mfcc=13, n_fft=n_fft, hop_length=hop_length
            )
            result["mfcc_mean"] = mfccs.mean(axis=1).tolist()

            # Spectral centroid — vocal brightness in Hz
            centroid = librosa.feature.spectral_centroid(
                y=samples, sr=rate, n_fft=n_fft, hop_length=hop_length
            )
            result["spectral_centroid_hz"] = float(centroid.mean())

            # Spectral rolloff — 85% energy concentration frequency
            rolloff = librosa.feature.spectral_rolloff(
                y=samples, sr=rate, n_fft=n_fft, hop_length=hop_length, roll_percent=0.85
            )
            result["spectral_rolloff_hz"] = float(rolloff.mean())

            # Harmonic ratio via HPSS — low ratio means more percussive/noisy signal
            harmonic, _ = librosa.effects.hpss(samples)
            total_energy    = float(np.sum(samples ** 2))
            harmonic_energy = float(np.sum(harmonic ** 2))
            result["harmonic_ratio"] = (
                harmonic_energy / total_energy if total_energy > 1e-10 else 1.0
            )

        except Exception:
            pass  # extended features are best-effort

    return result


def _zero_features() -> dict:
    return {"rms_energy": 0.0, "zero_crossing_rate": 0.0, "pitch_estimate_hz": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# Pitch estimators
# ─────────────────────────────────────────────────────────────────────────────

def _estimate_pitch_pyin(samples: np.ndarray, rate: int) -> float:
    """
    PYIN probabilistic pitch tracker (librosa).
    More robust than autocorrelation on noisy real-world mic signals.
    Returns the median F0 of voiced frames, or 0.0 if silence/fully unvoiced.
    """
    rms = float(np.sqrt(np.mean(samples ** 2)))
    if rms < 0.005:
        return 0.0
    try:
        frame_length = min(2048, len(samples))
        f0, voiced_flag, _ = librosa.pyin(
            samples,
            fmin=librosa.note_to_hz("C2"),  # ~65 Hz
            fmax=librosa.note_to_hz("A4"),  # ~440 Hz
            sr=rate,
            frame_length=frame_length,
        )
        if voiced_flag is not None:
            voiced = f0[voiced_flag]
            if len(voiced) > 0:
                median_f0 = float(np.nanmedian(voiced))
                if 80.0 <= median_f0 <= 450.0:
                    return median_f0
    except Exception:
        pass
    return 0.0


def _estimate_pitch_autocorr(samples: np.ndarray, rate: int) -> float:
    """
    Fallback autocorrelation pitch estimator (no librosa required).
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

    CALIBRATION_FRAMES = 100   # ~5s at 20 frames/s (50ms chunks)
    SCALE_FACTOR       = 0.25  # inaudible_threshold = median_rms * 0.25
    FLOOR              = 0.002 # Never go below this (prevents threshold=0 edge case)
    CEILING            = 0.015 # Never go above this (sane upper bound)
    DEFAULT_THRESHOLD  = 0.004 # Fallback if calibration fails

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
        arr    = np.array(self._samples)
        active = arr[arr > 0.001]
        if len(active) < 10:
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
    Returns a 0.0–1.0 nervousness score.

    With librosa (all four components):
        ZCR variance       0.30 — shaky voice texture
        Energy spike rate  0.30 — stuttering / stopping-starting
        Pitch slope        0.20 — rising pitch = increasing anxiety
        MFCC delta std     0.20 — rapid vocal quality shifts (tremor indicator)

    Without librosa (three components):
        ZCR variance       0.40
        Energy spike rate  0.40
        Pitch slope        0.20
    """
    if len(feature_history) < 5:
        return 0.0

    zcr_values    = [f["zero_crossing_rate"] for f in feature_history]
    energy_values = [f["rms_energy"] for f in feature_history]
    pitch_values  = [f["pitch_estimate_hz"] for f in feature_history if f["pitch_estimate_hz"] > 0]

    has_mfcc = any(f.get("mfcc_mean") for f in feature_history)
    w_zcr = w_energy = (0.30 if has_mfcc else 0.40)

    score = 0.0

    # ZCR variance — shaky voice texture
    zcr_std = float(np.std(zcr_values))
    score  += w_zcr * min(zcr_std / 0.1, 1.0)

    # Energy spike rate — stuttering / stop-start patterns
    spike_count = sum(
        1 for i in range(1, len(energy_values))
        if energy_values[i - 1] - energy_values[i] > 0.05
    )
    spike_rate = spike_count / max(len(energy_values) - 1, 1)
    score     += w_energy * min(spike_rate / 0.5, 1.0)

    # Pitch slope — rising F0 correlates with increasing anxiety
    if len(pitch_values) >= 4:
        x     = np.arange(len(pitch_values), dtype=float)
        slope = float(np.polyfit(x, pitch_values, 1)[0])
        score += 0.20 * min(max(slope, 0.0) / 5.0, 1.0)

    # MFCC delta variance — rapid vocal quality shifts (tremor/stress indicator)
    if has_mfcc:
        mfcc_sequences = [f["mfcc_mean"] for f in feature_history if f.get("mfcc_mean")]
        if len(mfcc_sequences) >= 4:
            mfcc_matrix = np.array(mfcc_sequences)      # (n_frames, 13)
            mfcc_delta  = np.diff(mfcc_matrix, axis=0)  # (n_frames-1, 13)
            delta_std   = float(np.mean(np.std(mfcc_delta, axis=0)))
            # Neutral speech: delta_std ~2–4; stressed/tremor: ~8–15
            score += 0.20 * min(delta_std / 10.0, 1.0)

    return float(min(max(score, 0.0), 1.0))


# ═══════════════════════════════════════════════════════════════════════════════
# Acoustic Anomaly Detection (Hysteresis-Gated + HPSS)
# ═══════════════════════════════════════════════════════════════════════════════

# Anomaly must persist for this many consecutive frames before firing.
# At 50ms per frame, 14 frames = 700ms — prevents single-frame spikes.
HYSTERESIS_FRAMES = 14


def detect_acoustic_anomalies(
    feature_history: List[dict],
    inaudible_threshold: float = 0.004,
) -> dict | None:
    """
    Checks for extreme acoustic conditions using a hysteresis gate.

    Background-noise detection uses HPSS harmonic_ratio when librosa is available
    (harmonic_ratio < 0.30 means >70% of signal energy is percussive/noise),
    and falls back to the ZCR heuristic otherwise.

    Returns a structured dict on anomaly, or None if signal is clean.
    """
    if len(feature_history) < HYSTERESIS_FRAMES:
        return None

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
            "recommended_interrupt": "You're clipping my mic. Speak at a normal volume.",
        }

    # ── Background Noise — HPSS preferred, ZCR fallback ─────────────────────
    harmonic_ratios = [
        f["harmonic_ratio"] for f in recent if f.get("harmonic_ratio") is not None
    ]
    if harmonic_ratios:
        avg_harmonic_ratio = float(np.mean(harmonic_ratios))
        if avg_harmonic_ratio < 0.30 and avg_rms > 0.01:
            return {
                "type": "acoustic",
                "reason": "background_noise",
                "is_critical": True,
                "error_type": "Acoustic Anomaly",
                "evidence": [
                    f"harmonic_ratio={avg_harmonic_ratio:.3f} < 0.30 (HPSS)",
                    f"avg_rms={avg_rms:.4f}",
                ],
                "detail": "Heavy background noise detected via harmonic/percussive separation.",
                "recommended_interrupt": "There's too much background noise. Move somewhere quieter.",
            }
    elif avg_zcr > 0.4 and avg_rms > 0.01:
        return {
            "type": "acoustic",
            "reason": "background_noise",
            "is_critical": True,
            "error_type": "Acoustic Anomaly",
            "evidence": [f"avg_zcr={avg_zcr:.4f} > 0.4", f"avg_rms={avg_rms:.4f}"],
            "detail": "There is heavy background noise obscuring your microphone.",
            "recommended_interrupt": "There's too much background noise. Move somewhere quieter.",
        }

    # ── Inaudible (calibrated threshold + hysteresis) ─────────────────────────
    if avg_rms < inaudible_threshold and avg_zcr > 0.02:
        return {
            "type": "acoustic",
            "reason": "inaudible",
            "is_critical": True,
            "error_type": "Acoustic Anomaly",
            "evidence": [
                f"avg_rms={avg_rms:.4f} < threshold={inaudible_threshold:.4f}",
                f"avg_zcr={avg_zcr:.4f}",
            ],
            "detail": "Your microphone volume is too low — you are inaudible.",
            "recommended_interrupt": "I can't hear you. Fix your mic or speak louder.",
        }

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Monotone Detection
# ═══════════════════════════════════════════════════════════════════════════════

def detect_monotone(feature_history: List[dict]) -> dict:
    """
    Detects whether the founder spoke in a monotone voice throughout the pitch.

    Uses the std-dev of pitch_estimate_hz across all session frames (populated by
    PYIN when librosa is available, giving more accurate voiced-only values):
      - Low variation  (std-dev < 30 Hz)  → monotone delivery
      - Medium variation (30–80 Hz)       → slightly flat but acceptable
      - High variation  (> 80 Hz)         → good vocal variety

    Returns:
        is_monotone      (bool)
        variation_score  (float)  — std-dev in Hz
        assessment       (str)    — human-readable verdict
    """
    pitch_values = [
        f["pitch_estimate_hz"]
        for f in feature_history
        if f.get("pitch_estimate_hz", 0) > 0
    ]

    if len(pitch_values) < 10:
        return {
            "is_monotone": False,
            "variation_score": 0.0,
            "assessment": "Not enough voice data to assess vocal variety.",
        }

    std_dev = float(np.std(pitch_values))

    if std_dev < 30:
        return {
            "is_monotone": True,
            "variation_score": round(std_dev, 2),
            "assessment": (
                "Monotone delivery detected — very little pitch variation throughout your pitch. "
                "Investors struggle to stay engaged when the voice stays flat. "
                "Practice emphasizing key numbers and pausing before important statements."
            ),
        }
    elif std_dev < 80:
        return {
            "is_monotone": False,
            "variation_score": round(std_dev, 2),
            "assessment": (
                "Slightly flat delivery — some pitch variation, but could be more dynamic. "
                "Try emphasizing your problem statement and key metrics with a stronger vocal shift."
            ),
        }
    else:
        return {
            "is_monotone": False,
            "variation_score": round(std_dev, 2),
            "assessment": "Good vocal variety — your delivery was dynamic and engaging.",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Speaking Rate Analysis
# ═══════════════════════════════════════════════════════════════════════════════

def detect_speaking_rate(
    feature_history: List[dict],
    inaudible_threshold: float = 0.004,
    frame_duration_ms: float = 50.0,
) -> dict:
    """
    Estimates speaking rate from RMS energy in the feature history.

    Classifies each frame as speech (rms > threshold) or silence, then derives:
      - speech_ratio: fraction of session spent speaking
      - pause_count: number of speech→silence transitions
      - pause_rate_per_minute: structural pacing indicator

    Note: for finer-grained segmentation, librosa.effects.split() on buffered raw
    PCM would improve precision — applicable if audio bytes are stored per-session.

    Returns dict with: speaking_rate_category, speech_ratio, pause_count,
                       pause_rate_per_minute, assessment.
    """
    if len(feature_history) < 10:
        return {
            "speaking_rate_category": "unknown",
            "speech_ratio": 0.0,
            "pause_count": 0,
            "pause_rate_per_minute": 0.0,
            "assessment": "Not enough audio data to assess speaking rate.",
        }

    energy_values = np.array([f.get("rms_energy", 0.0) for f in feature_history])
    is_speech = energy_values > inaudible_threshold

    # Count speech→silence transitions
    transitions = np.diff(is_speech.astype(int))
    pause_count = int(np.sum(transitions == -1))

    speech_ratio = float(np.mean(is_speech))
    total_duration_s = len(feature_history) * frame_duration_ms / 1000.0
    pause_rate_per_min = (pause_count / total_duration_s * 60.0) if total_duration_s > 0 else 0.0

    if speech_ratio > 0.88:
        category = "rushed"
        assessment = (
            "Minimal pausing — you're speaking almost continuously. "
            "Strategic pauses help investors absorb key metrics and show confidence."
        )
    elif speech_ratio > 0.68:
        category = "good"
        assessment = "Natural speaking pace with appropriate pauses — well-paced delivery."
    elif speech_ratio > 0.45:
        category = "measured"
        assessment = (
            "Deliberate, paused delivery. Good for emphasis, but ensure silences "
            "don't signal a loss of momentum or confidence."
        )
    else:
        category = "too_slow"
        assessment = (
            "Very high silence ratio — speech is fragmented or very slow. "
            "Build momentum in your delivery to keep investors engaged."
        )

    return {
        "speaking_rate_category": category,
        "speech_ratio": round(speech_ratio, 3),
        "pause_count": pause_count,
        "pause_rate_per_minute": round(pause_rate_per_min, 1),
        "assessment": assessment,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Vocal Stress Trajectory
# ═══════════════════════════════════════════════════════════════════════════════

def detect_vocal_stress_trajectory(feature_history: List[dict]) -> dict:
    """
    Analyzes spectral centroid trend over the session to detect rising vocal stress.

    A rising centroid over time correlates with increasing vocal tension/anxiety.
    Requires librosa to be installed (spectral_centroid_hz keys must be present).

    Returns dict with: trend, slope_hz_per_frame, mean_centroid_hz, assessment.
    """
    centroids = [
        f["spectral_centroid_hz"]
        for f in feature_history
        if f.get("spectral_centroid_hz") is not None
    ]

    if len(centroids) < 10:
        return {
            "trend": "unknown",
            "slope_hz_per_frame": 0.0,
            "mean_centroid_hz": 0.0,
            "assessment": (
                "Not enough spectral data for stress trajectory analysis. "
                "Install librosa to enable this feature."
                if not _LIBROSA_AVAILABLE else
                "Not enough voiced frames to assess vocal stress trajectory."
            ),
        }

    x     = np.arange(len(centroids), dtype=float)
    slope = float(np.polyfit(x, centroids, 1)[0])
    mean_centroid = float(np.mean(centroids))

    if slope > 10.0:
        trend = "rising"
        assessment = (
            f"Vocal brightness increased throughout your pitch "
            f"(spectral centroid rising ~{slope:.0f} Hz/frame). "
            "This often signals mounting tension. Practice maintaining a calm, "
            "grounded vocal tone in the second half of your pitch."
        )
    elif slope < -10.0:
        trend = "falling"
        assessment = (
            f"Vocal brightness decreased as your pitch progressed "
            f"(centroid falling ~{abs(slope):.0f} Hz/frame). "
            "This can indicate growing confidence or vocal fatigue. "
            "Ensure your energy and clarity stay high through the close."
        )
    else:
        trend = "stable"
        assessment = (
            "Vocal quality was consistent throughout the pitch — "
            "good tonal stability and vocal control."
        )

    return {
        "trend": trend,
        "slope_hz_per_frame": round(slope, 3),
        "mean_centroid_hz": round(mean_centroid, 1),
        "assessment": assessment,
    }
