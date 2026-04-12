"""
supabase_report.py
──────────────────
Saves the pitch analyzer's generated session report to the Supabase
`pitchdecks` table in the `session_report` JSONB column.

This module is intentionally thin and fault-tolerant:
  - It NEVER raises exceptions to the caller.
  - A failed Supabase write logs a warning and returns False.
  - The main report flow is never blocked by this module.
"""

import logging
import sys
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def save_report_to_supabase(pitchdeckid: str, report: dict) -> bool:
    """
    Updates `pitchdecks.session_report` for the given pitchdeckid.

    Args:
        pitchdeckid: UUID string of the target pitch deck row.
        report:      The full report dict from build_investment_readiness_report().

    Returns:
        True  — Supabase row was updated successfully.
        False — Update failed (logged as a warning). Caller should continue normally.
    """
    if not pitchdeckid:
        logger.warning("[SUPABASE] save_report_to_supabase called with empty pitchdeckid — skipping.")
        return False

    try:
        # Import the Supabase client from the core module.
        # We add the project root to sys.path so this works whether
        # called from the FastAPI process or the worker subprocess.
        _project_root = str(Path(__file__).resolve().parents[3])
        if _project_root not in sys.path:
            sys.path.insert(0, _project_root)

        from app.core.supabase_client import supabase  # type: ignore

        if supabase is None:
            logger.warning("[SUPABASE] Supabase client not initialized — cannot save session report.")
            return False

        result = (
            supabase
            .table("pitchdecks")
            .update({"session_report": report})
            .eq("pitchdeckid", pitchdeckid)
            .execute()
        )

        # PostgREST returns a list of updated rows — empty list means no row matched.
        if result.data is not None and len(result.data) > 0:
            logger.info(f"[SUPABASE] ✅ session_report saved for pitchdeckid={pitchdeckid}")
            return True
        else:
            logger.warning(
                f"[SUPABASE] No row found for pitchdeckid={pitchdeckid} — "
                "report was generated but not persisted to Supabase."
            )
            return False

    except Exception as exc:
        logger.warning(f"[SUPABASE] Failed to save session_report: {exc}")
        return False
