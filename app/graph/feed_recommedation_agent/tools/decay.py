"""
Time Decay Utilities
====================
Pure math functions for exponential time decay on Neo4j edge weights.

    W_eff = max( W · e^(−λ · Δt),  MIN_DECAYED_WEIGHT )

No I/O, no database calls — easily testable in isolation.

Single Responsibility: decay math only.
"""

import math
import os
from datetime import datetime, timezone


# ── Hyperparameters (environment-configurable) ────────────────────────────────
DECAY_HALF_LIFE_DAYS   = float(os.getenv("DECAY_HALF_LIFE_DAYS", "30"))
DECAY_LAMBDA           = math.log(2) / DECAY_HALF_LIFE_DAYS
MIN_DECAYED_WEIGHT     = float(os.getenv("MIN_DECAYED_WEIGHT", "0.05"))
DECAY_DEFAULT_AGE_DAYS = float(os.getenv("DECAY_DEFAULT_AGE_DAYS", "14"))


def _days_since_updated(neo4j_dt) -> float:
    """
    Convert a Neo4j DateTime (or None) to a float of days elapsed since then.

    None means the relationship pre-dates the last_updated column — we treat
    it as DECAY_DEFAULT_AGE_DAYS old rather than zero or infinity, so it
    receives a modest but non-zero penalty without being silenced.
    """
    if neo4j_dt is None:
        return DECAY_DEFAULT_AGE_DAYS

    # The Neo4j Python driver returns neo4j.time.DateTime objects.
    # .to_native() converts to a standard Python datetime (tz-aware).
    try:
        py_dt = neo4j_dt.to_native()
    except AttributeError:
        py_dt = neo4j_dt                    # already a Python datetime

    if py_dt.tzinfo is None:
        py_dt = py_dt.replace(tzinfo=timezone.utc)

    delta = datetime.now(timezone.utc) - py_dt
    return max(0.0, delta.total_seconds() / 86400)


def _apply_decay(weight: float, neo4j_dt) -> float:
    """
    Apply exponential time decay to a raw edge weight.

        W_eff = max( W · e^(−λ · Δt),  MIN_DECAYED_WEIGHT )

    The floor prevents a tag from dropping to zero just because the investor
    hasn't been online — stale doesn't mean irrelevant.
    """
    days   = _days_since_updated(neo4j_dt)
    w_eff  = weight * math.exp(-DECAY_LAMBDA * days)
    return max(w_eff, MIN_DECAYED_WEIGHT)
