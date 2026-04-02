"""
state.py — Shared state schemas for the Spark2Scale Pitch Coach.

CHANGES IN THIS VERSION:
  FIX 1 — interrupt_lock (asyncio.Lock) added to LiveKitSessionState.
           All three interrupt paths (streaming, committed, watcher) must acquire
           this lock before firing. Only one interrupt fires per cooldown window.

  FIX 2 — Default cooldown raised 8s → 10s.
"""

import asyncio
import operator
from typing import TypedDict, Annotated, List, Dict, Any, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# LANGGRAPH STATE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class PitchState(TypedDict):
    raw_documents: dict
    cheat_sheet:   dict | None
    voice_prompt:  str  | None


class AgentState(TypedDict):
    phase:         str
    system_prompt: str

    pitch_history:     Annotated[List[str], operator.add]
    massive_docs:      dict
    structured_claims: dict

    active_tool_call: Dict[str, Any]
    tool_output:      str

    time_elapsed:     float
    trigger_update:   bool
    last_pause_start: Optional[float]

    grammar_buffer:         Annotated[List[dict], operator.add]
    grammar_buffer_flushed: bool

    nervousness_score: float

    session_log:   Annotated[List[dict], operator.add]
    interrupt_log: Annotated[List[dict], operator.add]
    audio_metrics: Annotated[List[dict], operator.add]

    calibration_rms_baseline: float

    diligence_answered: Annotated[List[str], operator.add]
    post_pitch_review:  Optional[str]


# ═══════════════════════════════════════════════════════════════════════════════
# LIVEKIT SESSION STATE
# ═══════════════════════════════════════════════════════════════════════════════

class LiveKitSessionState:
    """
    Holds all mutable state for one LiveKit pitch coaching session.
    One instance is created per room connection inside entrypoint().
    """

    def __init__(self):
        # ── Company Context ────────────────────────────────────────────────────
        self.cheat_sheet:  dict = {}
        self.massive_docs: dict = {}
        self.voice_prompt: str  = ""

        # ── Pitch memory ───────────────────────────────────────────────────────
        self.pitch_history:        List[str] = []
        self.full_transcript:      str       = ""
        self.unhandled_transcript: str       = ""
        self.structured_claims:    dict      = {}
        self.diligence_answered:   List[str] = []

        # ── Session audit log ──────────────────────────────────────────────────
        self.session_log:    List[dict] = []
        self.grammar_buffer: List[dict] = []

        # ── Phase ──────────────────────────────────────────────────────────────
        self.phase: str = "listening"   # listening | interrogating | evaluating | done

        # ── Timing ────────────────────────────────────────────────────────────
        self.session_start_ts:          float = 0.0
        self.last_interrupt_ts:         float = 0.0
        self.last_grammar_interrupt_ts: float = 0.0
        self.last_speech_time:          float = 0.0
        self.last_streaming_check_time: float = 0.0

        # ── Audio / nervousness ────────────────────────────────────────────────
        self.feature_history:          List[dict] = []
        self.nervousness_score:        float      = 0.0
        self.calibration_rms_baseline: float      = 0.004
        self.calibration_done:         bool       = False
        self.calibration_done_ts:      float      = 0.0

        # ── FIX 1: Global interrupt lock ───────────────────────────────────────
        # All three interrupt paths MUST go through _try_interrupt() which holds
        # this lock.  The double-check pattern (check → lock → re-check) ensures
        # only one interrupt fires even when multiple async tasks pass the first
        # can_interrupt() call simultaneously.
        self.interrupt_lock: asyncio.Lock = asyncio.Lock()

        # ── Final review ───────────────────────────────────────────────────────
        self.post_pitch_review: Optional[str] = None

    def reset(self):
        """Re-initialise all fields. Call at the start of each entrypoint() call."""
        self.__init__()

    def log_event(self, event_type: str, reason: str, detail: str):
        """Append a timestamped entry to session_log."""
        import time
        elapsed = time.time() - self.session_start_ts
        self.session_log.append({
            "event":     event_type,
            "reason":    reason,
            "timestamp": round(elapsed, 1),
            "detail":    detail,
        })

    def can_interrupt(
        self,
        cooldown_s: float = 10.0,          # FIX 2: raised from 8s → 10s
        grammar_cooldown_s: float = 20.0,
        priority: int = 3,
    ) -> bool:
        """
        Returns True if enough time has passed since the last interrupt.

        Priority tiers:
          5 → consistency / document conflict  (10s cooldown)
          3 → grammar errors                   (10s cooldown)
          2 → filler words / nervousness        (also enforces grammar_cooldown_s)
        """
        import time
        now = time.time()
        if (now - self.last_interrupt_ts) < cooldown_s:
            return False
        if priority <= 2 and (now - self.last_grammar_interrupt_ts) < grammar_cooldown_s:
            return False
        return True

    def mark_interrupted(self, priority: int = 3):
        """Record that an interrupt just fired. Updates both timestamp fields."""
        import time
        now = time.time()
        self.last_interrupt_ts = now
        if priority <= 2:
            self.last_grammar_interrupt_ts = now