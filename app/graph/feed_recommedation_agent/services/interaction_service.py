"""
Interaction Service
===================
Encapsulates the business logic for handling investor interactions
(like, dislike, contact) with pitch decks.

Extracted from the ``/interactions`` route handler to follow the
Single Responsibility Principle — the route stays thin (parse → delegate → respond).

Open/Closed: new interaction types only require updating ``InteractionType``
and ``REWARD_MATRIX`` — this service does not need modification.
"""

import json as _json
from typing import Any

from app.core.supabase_client import supabase
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.rewards import REWARD_MATRIX, InteractionType

logger = get_logger(__name__)


class InteractionService:
    """
    Handles the business logic for processing investor-pitchdeck interactions.

    Responsibilities:
      1. Resolve interaction type from payload
      2. Fetch pitchdeck tags from Supabase
      3. Return structured data for background task dispatch
    """

    @staticmethod
    def resolve_interaction(payload: Any) -> tuple[InteractionType, str]:
        """
        Determine the interaction type from the payload.

        Returns:
            (InteractionType enum value, human-readable string)
        """
        return InteractionType.from_payload(
            liked=payload.liked,
            contacted=payload.contacted,
        )

    @staticmethod
    def fetch_pitchdeck_tags(pitch_id: str) -> dict:
        """
        Fetch pitchdeck analysis tags from Supabase.

        Returns:
            Dict with keys: 'parent_tags', 'sub_tags', 'raw_tags'

        Raises:
            RuntimeError: If the Supabase query fails.
        """
        try:
            response = supabase.table("pitchdecks").select("analysis, tags").eq(
                "pitchdeckid", pitch_id
            ).single().execute()

            raw_tags = response.data.get("tags") or []
            analysis = response.data.get("analysis", {})
            if isinstance(analysis, str):
                analysis = _json.loads(analysis)

            tags_dict   = analysis.get("sub_tags", {}) if isinstance(analysis, dict) else {}
            parent_tags = list(tags_dict.keys())
            sub_tags    = [st for sts in tags_dict.values() for st in sts]

            return {
                "parent_tags": parent_tags,
                "sub_tags": sub_tags,
                "raw_tags": raw_tags,
            }
        except Exception as e:
            logger.error("Failed to fetch tags for pitch %s: %s", pitch_id, e)
            raise RuntimeError(f"Database error: {str(e)}") from e

    @staticmethod
    def get_reward_config(action_type: InteractionType):
        """
        Look up the reward configuration for a given interaction type.

        Returns:
            RewardConfig with reward, alpha, and vector_beta values.
        """
        return REWARD_MATRIX.get(action_type)

    @staticmethod
    def build_success_message(
        action_type: InteractionType,
        parent_tags: list[str],
    ) -> dict:
        """Build the success response dict."""
        return {
            "status": "success",
            "message": (
                f"Registered {action_type.value}. "
                f"Neo4j + sub-vector update running in background for tags: {', '.join(parent_tags)}."
            ),
        }
