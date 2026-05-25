"""
Tag Tools — Backward-Compatible Facade
=======================================
This module used to contain all tag-related functionality (518 lines, 6+
responsibilities). It has been refactored following the Single Responsibility
Principle into four focused modules:

  - ``decay``          — pure time-decay math (no I/O)
  - ``supabase_tags``  — Supabase read-only data access
  - ``neo4j_queries``  — Neo4j read/update queries (UCB, siblings, weights)
  - ``neo4j_sync``     — Neo4j write-path full sync

This file is now a thin re-export facade so that **all existing import
paths continue to work** without modification:

    from app.graph.feed_recommedation_agent.tools.tag_tools import fetch_investor_tags  # ✓ still works
"""

# ── Decay (pure math) ────────────────────────────────────────────────────────
from app.graph.feed_recommedation_agent.tools.decay import (       # noqa: F401
    _days_since_updated,
    _apply_decay,
    DECAY_HALF_LIFE_DAYS,
    DECAY_LAMBDA,
    MIN_DECAYED_WEIGHT,
    DECAY_DEFAULT_AGE_DAYS,
)

# ── Supabase data access ─────────────────────────────────────────────────────
from app.graph.feed_recommedation_agent.tools.supabase_tags import (  # noqa: F401
    fetch_unique_tags,
    fetch_investor_tags,
    fetch_all_investors,
    fetch_seen_pitchdeck_ids,
)

# ── Neo4j read/update queries ────────────────────────────────────────────────
from app.graph.feed_recommedation_agent.tools.neo4j_queries import (  # noqa: F401
    get_investor_subtags,
    get_sibling_subtags,
    update_graph_edge_weights,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    UCB_C,
    UCB_EXPLOIT_RATIO,
)

# ── Neo4j write-path sync ────────────────────────────────────────────────────
from app.graph.feed_recommedation_agent.tools.neo4j_sync import (    # noqa: F401
    sync_supabase_to_neo4j,
)

__all__ = [
    # Decay
    "_days_since_updated",
    "_apply_decay",
    "DECAY_HALF_LIFE_DAYS",
    "DECAY_LAMBDA",
    "MIN_DECAYED_WEIGHT",
    "DECAY_DEFAULT_AGE_DAYS",
    # Supabase
    "fetch_unique_tags",
    "fetch_investor_tags",
    "fetch_all_investors",
    "fetch_seen_pitchdeck_ids",
    # Neo4j queries
    "get_investor_subtags",
    "get_sibling_subtags",
    "update_graph_edge_weights",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "UCB_C",
    "UCB_EXPLOIT_RATIO",
    # Neo4j sync
    "sync_supabase_to_neo4j",
]