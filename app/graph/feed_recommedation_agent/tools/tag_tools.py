"""
Tag Tools
=========
Functions that query the Supabase `investors` table for tag data.

Database reference:
    investors.tags  — text[] column storing each investor's interest tags.
"""

from typing import Optional
from app.core.supabase_client import supabase
from app.core.logger import get_logger

logger = get_logger(__name__)


def fetch_unique_tags() -> list[str]:
    """
    Return the de-duplicated union of all tags across every investor row.

    Returns:
        Sorted list of unique tag strings.
    """
    if not supabase:
        logger.error("[TagTools] Supabase client is not initialised.")
        return []

    resp = supabase.table("investors").select("tags").execute()
    if not resp.data:
        return []

    seen: set[str] = set()
    for row in resp.data:
        for tag in (row.get("tags") or []):
            seen.add(tag.strip().lower())

    unique = sorted(seen)
    logger.info(f"[TagTools] Found {len(unique)} unique tags across all investors.")
    return unique


def fetch_investor_tags(investor_id: str) -> list[str]:
    """
    Return the tags list for a single investor.

    Args:
        investor_id: UUID of the investor (maps to investors.user_id).

    Returns:
        List of tag strings; empty list if investor not found.
    """
    if not supabase:
        logger.error("[TagTools] Supabase client is not initialised.")
        return []

    resp = (
        supabase.table("investors")
        .select("tags")
        .eq("user_id", investor_id)
        .single()
        .execute()
    )
    tags = (resp.data or {}).get("tags") or []
    logger.info(f"[TagTools] Investor {investor_id} has {len(tags)} tags.")
    return [t.strip().lower() for t in tags]


def fetch_all_investors() -> list[dict]:
    """
    Return every investor row (user_id + tags).

    Returns:
        List of dicts with keys 'user_id' and 'tags'.
    """
    if not supabase:
        logger.error("[TagTools] Supabase client is not initialised.")
        return []

    resp = supabase.table("investors").select("user_id, tags").execute()
    return resp.data or []