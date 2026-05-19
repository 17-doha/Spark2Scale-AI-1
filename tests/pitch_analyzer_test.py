"""
Pitch Analyzer Agent — Integrated Test Suite
============================================
Unit tests for the real-time pitch coaching subsystem
(`app/graph/pitch_analyzer/`).

The pitch analyzer is the most stateful agent in the project (LiveKit room,
WebSocket to Qwen Realtime, audio analysis). These tests focus on the parts
that can be exercised in isolation:

  1. STATE & SCHEMA VALIDATION
  2. LIVEKITSESSIONSTATE INTERRUPT RULES
  3. ACOUSTIC FEATURE COMPUTATION
  4. NERVOUSNESS / ACOUSTIC ANOMALY DETECTORS
  5. MONOTONE DETECTOR
  6. RMS CALIBRATOR
  7. CONSISTENCY CHECK PIPELINE
  8. INVESTMENT READINESS REPORT    

We deliberately do NOT import `workflow.py` (depends on pyaudio + livekit) or
`node.py` (uses local-style imports `from state import …`). The InterruptLock
behavior tested here is reimplemented by `LiveKitSessionState.can_interrupt`.
"""

import pytest
from unittest.mock import patch, MagicMock

import numpy as np

# --- Imports from application ---
from app.graph.pitch_analyzer.state import (
    LiveKitSessionState,
    PitchState,
    AgentState,
)
from app.graph.pitch_analyzer.schema import (
    VCCheatSheet,
    PostPitchReview,
    GrammarIssue,
)
from app.graph.pitch_analyzer.tools import (
    compute_audio_features,
    detect_nervousness,
    detect_acoustic_anomalies,
    detect_monotone,
    RMSCalibrator,
    check_consistency_logic,
    execute_check_consistency,
    build_investment_readiness_report,
    HYSTERESIS_FRAMES,
)


# ===========================================================================
# 1. STATE & SCHEMA VALIDATION
# ===========================================================================
class TestPitchStateTyping:
    def test_pitch_state_typed_dict_accepts_keys(self):
        s: PitchState = {
            "raw_documents": {"evaluation": "..."},
            "cheat_sheet": None,
            "voice_prompt": None,
        }
        assert s["raw_documents"]["evaluation"] == "..."

    def test_agent_state_typed_dict_accepts_keys(self):
        s: AgentState = {
            "phase": "listening",
            "system_prompt": "you are alex",
            "pitch_history": [],
            "massive_docs": {},
            "structured_claims": {},
            "active_tool_call": {},
            "tool_output": "",
            "time_elapsed": 0.0,
            "trigger_update": False,
            "last_pause_start": None,
            "grammar_buffer": [],
            "grammar_buffer_flushed": False,
            "nervousness_score": 0.0,
            "session_log": [],
            "interrupt_log": [],
            "audio_metrics": [],
            "calibration_rms_baseline": 0.004,
            "diligence_answered": [],
            "post_pitch_review": None,
        }
        assert s["phase"] == "listening"


class TestPitchSchemas:
    def test_grammar_issue_schema(self):
        gi = GrammarIssue(
            timestamp=12.5,
            text_fragment="we are gonna disrupt",
            issues=["filler: gonna"],
        )
        assert gi.timestamp == 12.5
        assert gi.issues == ["filler: gonna"]

    def test_post_pitch_review_schema(self):
        review = PostPitchReview(
            filler_words=["um", "uh"],
            weak_phrases=["basically"],
            grammar_issues=[],
            interrupts_triggered=2,
            strengths=["clear vision"],
            next_steps=["practice transitions"],
        )
        assert review.interrupts_triggered == 2
        assert "clear vision" in review.strengths

    def test_vc_cheat_sheet_schema_minimum(self):
        sheet = VCCheatSheet(
            startup_name="Acme",
            evaluation_pillars={
                "team": "strong",
                "problem": "real",
                "product": "v1",
                "gtm": "outbound",
                "traction": "early",
                "vision": "big",
                "business": "saas",
                "market": "huge",
                "operations": "lean",
            },
            business_plan_context="seed-stage saas",
            cap_table_context="founder-owned",
            market_research_stats="TAM $10B",
            expected_ppt_flow=["intro", "problem", "solution"],
            prior_recommendations=["focus on ICP"],
            swot_analysis={
                "strengths": ["team"],
                "weaknesses": ["traction"],
                "opportunities": ["AI shift"],
                "threats": ["incumbents"],
            },
            hard_numbers={"burn_rate": "$10k/mo", "target_raise": "$1M"},
            vulnerabilities_to_attack=["customer churn"],
            diligence_questions=["a", "b", "c"],
        )
        assert sheet.startup_name == "Acme"
        assert sheet.evaluation_pillars.team == "strong"
        assert len(sheet.diligence_questions) == 3


# ===========================================================================
# 2. LIVEKITSESSIONSTATE INTERRUPT RULES
# ===========================================================================
class TestLiveKitSessionStateInterruptRules:
    def test_initial_state_allows_interrupt(self):
        state = LiveKitSessionState()
        assert state.can_interrupt() is True

    def test_cooldown_blocks_subsequent_interrupt(self, monkeypatch):
        """state.py does `import time; time.time()` inside the methods, so patching
        `time.time` on the module object propagates to the methods."""
        import time as _time

        clock = [1000.0]
        monkeypatch.setattr(_time, "time", lambda: clock[0])

        state = LiveKitSessionState()
        state.mark_interrupted(priority=3)

        # Same instant — within 10s cooldown
        clock[0] = 1001.0
        assert state.can_interrupt() is False

        # Past cooldown
        clock[0] = 1011.0
        assert state.can_interrupt() is True

    def test_grammar_cooldown_blocks_priority_2(self, monkeypatch):
        """Priority<=2 (filler/nervousness) is blocked for grammar_cooldown_s after a p<=2 interrupt."""
        state = LiveKitSessionState()
        import time as _time

        clock = [2000.0]
        monkeypatch.setattr(_time, "time", lambda: clock[0])

        state.mark_interrupted(priority=2)

        # 12s later: past general cooldown (10s) but inside grammar cooldown (20s)
        clock[0] = 2012.0
        assert state.can_interrupt(priority=2) is False

        # Higher priority interrupts ignore the grammar window
        assert state.can_interrupt(priority=5) is True

        # 21s later: grammar cooldown over too
        clock[0] = 2021.0
        assert state.can_interrupt(priority=2) is True

    def test_log_event_appends_relative_timestamp(self, monkeypatch):
        state = LiveKitSessionState()
        import time as _time

        monkeypatch.setattr(_time, "time", lambda: 105.0)
        state.session_start_ts = 100.0

        state.log_event("interrupt", "grammar", "subject-verb")
        assert len(state.session_log) == 1
        entry = state.session_log[0]
        assert entry["event"] == "interrupt"
        assert entry["reason"] == "grammar"
        assert entry["timestamp"] == 5.0

    def test_reset_clears_buffers(self):
        state = LiveKitSessionState()
        state.session_log.append({"event": "x", "reason": "y", "timestamp": 0, "detail": ""})
        state.pitch_history.append("hello")
        state.phase = "evaluating"

        state.reset()

        assert state.session_log == []
        assert state.pitch_history == []
        assert state.phase == "listening"


# ===========================================================================
# 3. ACOUSTIC FEATURE COMPUTATION
# ===========================================================================
class TestComputeAudioFeatures:
    def test_empty_input_returns_zeros(self):
        out = compute_audio_features(b"")
        assert out == {"rms_energy": 0.0, "zero_crossing_rate": 0.0, "pitch_estimate_hz": 0.0}

    def test_silence_produces_low_rms(self):
        # 4800 samples (0.2s @ 24kHz) of zeros → 9600 bytes int16
        pcm = (np.zeros(4800, dtype=np.int16)).tobytes()
        out = compute_audio_features(pcm)
        assert out["rms_energy"] == 0.0
        assert out["pitch_estimate_hz"] == 0.0

    def test_sine_wave_at_220hz_recovers_pitch(self):
        """A clean 220 Hz sine should be detected within ~10 Hz."""
        rate = 24000
        duration_s = 0.5
        t = np.arange(int(rate * duration_s)) / rate
        signal = 0.5 * np.sin(2 * np.pi * 220 * t)
        pcm = (signal * 32767).astype(np.int16).tobytes()

        out = compute_audio_features(pcm, rate=rate)
        assert out["rms_energy"] > 0.1
        assert abs(out["pitch_estimate_hz"] - 220.0) < 15.0


# ===========================================================================
# 4. NERVOUSNESS / ACOUSTIC ANOMALY DETECTORS
# ===========================================================================
class TestDetectNervousness:
    def test_short_history_returns_zero(self):
        feature_history = [
            {"rms_energy": 0.1, "zero_crossing_rate": 0.05, "pitch_estimate_hz": 150}
            for _ in range(3)
        ]
        assert detect_nervousness(feature_history) == 0.0

    def test_steady_features_score_low(self):
        feature_history = [
            {"rms_energy": 0.1, "zero_crossing_rate": 0.05, "pitch_estimate_hz": 150}
            for _ in range(10)
        ]
        score = detect_nervousness(feature_history)
        assert 0.0 <= score < 0.3

    def test_volatile_features_score_high(self):
        # Alternating ZCR + big energy spikes + rising pitch
        feature_history = []
        for i in range(20):
            feature_history.append({
                "rms_energy": 0.3 if i % 2 == 0 else 0.05,
                "zero_crossing_rate": 0.2 if i % 2 == 0 else 0.0,
                "pitch_estimate_hz": 120 + i * 10,
            })
        score = detect_nervousness(feature_history)
        assert score > 0.5
        assert score <= 1.0


class TestDetectAcousticAnomalies:
    def _frames(self, rms: float, zcr: float, n: int = HYSTERESIS_FRAMES):
        return [
            {"rms_energy": rms, "zero_crossing_rate": zcr, "pitch_estimate_hz": 0.0}
            for _ in range(n)
        ]

    def test_short_history_returns_none(self):
        assert detect_acoustic_anomalies(self._frames(0.001, 0.02, n=3)) is None

    def test_shouting_detected(self):
        result = detect_acoustic_anomalies(self._frames(0.6, 0.1))
        assert result is not None
        assert result["reason"] == "shouting"
        assert result["is_critical"] is True

    def test_background_noise_detected(self):
        result = detect_acoustic_anomalies(self._frames(0.05, 0.5))
        assert result is not None
        assert result["reason"] == "background_noise"

    def test_inaudible_detected(self):
        # rms below threshold AND zcr > 0.02 (so we know mic isn't simply muted)
        result = detect_acoustic_anomalies(
            self._frames(0.001, 0.05),
            inaudible_threshold=0.004,
        )
        assert result is not None
        assert result["reason"] == "inaudible"

    def test_clean_audio_returns_none(self):
        assert detect_acoustic_anomalies(self._frames(0.1, 0.05)) is None


# ===========================================================================
# 5. MONOTONE DETECTOR
# ===========================================================================
class TestDetectMonotone:
    def test_insufficient_pitch_data(self):
        feature_history = [
            {"rms_energy": 0.1, "zero_crossing_rate": 0.05, "pitch_estimate_hz": 0}
            for _ in range(20)
        ]
        result = detect_monotone(feature_history)
        assert result["is_monotone"] is False
        assert "Not enough" in result["assessment"]

    def test_monotone_flagged(self):
        # Std-dev ~5 Hz — clearly monotone
        feature_history = [
            {"rms_energy": 0.1, "zero_crossing_rate": 0.05, "pitch_estimate_hz": 150 + (i % 3)}
            for i in range(30)
        ]
        result = detect_monotone(feature_history)
        assert result["is_monotone"] is True
        assert result["variation_score"] < 30

    def test_dynamic_delivery_passes(self):
        # Std-dev ~80+ Hz
        rng = np.random.default_rng(42)
        feature_history = [
            {
                "rms_energy": 0.1,
                "zero_crossing_rate": 0.05,
                "pitch_estimate_hz": float(150 + rng.normal(0, 100)),
            }
            for _ in range(40)
        ]
        result = detect_monotone(feature_history)
        assert result["is_monotone"] is False
        assert result["variation_score"] >= 30


# ===========================================================================
# 6. RMS CALIBRATOR
# ===========================================================================
class TestRMSCalibrator:
    def test_starts_uncalibrated_with_default_threshold(self):
        cal = RMSCalibrator()
        assert cal.is_ready() is False
        assert cal.inaudible_threshold == RMSCalibrator.DEFAULT_THRESHOLD

    def test_calibrates_after_n_samples(self):
        cal = RMSCalibrator()
        for _ in range(RMSCalibrator.CALIBRATION_FRAMES):
            cal.add_sample(0.05)
        assert cal.is_ready() is True
        # 0.05 * 0.25 = 0.0125 — within FLOOR..CEILING
        assert (
            RMSCalibrator.FLOOR
            <= cal.inaudible_threshold
            <= RMSCalibrator.CEILING
        )

    def test_silent_room_uses_default(self):
        cal = RMSCalibrator()
        # Below the 0.001 active-frame filter
        for _ in range(RMSCalibrator.CALIBRATION_FRAMES):
            cal.add_sample(0.0001)
        assert cal.is_ready() is True
        assert cal.inaudible_threshold == RMSCalibrator.DEFAULT_THRESHOLD

    def test_force_complete_when_pitch_starts_early(self):
        cal = RMSCalibrator()
        cal.add_sample(0.02)
        cal.add_sample(0.03)
        cal.force_complete()
        assert cal.is_ready() is True

    def test_threshold_clamped_to_ceiling(self):
        """Even with very loud baseline samples, threshold caps at CEILING."""
        cal = RMSCalibrator()
        for _ in range(RMSCalibrator.CALIBRATION_FRAMES):
            cal.add_sample(0.5)
        assert cal.inaudible_threshold <= RMSCalibrator.CEILING


# ===========================================================================
# 7. CONSISTENCY CHECK PIPELINE
# ===========================================================================
class TestConsistencyChecks:
    @patch("app.graph.pitch_analyzer.tools._get_fast_llm")
    def test_check_consistency_logic_uses_llm_result(self, mock_get_llm):
        """check_consistency_logic returns the LLM JSON verdict directly."""
        verdict = {
            "contradiction": True,
            "is_critical": True,
            "error_type": "Self-Contradiction",
            "evidence": ["earlier said 100 users", "now says 50"],
            "detail": "user count contradiction",
            "recommended_interrupt": "Hold on — earlier you said 100 users.",
        }
        # The function builds a chain (`prompt | llm | parser`). Easiest mock:
        # short-circuit by patching the chain `invoke` indirectly via the LLM.
        # _get_fast_llm() returns an LLM that's chained with prompt + parser.
        # We patch the whole pipeline by replacing `_get_fast_llm` to return
        # a MagicMock LLM and then patching JsonOutputParser to return verdict.
        with patch(
            "app.graph.pitch_analyzer.tools.JsonOutputParser"
        ) as mock_parser_cls:
            chain_mock = MagicMock()
            chain_mock.invoke.return_value = verdict

            # `prompt | llm | parser` produces a Runnable. We bypass the pipe
            # by making the parser instance behave like a chain terminus we
            # can control — easier path: patch `check_consistency_logic`'s
            # internal chain construction by stubbing prompt | llm | parser.
            # Use a simpler approach: patch ChatPromptTemplate.from_messages.
            with patch(
                "app.graph.pitch_analyzer.tools.ChatPromptTemplate.from_messages"
            ) as mock_prompt_from:
                # Simulate prompt | llm | parser → chain_mock
                fake_prompt = MagicMock()
                fake_prompt.__or__ = MagicMock(return_value=MagicMock(
                    __or__=MagicMock(return_value=chain_mock)
                ))
                mock_prompt_from.return_value = fake_prompt

                result = check_consistency_logic("we have 50 users", ["we had 100 users"])
                assert result["contradiction"] is True
                assert result["error_type"] == "Self-Contradiction"

    def test_check_consistency_logic_empty_history_short_circuits(self):
        """No history means nothing to contradict."""
        with patch(
            "app.graph.pitch_analyzer.tools.ChatPromptTemplate.from_messages"
        ):
            # Should not even need the LLM when history is empty — but helper
            # may still call it; just verify the structure is sane on raise.
            with patch(
                "app.graph.pitch_analyzer.tools._get_fast_llm",
                side_effect=RuntimeError("must not call"),
            ):
                # The helper does check the empty path:
                result = check_consistency_logic("first claim", [])
                assert result["contradiction"] is False

    @patch("app.graph.pitch_analyzer.tools.check_consistency_logic")
    @patch("app.graph.pitch_analyzer.tools.verify_claims_vs_cheat_sheet")
    def test_execute_check_consistency_self_stage_short_circuits(
        self, mock_verify, mock_self
    ):
        """If the self-check finds a contradiction, the cheat-sheet stage is skipped."""
        mock_self.return_value = {
            "contradiction": True,
            "is_critical": True,
            "error_type": "Self-Contradiction",
            "evidence": [],
            "detail": "x",
            "recommended_interrupt": "stop",
        }
        result = execute_check_consistency("claim", ["earlier"], {"any": "sheet"}, {})
        assert result["contradiction"] is True
        assert result["stage"] == "self"
        mock_verify.assert_not_called()

    @patch("app.graph.pitch_analyzer.tools.check_consistency_logic")
    @patch("app.graph.pitch_analyzer.tools.verify_claims_vs_cheat_sheet")
    def test_execute_check_consistency_summary_stage(self, mock_verify, mock_self):
        """When self-check passes, document conflict check runs and returns stage='summary'."""
        mock_self.return_value = {
            "contradiction": False,
            "is_critical": False,
            "error_type": None,
            "evidence": [],
            "detail": "",
            "recommended_interrupt": "",
        }
        mock_verify.return_value = {
            "contradiction": True,
            "is_critical": True,
            "error_type": "Document-Conflict",
            "evidence": ["doc says 200 users"],
            "detail": "doc conflict",
            "recommended_interrupt": "your doc says 200",
        }
        result = execute_check_consistency(
            "we have 50 users",
            [],
            {"hard_numbers": {"users": 200}},
            {},
        )
        assert result["contradiction"] is True
        assert result["stage"] == "summary"

    @patch("app.graph.pitch_analyzer.tools.check_consistency_logic")
    def test_execute_check_consistency_clean_when_no_context(self, mock_self):
        """No cheat_sheet AND no massive_docs → just self-check, return clean."""
        mock_self.return_value = {
            "contradiction": False,
            "is_critical": False,
            "error_type": None,
            "evidence": [],
            "detail": "",
            "recommended_interrupt": "",
        }
        result = execute_check_consistency("claim", [], {}, {})
        assert result["contradiction"] is False
        assert result["stage"] is None


# ===========================================================================
# 8. INVESTMENT READINESS REPORT
# ===========================================================================
# NOTE: tools.py defines `build_investment_readiness_report` twice (line 410 and
# line 902). Python's last-definition-wins rule means the LLM-driven version
# (line 902) is the one actually exported. It builds a `prompt | llm | parser`
# chain and returns whatever the chain produces, so the tests below mock the
# chain construction.
class TestInvestmentReadinessReport:
    def _patch_chain(self, chain_result):
        """Helper: patches tools so `prompt | llm | parser` short-circuits to chain_result."""
        chain_mock = MagicMock()
        chain_mock.invoke.return_value = chain_result

        # Build a fake prompt that absorbs `| llm | parser` and yields our chain.
        fake_after_llm = MagicMock()
        fake_after_llm.__or__ = MagicMock(return_value=chain_mock)
        fake_prompt = MagicMock()
        fake_prompt.__or__ = MagicMock(return_value=fake_after_llm)
        return fake_prompt, chain_mock

    @patch("app.graph.pitch_analyzer.tools.JsonOutputParser")
    @patch("app.graph.pitch_analyzer.tools._get_fast_llm")
    @patch("app.graph.pitch_analyzer.tools.ChatPromptTemplate.from_messages")
    def test_report_returns_llm_payload(self, mock_prompt_from, mock_llm, mock_parser):
        """The exported builder calls the LLM chain and returns its dict result."""
        canned = {
            "grade": "B+",
            "score": 78,
            "max_score": 100,
            "rubric": {"team": {"score": 8, "notes": "strong CTO"}},
            "strengths": ["team"],
            "critical_weaknesses": ["traction"],
            "essentials_checklist": {"covered": ["problem"], "missing": ["traction"]},
            "investor_killer_moments": [
                {"timestamp_s": 12.3, "type": "grammar_and_fillers", "detail": "subject-verb"},
            ],
            "recommended_actions": ["land 3 design partners", "tighten ICP", "ship onboarding flow"],
            "final_verdict": "Compelling team but I'd wait for traction.",
        }
        fake_prompt, chain_mock = self._patch_chain(canned)
        mock_prompt_from.return_value = fake_prompt

        report = build_investment_readiness_report(
            session_log=[
                {"event": "interrupt", "reason": "grammar_and_fillers",
                 "timestamp": 12.3, "detail": "subject-verb"},
            ],
            grammar_buffer=[],
            structured_claims={},
            pitch_history=[],
            diligence_answered=[],
            full_transcript="we built a thing.",
        )

        assert report == canned
        chain_mock.invoke.assert_called_once()
        # Verify the args dict contains the exact keys the prompt template needs.
        kwargs = chain_mock.invoke.call_args[0][0]
        for key in (
            "session_log",
            "grammar_buffer",
            "structured_claims",
            "pitch_history",
            "diligence_answered",
            "full_transcript",
            "monotone_assessment",
        ):
            assert key in kwargs

    @patch("app.graph.pitch_analyzer.tools.JsonOutputParser")
    @patch("app.graph.pitch_analyzer.tools._get_fast_llm")
    @patch("app.graph.pitch_analyzer.tools.ChatPromptTemplate.from_messages")
    def test_report_returns_empty_dict_on_llm_failure(
        self, mock_prompt_from, mock_llm, mock_parser
    ):
        """When the chain raises, the builder swallows the error and returns {}."""
        chain_mock = MagicMock()
        chain_mock.invoke.side_effect = RuntimeError("LLM down")
        fake_after_llm = MagicMock()
        fake_after_llm.__or__ = MagicMock(return_value=chain_mock)
        fake_prompt = MagicMock()
        fake_prompt.__or__ = MagicMock(return_value=fake_after_llm)
        mock_prompt_from.return_value = fake_prompt

        report = build_investment_readiness_report(
            session_log=[],
            grammar_buffer=[],
            structured_claims={},
            pitch_history=[],
            diligence_answered=[],
            full_transcript="",
        )
        assert report == {}

    @patch("app.graph.pitch_analyzer.tools.JsonOutputParser")
    @patch("app.graph.pitch_analyzer.tools._get_fast_llm")
    @patch("app.graph.pitch_analyzer.tools.ChatPromptTemplate.from_messages")
    def test_report_passes_monotone_assessment(
        self, mock_prompt_from, mock_llm, mock_parser
    ):
        """The optional monotone_assessment kwarg is forwarded to the LLM prompt."""
        fake_prompt, chain_mock = self._patch_chain({"grade": "A"})
        mock_prompt_from.return_value = fake_prompt

        build_investment_readiness_report(
            session_log=[],
            grammar_buffer=[],
            structured_claims={},
            pitch_history=[],
            diligence_answered=[],
            full_transcript="",
            monotone_assessment="Good vocal variety.",
        )
        kwargs = chain_mock.invoke.call_args[0][0]
        assert kwargs["monotone_assessment"] == "Good vocal variety."
