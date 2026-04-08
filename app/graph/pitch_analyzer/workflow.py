import os
import json
import time
import random
import re
import asyncio
import websockets
import base64
import logging
from pathlib import Path
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from state import PitchState, AgentState
from node import extract_vc_cheat_sheet, format_voice_prompt, tool_node, phase_node
from prompts import (
    generate_agent_system_prompt,
    GREETING_INSTRUCTION,
    NERVOUSNESS_INTERRUPT_INSTRUCTION,
)
from tools import (
    compute_audio_features, detect_acoustic_anomalies, detect_nervousness, extract_claims,
    execute_grammar_check, execute_check_consistency, check_investor_essentials,
    build_investment_readiness_report, deep_search_verification
)

import pyaudio

# ── Nervousness threshold ──────────────────────────────────────────────────────
NERVOUSNESS_THRESHOLD = 0.7

# ── Audio settings (must match Qwen Realtime API format) ──────────────────────
AUDIO_RATE  = 24000
AUDIO_CHUNK = 2400

# ── Interrupt priority map (FIX 5) ────────────────────────────────────────────
# acoustic(1) must never override semantic(>=3) that fired in last 15s
INTERRUPT_PRIORITY = {
    "document_conflict":       5,
    "internal_contradiction":  5,
    "grammar_and_fillers":     3,
    "nervousness":             2,
    "acoustic_anomaly":        1,
}

# ── Filler word regex (FIX 6) ─────────────────────────────────────────────────
FILLER_PATTERN = re.compile(r'\b(um|uh|like|you know|basically|sort of|right\?)\b', re.IGNORECASE)

# ── Mic-check phrases that suppress acoustic interrupt (IMP C) ────────────────
CONFIRMATION_PHRASES = ["can you hear me", "are you there", "hello alex", "hello sparky", "are you listening"]

# ── Utterance completeness guard (BUG 3) ─────────────────────────────────────
# Only fire LLM interrupts once the founder's utterance looks syntactically complete.
SENTENCE_ENDINGS = re.compile(r'[.!?,]$|\b(right|okay|so|and)\s*$', re.IGNORECASE)

# ── Post-calibration acoustic grace window (BUG 4) ───────────────────────────
# NO acoustic interrupts for this many seconds after calibration finishes.
# 20s gives time for greeting TTS to finish + founder's first sentence to start.
ACOUSTIC_GRACE_S: float = 20.0


class InterruptLock:
    """
    FIX 2 + FIX 5: Coroutine-safe gate controlling whether any interrupt fires.

    Rules:
      - Only ONE interrupt active at a time (_response_active guard).
      - Minimum 8s cooldown between any two interrupts.
      - Acoustic (priority=1) blocked for 15s after any semantic (priority>=3).
    """

    def __init__(self, cooldown_s: float = 8.0):
        self._last_fired: float = 0.0
        self._last_semantic_fired: float = 0.0
        self._response_active: bool = False
        self.cooldown_s = cooldown_s

    def can_fire(self, now: float, priority: int = 1) -> bool:
        if self._response_active:
            return False
        if (now - self._last_fired) < self.cooldown_s:
            return False
        # Acoustic must not fire within 15s of a semantic interrupt
        if priority <= 1 and (now - self._last_semantic_fired) < 15.0:
            return False
        return True

    def on_fire(self, now: float, priority: int = 1):
        """Call BEFORE sending any interrupt signal."""
        if priority >= 1:  # priority=0 means normal response tracking, not an interrupt
            self._last_fired = now
        self._response_active = True
        if priority >= 3:
            self._last_semantic_fired = now

    def on_response_done(self):
        """Call inside the response.done WebSocket handler."""
        self._response_active = False

    @property
    def response_active(self) -> bool:
        return self._response_active


from livekit.agents import (
    JobContext, WorkerOptions, cli,
    AgentSession, Agent, function_tool, RunContext,
)
from livekit.plugins import openai as lk_openai, silero, elevenlabs, deepgram

from tools import (
    build_investment_readiness_report,
    extract_claims,
    compute_audio_features,
    detect_nervousness,
    detect_acoustic_anomalies,
    execute_grammar_check,
    execute_check_consistency,
    deep_search_verification,
    check_investor_essentials
)
from state import (
    AgentState,
    LiveKitSessionState
)
from schema import (
    VCCheatSheet
)
from prompts import (
    GREETING_INSTRUCTION,
    generate_agent_system_prompt
)
from node import (
    extract_vc_cheat_sheet,
    format_voice_prompt
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

import re

SENTENCE_ENDINGS = re.compile(r'[.!?]\s*$')
FILLER_PATTERN   = re.compile(r'\b(um|uh|like|you know|i mean|basically|actually|literally)\b', flags=re.IGNORECASE)

AUDIO_RATE = 24000
AUDIO_CHUNK = 1200  # 50ms chunks (24000 * 0.05)
CONFIRMATION_PHRASES = ["can you hear", "hear me", "testing", "is this working", "check"]

# ── Tuning constants ──────────────────────────────────────────────────────────
NERVOUSNESS_THRESHOLD = 0.70
ACOUSTIC_GRACE_S      = 20.0

# Minimum words in a streaming partial before we bother checking it.
# 12 words catches medium-length contradictions without false positives on greetings.
STREAMING_MIN_WORDS   = 12
STREAMING_COOLDOWN_S  = 8.0

# How many seconds from pitch start before ANY consistency/grammar checks fire.
# Filters out the intro phase (names, greetings, chitchat) where qwen-turbo
# is prone to flagging casual speech as factual contradictions.
CONSISTENCY_GRACE_S   = 60.0

# How long to wait before asking "are you still there?" after a silence.
SILENCE_PROMPT_S      = 15.0
# Minimum wait after the agent SPOKE before the silence watcher can fire.
# Prevents repeated prompts right after the agent finishes speaking.
SILENCE_AGENT_GAP_S   = 3.0

# ── Session timeline (seconds after greeting_done) ────────────────────────────
PHASE_INTERROGATING_S = 210   # T=3:30 — switch to diligence questions
PHASE_PRE_REPORT_S    = 270   # T=4:30 — pre-compute the report in background
PHASE_EVALUATING_S    = 300   # T=5:00 — post-pitch review + goodbye
PHASE_HARD_CAP_S      = 330   # T=5:30 — force goodbye no matter what
# PHASE_INTERROGATING_S = 20  # Shift to diligence after 20 seconds
# PHASE_PRE_REPORT_S    = 45  # Start background JSON generation at 45 seconds
# PHASE_EVALUATING_S    = 60  # Trigger final review at 60 seconds
# PHASE_HARD_CAP_S      = 75  # Hard cutoff at 1 min 15s if evaluating fails
# ── Pre-flight cache (populated by main.py) ───────────────────────────────────
_PREFLIGHT: dict = {
    "cheat_sheet":  {},
    "massive_docs": {},
    "voice_prompt": "",
}

# ── Absolute path for session report (must match _REPORT_PATH in pitch_analyzer.py) ──
_SESSION_REPORT_PATH = Path(os.getcwd()) / "app" / "graph" / "pitch_analyzer" / "session_report.json"


def build_extractor_workflow():
    """
    One-shot LangGraph pipeline:
      START → extract_vc_cheat_sheet → format_voice_prompt → END

    Compresses the 7 massive docs into a VCCheatSheet, then formats the
    system prompt string that will be injected into Sparky's session.
    """
    from state import PitchState
    workflow = StateGraph(PitchState)
    workflow.add_node("extract_context", extract_vc_cheat_sheet)
    workflow.add_node("format_prompt", format_voice_prompt)
    workflow.add_edge(START, "extract_context")
    workflow.add_edge("extract_context", "format_prompt")
    workflow.add_edge("format_prompt", END)
    return workflow.compile()


# ═══════════════════════════════════════════════════════════════════════════════
# RATE LIMIT RETRY WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════

async def _safe_thread_call(fn, *args, retries=3):
    """Exponential backoff retry for any rate-limit (429) errors."""
    for attempt in range(retries):
        try:
            return await asyncio.to_thread(fn, *args)
        except Exception as e:
            if "429" in str(e) and attempt < retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logging.warning(f"Rate limit (attempt {attempt+1}/{retries}), retrying in {wait:.1f}s")
                await asyncio.sleep(wait)
            else:
                raise
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# FORCE SPEAK HELPER
# ═══════════════════════════════════════════════════════════════════════════════

async def _force_speak(session: AgentSession, exact_phrase: str):
    """Cuts ongoing TTS and speaks exact_phrase with no interruptions allowed."""
    try:
        await session.interrupt()
    except Exception as e:
        logging.warning(f"session.interrupt() failed: {e}")

    for attempt in range(3):
        try:
            await session.say(exact_phrase, allow_interruptions=False, add_to_chat_ctx=True)
            return
        except Exception as e:
            logging.warning(f"TTS say() attempt {attempt+1}/3 failed: {e}")
            await asyncio.sleep(0.5)

    logging.error(f"Failed to speak after 3 attempts: {exact_phrase[:60]}")


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE INTERRUPT GATE
# ═══════════════════════════════════════════════════════════════════════════════

async def _try_interrupt(
    state:                 LiveKitSessionState,
    session:               AgentSession,
    interrupt_msg:         str,
    priority:              int,
    reason:                str,
    detail:                str,
    add_to_grammar_buffer: bool = False,
    utterance:             str  = "",
) -> bool:
    """
    Core interrupt logic — interrupts and speaks the interrupt message directly.
    Using session.say() for reliable delivery (generate_reply is non-deterministic).
    """
    if not state.can_interrupt(priority=priority):
        return False

    async with state.interrupt_lock:
        if not state.can_interrupt(priority=priority):
            return False

        state.mark_interrupted(priority=priority)
        state.log_event("interrupt", reason, detail)

        if add_to_grammar_buffer and utterance:
            state.grammar_buffer.append({
                "timestamp": time.time() - state.session_start_ts,
                "text":      utterance,
                "issues":    [detail],
            })

        logging.warning(f"[INTERRUPT p={priority}] {reason}: {detail[:80]}")

        # Stop whatever the agent is currently doing
        try:
            await session.interrupt()
        except Exception:
            pass

        # Speak the interrupt message directly — no LLM round-trip needed
        try:
            await session.say(interrupt_msg, add_to_chat_ctx=True)
        except Exception as e:
            logging.warning(f"[INTERRUPT] say() failed: {e}")

        return True

# ═══════════════════════════════════════════════════════════════════════════════
# FUNCTION TOOLS  (bound to session state via factory)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_tools(state: LiveKitSessionState, session_ref: list):
    """
    Returns all @function_tool callables, closed over state and session_ref.
    session_ref is a 1-element list so the session can be injected after creation.
    """

    @function_tool
    async def lk_check_grammar(text: str, context: RunContext):
        """
        INTERRUPT TOOL — call after EVERY founder turn.
        Runs LanguageTool en-US grammar check silently.
        If a critical issue is found, interrupts the founder immediately.
        DO NOT narrate this call.
        """
        logging.info(f"[TOOL] check_grammar → {text[:60]}")
        result = await _safe_thread_call(execute_grammar_check, text)
        if result and result["is_critical"]:
            issue_summary = "; ".join(result["issues"][:2])
            await _try_interrupt(
                state, session_ref[0], result["recommended_interrupt"],
                priority=3, reason="grammar_and_fillers", detail=issue_summary,
                add_to_grammar_buffer=True, utterance=text,
            )
            return result["recommended_interrupt"]
        return "No grammar issue."

    @function_tool
    async def lk_check_consistency(claim: str, context: RunContext):
        """
        INTERRUPT TOOL. Call whenever the founder states a specific number,
        traction metric, market size, team fact, or funding figure.
        DO NOT narrate this call.
        """
        logging.info(f"[TOOL] check_consistency → {claim[:80]}")
        result = await _safe_thread_call(
            execute_check_consistency,
            claim, state.pitch_history, state.cheat_sheet, state.massive_docs,
        )
        state.pitch_history.append(claim)
        if result and result["contradiction"]:
            await _try_interrupt(
                state, session_ref[0], result["recommended_interrupt"],
                priority=5, reason=result.get("error_type", "consistency"),
                detail=result.get("detail", "Contradiction detected."),
            )
            return result["recommended_interrupt"]
        return "No contradiction."

    @function_tool
    async def verify_document(category: str, claimed_value: str, context: RunContext):
        """
        INTERRUPT TOOL. Use when check_consistency missed a discrepancy but you
        suspect a number is wrong. Searches raw Company Context for ground truth.
        DO NOT narrate this call.
        """
        logging.info(f"[TOOL] verify_document category={category}")
        result = await _safe_thread_call(deep_search_verification, category, state.massive_docs)
        state.log_event("tool_call", "deep_search", f"category={category}")
        if result and result["found"]:
            excerpt = result["ground_truth"][:200]
            return (
                f"DOCUMENT FACT ({category}): {excerpt}\n"
                f"FOUNDER CLAIMED: '{claimed_value}'\n"
                f"If these conflict, say: 'Hold on — your {category} document shows "
                f"'{excerpt[:60]}...' but you said '{claimed_value}'. Which is accurate?'"
            )
        return f"No document data found for '{category}'."

    @function_tool
    async def check_pitch_essentials(transcript_so_far: str, context: RunContext):
        """
        REALITY MENTOR TOOL. Call when the founder pauses after 2+ minutes.
        Checks whether the 8 investor essentials have been covered.
        """
        elapsed = time.time() - state.session_start_ts
        if elapsed < 120.0:
            return "Too early — let the founder speak for at least 2 minutes first."
        result = await _safe_thread_call(check_investor_essentials, transcript_so_far)
        if not result:
            return "Could not check essentials."
        missing = result.get("missing", [])
        covered = result.get("covered", [])
        if missing:
            return (
                f"REALITY CHECK — Covered: {covered}. STILL MISSING: {missing}. "
                f"Interrupt now: 'Hold on — you've been talking for a while and I "
                f"still haven't heard about your {missing[0]}. What is it?'"
            )
        return f"All investor essentials covered: {covered}."

    @function_tool
    async def generate_final_report(ready: bool, context: RunContext):
        """
        END-OF-SESSION TOOL. Call when 5 minutes have elapsed or pitch is done.
        Generates the full Investment Readiness Report.
        """
        logging.info("[TOOL] generate_final_report called.")
        report = await _safe_thread_call(
            build_investment_readiness_report,
            state.session_log, state.grammar_buffer, state.structured_claims,
            state.pitch_history, state.diligence_answered, state.full_transcript,
        )
        if not report:
            return "Could not generate report — session data may be incomplete."

        grade      = report.get("grade", "?")
        score      = report.get("score", 0)
        max_s      = report.get("max_score", 100)
        strengths  = ", ".join(report.get("strengths", []))
        weaknesses = ", ".join(report.get("critical_weaknesses", []))
        missing    = ", ".join(report.get("essentials_checklist", {}).get("missing", []))
        moments    = "\n  ".join(
            f"[{k['timestamp_s']}s] {k['type']}: {k['detail']}"
            for k in report.get("investor_killer_moments", [])[:3]
        )
        state.post_pitch_review = report
        return (
            f"FINAL REPORT — Grade: {grade} ({score}/{max_s})\n"
            f"Strengths: {strengths}\n"
            f"Critical Weaknesses: {weaknesses}\n"
            f"Missing Essentials: {missing or 'None'}\n"
            f"Top Moments: {moments or 'None'}\n"
            "Now deliver this report conversationally. "
            "Speak naturally like a human investor giving their final thoughts "
            "face-to-face. Cover the grade, biggest strength, biggest weakness, and final verdict."
        )

    return [verify_document, check_pitch_essentials, generate_final_report]


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER A — STREAMING INTERRUPT ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

async def _check_streaming_interrupt(
    state:        LiveKitSessionState,
    session:      AgentSession,
    partial_text: str,
    lock:         asyncio.Lock,
):
    """
    Called on every Deepgram streaming partial while founder is STILL speaking.
    Consistency check only (fast). Grammar deferred to committed path.
    """
    words = partial_text.strip().split()
    if len(words) < STREAMING_MIN_WORDS:
        return
    if lock.locked():
        return

    # Grace period: skip consistency checks during intro/greeting phase
    if state.session_start_ts > 0 and (time.time() - state.session_start_ts) < CONSISTENCY_GRACE_S:
        return

    async with lock:
        try:
            result = await _safe_thread_call(
                execute_check_consistency,
                partial_text, state.pitch_history, state.cheat_sheet, state.massive_docs,
            )
            if result and result["contradiction"]:
                await _try_interrupt(
                    state, session, result["recommended_interrupt"],
                    priority=5, reason=result.get("error_type", "consistency"),
                    detail=result.get("detail", "Contradiction."),
                )
        except Exception as e:
            logging.warning(f"Streaming consistency check error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER B — COMMITTED UTTERANCE PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

async def _check_issues_and_interrupt(
    state:     LiveKitSessionState,
    session:   AgentSession,
    utterance: str,
):
    """
    Consistency (p=5) → Grammar (p=3) → Fillers (p=2).
    Each step routes through _try_interrupt() which holds interrupt_lock,
    so only one of the three fires per utterance.
    """
    # Grace period: don't check consistency for the first 60 seconds
    import time
    elapsed = time.time() - state.session_start_ts if state.session_start_ts > 0 else 0
    if elapsed < CONSISTENCY_GRACE_S:
        logging.debug(f"[COMMITTED] Skipping checks — grace period ({elapsed:.0f}s < {CONSISTENCY_GRACE_S}s)")
        state.pitch_history.append(utterance)
        return

    # ── Step 1: Consistency / document conflict ────────────────────────────────
    try:
        result = await _safe_thread_call(
            execute_check_consistency,
            utterance, state.pitch_history, state.cheat_sheet, state.massive_docs,
        )
        state.pitch_history.append(utterance)
        if result and result["contradiction"]:
            fired = await _try_interrupt(
                state, session, result["recommended_interrupt"],
                priority=5, reason=result.get("error_type", "consistency"),
                detail=result.get("detail", "Contradiction detected."),
            )
            if fired:
                return
    except Exception as e:
        logging.warning(f"Committed consistency check error: {e}")

    # ── Step 2: Grammar errors ────────────────────────────────────────────────
    try:
        gr = await _safe_thread_call(execute_grammar_check, utterance)
        if gr and gr["is_critical"]:
            issue_summary = "; ".join(gr["issues"][:2])
            fired = await _try_interrupt(
                state, session, gr["recommended_interrupt"],
                priority=3, reason="grammar_and_fillers", detail=issue_summary,
                add_to_grammar_buffer=True, utterance=utterance,
            )
            if fired:
                return
    except Exception as e:
        logging.warning(f"Committed grammar check error: {e}")

    # ── Step 3: Filler word overload ──────────────────────────────────────────
    fillers = FILLER_PATTERN.findall(utterance)
    if len(fillers) >= 3:
        filler_sample = ", ".join(f'"{f}"' for f in fillers[:3])
        await _try_interrupt(
            state, session,
            interrupt_msg=(
                f"Quick pause — too many filler words: {filler_sample}. "
                f"Take a breath and rephrase that last point, clean and confident."
            ),
            priority=2, reason="filler_overload", detail=filler_sample,
            add_to_grammar_buffer=True, utterance=utterance,
        )


async def _merge_claims(state: LiveKitSessionState, utterance: str):
    """Extracts structured claims passively — no interrupts."""
    try:
        claims = await _safe_thread_call(extract_claims, utterance)
        if not claims:
            return
        existing = state.structured_claims
        for key, subdict in claims.items():
            if key == "raw_numbers":
                continue
            if isinstance(subdict, dict):
                if key not in existing:
                    existing[key] = subdict
                else:
                    for field, val in subdict.items():
                        if val and not existing[key].get(field):
                            existing[key][field] = val
            elif isinstance(subdict, list) and subdict:
                existing[key] = list(set(existing.get(key, []) + subdict))
        state.structured_claims = existing
    except Exception as e:
        logging.warning(f"Claim extraction failed: {e}")


async def _check_nervousness(
    state:     LiveKitSessionState,
    session:   AgentSession,
    utterance: str,
):
    """Filler-ratio nervousness proxy. Fires at priority=2 when score >= 0.70."""
    import time
    elapsed = time.time() - state.session_start_ts
    if elapsed < ACOUSTIC_GRACE_S:
        return

    words        = utterance.split()
    filler_count = len(FILLER_PATTERN.findall(utterance))
    filler_ratio = filler_count / max(len(words), 1)

    state.feature_history.append({
        "rms_energy":         0.0,
        "zero_crossing_rate": filler_ratio * 0.5,
        "pitch_estimate_hz":  0.0,
    })
    if len(state.feature_history) > 20:
        state.feature_history.pop(0)

    if len(state.feature_history) >= 5:
        state.nervousness_score = detect_nervousness(state.feature_history)

    if state.nervousness_score >= NERVOUSNESS_THRESHOLD:
        await _try_interrupt(
            state, session,
            interrupt_msg=(
                "Actually, back up a second. You're rushing. "
                "Slow down, take a breath, and try that last point again."
            ),
            priority=2, reason="nervousness",
            detail=f"score={state.nervousness_score:.2f}, fillers={filler_count}",
        )


async def _on_utterance(
    state:     LiveKitSessionState,
    session:   AgentSession,
    utterance: str,
):
    """Full committed-utterance analysis pipeline."""
    await _check_issues_and_interrupt(state, session, utterance)
    await asyncio.gather(
        _merge_claims(state, utterance),
        _check_nervousness(state, session, utterance),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND LOOPS
# ═══════════════════════════════════════════════════════════════════════════════

async def _silence_watcher(state: LiveKitSessionState, session: AgentSession):
    """Prompts the founder after silence during active phases (listening + interrogating)."""
    import time
    last_agent_speech_ts: float = 0.0

    @session.on("agent_speech_committed")
    def _track_agent_speech(msg):
        nonlocal last_agent_speech_ts
        last_agent_speech_ts = time.time()

    while state.phase not in ("done", "evaluating"):
        await asyncio.sleep(1.0)

        # Only fire when founder SHOULD be talking (listening or interrogating)
        if state.last_speech_time <= 0 or state.phase not in ("listening", "interrogating"):
            continue

        # Don't fire within SILENCE_AGENT_GAP_S seconds of the agent speaking
        if (time.time() - last_agent_speech_ts) < SILENCE_AGENT_GAP_S:
            continue

        elapsed_silence = time.time() - state.last_speech_time
        if elapsed_silence >= SILENCE_PROMPT_S:
            logging.info(f"[SILENCE] {elapsed_silence:.1f}s in phase={state.phase} — prompting founder.")
            state.last_speech_time = time.time()
            last_agent_speech_ts = time.time()  # prevent immediate re-fire
            try:
                prompt = (
                    "I'm still waiting — go ahead."
                    if state.phase == "interrogating"
                    else "I'm listening — go ahead whenever you're ready."
                )
                await session.say(prompt, add_to_chat_ctx=True)
            except RuntimeError:
                break


async def contradiction_watcher(state: LiveKitSessionState, session: AgentSession):
    """LAYER C: 5s backstop — catches anything Layers A+B missed."""
    import time
    while state.phase != "done":
        await asyncio.sleep(5.0)

        # Grace period: don't run watcher during intro/greeting phase
        if state.session_start_ts > 0 and (time.time() - state.session_start_ts) < CONSISTENCY_GRACE_S:
            continue

        text = state.unhandled_transcript.strip()
        if len(text.split()) < 5:
            continue
        state.unhandled_transcript = ""
        try:
            result = await _safe_thread_call(
                execute_check_consistency,
                text, state.pitch_history, state.cheat_sheet, state.massive_docs,
            )
            state.pitch_history.append(text)
            if result and result["contradiction"]:
                await _try_interrupt(
                    state, session, result["recommended_interrupt"],
                    priority=5, reason=result.get("error_type", "consistency"),
                    detail=result.get("detail", "Contradiction."),
                )
                state.unhandled_transcript = ""
        except Exception as e:
            logging.warning(f"Watcher consistency check error: {e}")
            state.pitch_history.append(text)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE WATCHER (Updated to actively ask Diligence Questions)

# Add ctx: JobContext to the arguments
async def _phase_watcher(state: LiveKitSessionState, session: AgentSession, ctx: JobContext, greeting_done: asyncio.Event):
    """
    Monitors time and shifts phases.
    - INTERROGATING: asks diligence questions one at a time via generate_reply(instructions=...)
    - EVALUATING: triggers the post-pitch review and final report
    """
    import time
    await greeting_done.wait()

    questions_asked  = 0
    diligence_qs     = _PREFLIGHT.get("cheat_sheet", {}).get("diligence_questions", [])
    q_cooldown_until = 0.0   # don't ask next question before this timestamp
    

    while True:
        await asyncio.sleep(2.0)

        # ── EXIT immediately if session was ended early (e.g. user disconnected) ──
        # This stops the watcher from calling session.generate_reply() on a dead room.
        if state.phase == "done":
            logging.info("[PHASE WATCHER] Phase is 'done' — exiting watcher loop.")
            return

        now     = time.time()
        elapsed = now - state.session_start_ts
        state.time_elapsed = elapsed

        # ── TRANSITION TO INTERROGATING ──────────────────────────────────────
        if PHASE_INTERROGATING_S <= elapsed < PHASE_EVALUATING_S and state.phase != "interrogating":
            state.phase = "interrogating"
            logging.info("Phase → INTERROGATING")
            # Set cooldown so the diligence Q block doesn't also fire on this same tick
            q_cooldown_until = now + 40.0  # give time for the transition announcement to play
            # q_cooldown_until = now + 5.0
            try:
                await session.interrupt()
            except Exception:
                pass
            try:
                await session.generate_reply(
                    instructions=(
                        "The open pitch is over. Transition to DILIGENCE mode now. "
                        "Say: 'Okay, let's shift gears. I have a few hard questions for you.' "
                        "Then immediately ask the first diligence question from the checklist."
                    )
                )
            except Exception as e:
                logging.warning(f"Phase watcher (interrogating entry) error: {e}")

        # ── ASK NEXT DILIGENCE QUESTION ───────────────────────────────────────
        if (
            state.phase == "interrogating"
            and diligence_qs
            and questions_asked < len(diligence_qs)
            and now >= q_cooldown_until
        ):
            q = diligence_qs[questions_asked]
            questions_asked  += 1
            q_cooldown_until  = now + 35.0   # wait 35s before next question
            # Change from 35.0 to 10.0
            # q_cooldown_until  = now + 10.0
            logging.info(f"[PHASE] Asking diligence Q{questions_asked}: {q[:60]}")
            try:
                await session.interrupt()
            except Exception:
                pass
            try:
                await session.generate_reply(
                    instructions=(
                        f"Ask this exact diligence question and nothing else: '{q}' "
                        "One question only. Then go completely silent and wait for the answer."
                    )
                )
            except Exception as e:
                logging.warning(f"Phase watcher (diligence question) error: {e}")

        # ── PRE-COMPUTE REPORT ─────────────────────────────────────────────
        # At T=4:30, start building the report in the background so it's
        # ready the instant the evaluating phase fires at T=5:00.
        if elapsed >= PHASE_PRE_REPORT_S and not getattr(state, '_report_preflight_started', False):
            state._report_preflight_started = True
            logging.info("[PHASE] Pre-computing final report + monotone detection in background...")
            
            # 1. Run monotone detection synchronously first
            try:
                # Adjust import path to match your project structure if needed
                from tools import detect_monotone 
                mono_result = detect_monotone(state.feature_history)
                state.monotone_assessment = mono_result.get("assessment", "")
                logging.info(f"[PHASE] Monotone assessment: {state.monotone_assessment[:60]}")
            except Exception as mono_err:
                logging.warning(f"[PHASE] Monotone detection failed: {mono_err}")
                state.monotone_assessment = ""

            # 2. Build the report
            async def _preflight_report():
                try:
                    r = await _safe_thread_call(
                        build_investment_readiness_report,
                        state.session_log, state.grammar_buffer, state.structured_claims,
                        state.pitch_history, state.diligence_answered, state.full_transcript,
                        getattr(state, 'monotone_assessment', ''), # <--- Added monotone argument
                    )
                    state._preflight_report = r
                    logging.info("[PHASE] Pre-computed report ready.")
                except Exception as e:
                    logging.warning(f"[PHASE] Pre-compute report failed: {e}")
                    state._preflight_report = None
            asyncio.create_task(_preflight_report())

        # ── TRANSITION TO EVALUATING ──────────────────────────────────────────
        if elapsed >= PHASE_EVALUATING_S and state.phase != "evaluating":
            state.phase = "evaluating"
            logging.info("Phase → EVALUATING")
            try:
                await session.interrupt()
            except Exception:
                pass

            try:
                # Use the pre-computed report if it's ready; otherwise wait briefly
                report = getattr(state, '_preflight_report', None)
                if report is None:
                    logging.info("[PHASE] Pre-computed report not ready yet, computing now...")
                    report = await _safe_thread_call(
                        build_investment_readiness_report,
                        state.session_log, state.grammar_buffer, state.structured_claims,
                        state.pitch_history, state.diligence_answered, state.full_transcript,
                        getattr(state, 'monotone_assessment', ''), # <--- Added monotone argument
                    )
            except Exception as e:
                report = None
                logging.warning(f"Report generation failed: {e}")

            if report:
                import json as _json

                grade       = report.get("grade", "?")
                score       = report.get("score", 0)
                max_s       = report.get("max_score", 100)
                rubric_data = report.get("rubric", {})
                strength_keys   = report.get("strengths", [])
                weakness_keys   = report.get("critical_weaknesses", [])
                
                # Safely grab the first strength/weakness text for the script
                strength_notes  = [rubric_data[k]["notes"] for k in strength_keys if k in rubric_data]
                weakness_notes  = [rubric_data[k]["notes"] for k in weakness_keys if k in rubric_data]
                
                top_strength = strength_notes[0].lower().strip('.') if strength_notes else "your core concept"
                top_weakness = weakness_notes[0].lower().strip('.') if weakness_notes else "some missing details"
                final_verdict = report.get("final_verdict", "I'd need to see more traction before investing.")

                # Construct the spoken script natively so it cannot fail or be interrupted
                spoken_script = (
                    f"Alright, the pitch is over. I've compiled your Investment Readiness Review. "
                    f"Overall, I'm giving this pitch a {grade}. "
                    f"Your biggest strength was {top_strength}. "
                    f"However, the critical weakness that stood out was {top_weakness}. "
                    f"My final verdict? {final_verdict} "
                    "Keep iterating, you are definitely on the right track."
                )

                state.post_pitch_review = report

                # Save full report to disk for /report endpoint
                try:
                    with open(_SESSION_REPORT_PATH, "w", encoding="utf-8") as f:
                        _json.dump(report, f, indent=2, ensure_ascii=False)
                    logging.info(f"[REPORT] Saved to {_SESSION_REPORT_PATH}")
                except Exception as e:
                    logging.warning(f"Failed to save report JSON: {e}")

                logging.info("[PHASE] Speaking final verdict forcefully via session.say()")
                
                # FORCE the speech, ignoring user interruptions
                await session.say(spoken_script, allow_interruptions=False)
                await asyncio.sleep(5.0) 
                
                logging.info("Ending session automatically...")
                await ctx.room.disconnect() 
                break # Exit the while loop

            else:
                # Fallback: summarize from raw state data
                gram_count = len(state.grammar_buffer)
                raw_report_context = (
                    f"Time's up. Missing data. Caught {gram_count} grammar issues. "
                    "Main weaknesses: unclear metrics, unverified revenue."
                )

            try:
                await session.generate_reply(
                    instructions=(
                        f"The pitch is now completely over. Here is the raw final report data:\n{raw_report_context}\n"
                        "Deliver the final Investment Readiness Review NOW based on this data. "
                        "Do NOT read a nested list or bullet points. Speak naturally, like a human investor "
                        "giving their final thoughts face-to-face. Keep it conversational but direct, "
                        "summarizing their grade, biggest strength, biggest weakness, and your final verdict. "
                        "End with exactly ONE sentence of genuine encouragement."
                    )
                )
            except Exception as e:
                logging.warning(f"Phase watcher (evaluating generate_reply) error: {e}")

        # ── HARD CAP ─────────────────────────────────────────────────────────
        if elapsed >= PHASE_HARD_CAP_S and state.phase != "done":
            state.phase = "done"
            logging.info("Phase → DONE (hard cap)")
            try:
                await session.say(
                    "Time's up. That was a solid session — give me just a moment to pull together your Investment Readiness Review.",
                    allow_interruptions=False,
                )
            except Exception:
                pass

            # Deliver the report — use pre-computed if ready, otherwise compute now
            try:
                import json as _json
                report = getattr(state, '_preflight_report', None)
                if report is None:
                    logging.info("[HARD CAP] Pre-computed report not ready, computing now...")
                    report = await _safe_thread_call(
                        build_investment_readiness_report,
                        state.session_log, state.grammar_buffer, state.structured_claims,
                        state.pitch_history, state.diligence_answered, state.full_transcript,
                        getattr(state, 'monotone_assessment', ''), # <--- Added monotone argument
                    )

                if report:
                    grade          = report.get("grade", "?")
                    score          = report.get("score", 0)
                    max_s          = report.get("max_score", 100)
                    rubric_data    = report.get("rubric", {})
                    strength_keys  = report.get("strengths", [])
                    weakness_keys  = report.get("critical_weaknesses", [])
                    missing        = report.get("essentials_checklist", {}).get("missing", [])
                    killer_moments = report.get("investor_killer_moments", [])

                    strength_notes = [rubric_data[k]["notes"] for k in strength_keys if k in rubric_data]
                    weakness_notes = [rubric_data[k]["notes"] for k in weakness_keys if k in rubric_data]
                    grammar_events = [
                        m["detail"][:80] for m in killer_moments
                        if m.get("type") in ("grammar_and_fillers", "filler_overload")
                    ][:3]
                    contradiction_events = [
                        m["detail"][:80] for m in killer_moments
                        if m.get("type") in ("consistency", "Self-Contradiction")
                    ][:3]

                    raw_report_context = (
                        f"GRADE: {grade} ({score}/{max_s})\n"
                        f"STRENGTHS: {'. '.join(strength_notes)}\n"
                        f"WEAKNESSES: {'. '.join(weakness_notes)}\n"
                        f"CONTRADICTIONS: {'. '.join(contradiction_events)}\n"
                        f"GRAMMAR/FILLERS: {'. '.join(grammar_events)}\n"
                        f"MISSING: {', '.join(missing)}\n"
                    )
                    state.post_pitch_review = report

                    try:
                        with open(_SESSION_REPORT_PATH, "w", encoding="utf-8") as f:
                            _json.dump(report, f, indent=2, ensure_ascii=False)
                        logging.info(f"[REPORT] Saved to {_SESSION_REPORT_PATH}")
                    except Exception as e:
                        logging.warning(f"Failed to save report JSON: {e}")

                    await session.generate_reply(
                        instructions=(
                            f"Here is the raw final report data:\n{raw_report_context}\n"
                            "Deliver the final Investment Readiness Review NOW based on this data. "
                            "Do NOT read a nested list or bullet points. Speak naturally, like a human investor "
                            "giving their final thoughts face-to-face. Keep it conversational but direct, "
                            "summarizing their grade, biggest strength, biggest weakness, and your final verdict. "
                            "End with exactly ONE sentence of genuine encouragement."
                        )
                    )
                else:
                    await session.say(
                        "I wasn't able to compile the full report this time — but you pitched well. Keep working on it.",
                        allow_interruptions=False,
                    )
            except Exception as e:
                logging.warning(f"[HARD CAP] Report delivery error: {e}")
            break
# ═══════════════════════════════════════════════════════════════════════════════
# LIVEKIT ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════════

async def entrypoint(ctx: JobContext):
    """
    Called once per LiveKit room.
    """
    import time
    await ctx.connect()
    logging.info("Connected to LiveKit room.")

    state = LiveKitSessionState()
    state.reset()

    state.cheat_sheet  = _PREFLIGHT["cheat_sheet"]
    state.massive_docs = _PREFLIGHT["massive_docs"]
    state.voice_prompt = _PREFLIGHT["voice_prompt"]

    system_prompt = generate_agent_system_prompt(
        summary_cache=state.voice_prompt or str(state.cheat_sheet),
        state="listening",
    )

    session_ref: list = [None]

    agent = Agent(
        instructions=system_prompt,
        tools=_make_tools(state, session_ref),
    )

    session = AgentSession(
        vad=silero.VAD.load(min_speech_duration=0.1, min_silence_duration=2.0),
        stt=deepgram.STT(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            model="nova-2",
            language="en-US",
        ),
        # Switched to Groq
        llm=lk_openai.LLM(
            model="llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY_1"),
        ),
        # Deepgram TTS — robust, fast, no strict web socket limits
        tts=deepgram.TTS(
            model="aura-asteria-en",
        ),
    )

    session_ref[0] = session

    # Per-utterance streaming lock (prevents racing partials)
    streaming_lock = asyncio.Lock()
    # Gates the phase timer until greeting finishes
    greeting_done = asyncio.Event()

    @session.on("user_input_transcribed")
    def on_streaming_transcript(event):
        """LAYER A (streaming) + LAYER B (finals) handler."""
        import time
        if not hasattr(event, "transcript") or not event.transcript:
            return
        transcript = event.transcript.strip()
        if not transcript or state.phase == "done":
            return

        state.last_speech_time = time.time()

        if getattr(event, "is_final", False):
            # ── LAYER B: committed utterance ──────────────────────────────────
            state.full_transcript      += f" {transcript}"
            state.unhandled_transcript += f" {transcript}"
            logging.info(f"[FOUNDER] {transcript}")
            asyncio.create_task(_on_utterance(state, session, transcript))
        else:
            # ── LAYER A: streaming partial ────────────────────────────────────
            asyncio.create_task(
                _check_streaming_interrupt(state, session, transcript, streaming_lock)
            )

    @session.on("user_speech_committed")
    def on_user_speech(msg):
        """Fallback handler — updates last_speech_time if is_final wasn't caught above."""
        import time
        # Determine text from whichever attribute exists
        text = (
            getattr(msg, "text", None)
            or getattr(msg, "content", None)
            or ""
        )
        if isinstance(text, list):
            # ChatMessage content can be a list of parts
            text = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in text
            )
        text = str(text).strip()
        # Skip if already handled by on_streaming_transcript (is_final path)
        if text and text not in state.full_transcript[-len(text)-5:]:
            state.last_speech_time = time.time()
            logging.debug(f"[FOUNDER-FALLBACK] {text[:60]}")

    @session.on("agent_speech_committed")
    def on_agent_speech(msg):
        text = getattr(msg, "text", None) or getattr(msg, "content", "") or ""
        if isinstance(text, list):
            text = " ".join(str(p) for p in text)
        text = str(text).strip()
        if text:
            logging.info(f"[ALEX] {text[:120]}")
            state.log_event("agent_speech", "speech", text[:120])
    # ── HANG-UP INTERCEPTOR ─────────────────────────────────────────────────
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        logging.info(f"Founder {participant.identity} clicked END CALL. Cleaning up session...")

        # ── CRITICAL: set phase to 'done' SYNCHRONOUSLY ──────────────────────────
        # This immediately terminates the _phase_watcher, _silence_watcher, and
        # contradiction_watcher loops on their next iteration (all check state.phase).
        # Without this, the old agent stays in the room and answers the NEXT session.
        state.phase = "done"
        logging.info("[DISCONNECT] state.phase set to 'done' — all watchers will terminate.")

        async def generate_offline_report():
            try:
                # 1. Run the fast monotone check first
                from tools import detect_monotone
                mono_result = detect_monotone(state.feature_history)
                state.monotone_assessment = mono_result.get("assessment", "Not enough voice data.")

                # 2. Build transcript — use pitch_history as fallback if STT produced nothing
                #    (can happen when session is very short or user ended before speaking)
                transcript = state.full_transcript.strip()
                if not transcript:
                    if state.pitch_history:
                        transcript = " ".join(state.pitch_history)
                        logging.warning("[OFFLINE REPORT] full_transcript empty — using pitch_history as fallback.")
                    else:
                        logging.warning("[OFFLINE REPORT] Skipping report — no speech data captured (session too short).")
                        # Still disconnect cleanly even if no report
                        await asyncio.sleep(0.5)
                        try:
                            await ctx.room.disconnect()
                        except Exception:
                            pass
                        return

                logging.info("[OFFLINE REPORT] Building report via LLM...")

                # 3. Trigger the main report builder
                report = await _safe_thread_call(
                    build_investment_readiness_report,
                    state.session_log,
                    state.grammar_buffer,
                    state.structured_claims,
                    state.pitch_history,
                    state.diligence_answered,
                    transcript,
                    getattr(state, 'monotone_assessment', ''),
                )

                # 4. Save it to JSON
                if report:
                    import json as _json
                    with open(_SESSION_REPORT_PATH, "w", encoding="utf-8") as f:
                        _json.dump(report, f, indent=2, ensure_ascii=False)
                    logging.info(f"✅ [OFFLINE REPORT] Successfully saved to {_SESSION_REPORT_PATH}")
                else:
                    logging.warning("⚠️ [OFFLINE REPORT] LLM returned empty report.")

            except Exception as e:
                logging.error(f"[OFFLINE REPORT] Failed: {e}")

            finally:
                # 5. ALWAYS disconnect the agent from the room after report is done.
                #    This is the key fix for the double-agent problem: the agent must
                #    leave its room so the next session gets a clean agent.
                await asyncio.sleep(1)  # brief pause so LiveKit can flush any pending audio
                try:
                    await ctx.room.disconnect()
                    logging.info("[DISCONNECT] Agent disconnected from room. Session fully closed.")
                except Exception as disc_err:
                    logging.warning(f"[DISCONNECT] room.disconnect() failed: {disc_err}")

        # Fire off the generation + cleanup task
        asyncio.create_task(generate_offline_report())
    # ── Start session ─────────────────────────────────────────────────────────
    await session.start(room=ctx.room, agent=agent)

    # ── Fire greeting ─────────────────────────────────────────────────────────
    await session.generate_reply(instructions=GREETING_INSTRUCTION)

    # ── FIX 2: Start pitch clock AFTER greeting ───────────────────────────────
    import time
    state.session_start_ts = time.time()
    state.last_speech_time = time.time()
    greeting_done.set()

    logging.info("Greeting done. Pitch clock started. Waiting for founder...")

    asyncio.create_task(_silence_watcher(state, session))
    asyncio.create_task(contradiction_watcher(state, session))
    asyncio.create_task(_phase_watcher(state, session, ctx, greeting_done))

def build_agent_workflow():
    """
    Stateful LangGraph agent with MemorySaver checkpointing.

    Router logic:
      - If active_tool_call is set → run tool_node
      - Otherwise                  → run phase_node (time-based transitions)

    Both nodes return partial state updates; LangGraph merges them.
    """
    workflow = StateGraph(AgentState)
    workflow.add_node("execute_tool", tool_node)
    workflow.add_node("check_phase", phase_node)

    def router(state: AgentState):
        if state.get("active_tool_call"):
            return "execute_tool"
        return "check_phase"

    workflow.add_conditional_edges(START, router)
    workflow.add_edge("execute_tool", END)
    workflow.add_edge("check_phase", END)
    return workflow.compile(checkpointer=MemorySaver())



