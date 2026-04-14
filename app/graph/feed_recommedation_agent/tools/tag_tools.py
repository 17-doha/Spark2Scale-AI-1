"""
Tag Tools
=========
Functions that query the Supabase `investors` table for tag data.

Database reference:
    investors.tags  — text[] column storing each investor's interest tags.
"""

from typing import Optional
import math
import os
import json
from neo4j import GraphDatabase
from app.core.config import config
from app.core.supabase_client import supabase
from app.core.logger import get_logger
from datetime import datetime, timezone

logger = get_logger(__name__)

# Neo4j Details
NEO4J_URI = config.NEO4J_URI
NEO4J_USER = config.NEO4J_USERNAME
NEO4J_PASSWORD = config.NEO4J_PASSWORD

UCB_C = float(os.getenv("UCB_C", "1.414"))
UCB_EXPLOIT_RATIO = float(os.getenv("UCB_EXPLOIT_RATIO", "0.8"))
DECAY_HALF_LIFE_DAYS  = float(os.getenv("DECAY_HALF_LIFE_DAYS", "30"))
DECAY_LAMBDA          = math.log(2) / DECAY_HALF_LIFE_DAYS
MIN_DECAYED_WEIGHT    = float(os.getenv("MIN_DECAYED_WEIGHT", "0.05"))
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


# ════════════════════════════════════════════════════════════════════════════
#  Neo4j Retrieval & Sync
# ════════════════════════════════════════════════════════════════════════════
def get_investor_subtags(
    user_id: str,
    hate_threshold: float = 0.01,
    limit: int = 50,
) -> list[str]:
    if not NEO4J_URI:
        return []

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # ── now returns last_updated so Python can apply decay ───────────────────
    query = """
    MATCH (i:Investor {userId: $userId})-[rs:INTERESTED_IN_SUB]->(st:SubTag)
          <-[:CONTAINS]-(t:Tag)<-[rt:INTERESTED_IN]-(i)
    WHERE coalesce(rt.weight, 0.5) >= $threshold
    RETURN
        st.name                          AS SubTag,
        coalesce(rs.weight, 0.5)         AS weight,
        coalesce(rs.impressions, 0)      AS impressions,
        rs.last_updated                  AS last_updated   // ← Task 3 addition
    """

    try:
        with driver.session() as session:
            rows = [
                {
                    "subtag"      : r["SubTag"],
                    "weight"      : r["weight"],
                    "impressions" : r["impressions"],
                    "last_updated": r["last_updated"],
                }
                for r in session.run(query, userId=user_id, threshold=hate_threshold)
            ]
    except Exception as e:
        logger.error("[Neo4j] Error fetching subtags for UCB: %s", e)
        return []
    finally:
        driver.close()

    if not rows:
        return []

    # ── Task 3: apply time decay to raw weight before any scoring ────────────
    for r in rows:
        r["decayed_weight"] = _apply_decay(r["weight"], r["last_updated"])

    # ── Task 1: UCB scoring (now on decayed weight) ──────────────────────────
    N = sum(r["impressions"] for r in rows)

    for r in rows:
        n_i = r["impressions"]
        w_d = r["decayed_weight"]           # ← decayed weight, not raw
        if n_i == 0 or N == 0:
            r["ucb"] = float("inf")
        else:
            r["ucb"] = w_d + UCB_C * math.sqrt(math.log(N) / n_i)

    # ── 80/20 split (unchanged from Task 1) ──────────────────────────────────
    exploit_n = max(1, round(limit * UCB_EXPLOIT_RATIO))
    explore_n = limit - exploit_n

    exploit_pool = sorted(rows, key=lambda r: r["decayed_weight"], reverse=True)
    exploit_tags = [r["subtag"] for r in exploit_pool[:exploit_n]]
    exploit_set  = set(exploit_tags)

    explore_pool = sorted(
        (r for r in rows if r["subtag"] not in exploit_set),
        key=lambda r: r["ucb"],
        reverse=True,
    )
    explore_tags = [r["subtag"] for r in explore_pool[:explore_n]]

    final = exploit_tags + explore_tags

    logger.info(
        "[UCB+Decay] investor=%s  N=%d  λ=%.4f  exploit=%d  explore=%d  total=%d",
        user_id, N, DECAY_LAMBDA, len(exploit_tags), len(explore_tags), len(final),
    )
    return final

def _add_investor_node(tx, user_id, tags):
    if not tags:
        tx.run("""
        MATCH (i:Investor {userId: $user_id})-[r]->()
        WHERE type(r) IN ['INTERESTED_IN', 'INTERESTED_IN_SUB']
        DELETE r
        """, user_id=user_id)
        return

    query = """
    MERGE (i:Investor {userId: $user_id})
    WITH i

    OPTIONAL MATCH (i)-[r_tag:INTERESTED_IN]->(t_old:Tag)
    WHERE NOT t_old.name IN $tags
    DELETE r_tag
    WITH DISTINCT i

    OPTIONAL MATCH (i)-[r_sub:INTERESTED_IN_SUB]->(st:SubTag)
    WHERE NOT EXISTS {
        MATCH (valid_t:Tag)-[:CONTAINS]->(st)
        WHERE valid_t.name IN $tags
    }
    DELETE r_sub
    WITH DISTINCT i

    UNWIND $tags AS tag_name
    MERGE (t:Tag {name: tag_name})
    MERGE (i)-[rt:INTERESTED_IN]->(t)
    ON CREATE SET
        rt.weight       = 0.5,
        rt.impressions  = 0,
        rt.last_updated = datetime()          // ← Task 3 addition
    WITH DISTINCT i

    MATCH (i)-[all_rt:INTERESTED_IN]->(:Tag)
    WITH i, sum(coalesce(all_rt.weight, 0.5)) AS total_t
    WHERE total_t > 0
    MATCH (i)-[norm_rt:INTERESTED_IN]->(:Tag)
    SET norm_rt.weight = coalesce(norm_rt.weight, 0.5) / total_t
    WITH DISTINCT i

    OPTIONAL MATCH (i)-[:INTERESTED_IN]->(t:Tag)-[:CONTAINS]->(st:SubTag)
    WITH i, st WHERE st IS NOT NULL
    MERGE (i)-[rs:INTERESTED_IN_SUB]->(st)
    ON CREATE SET
        rs.weight       = 0.5,
        rs.impressions  = 0,
        rs.last_updated = datetime()          // ← Task 3 addition
    WITH DISTINCT i

    MATCH (i)-[:INTERESTED_IN]->(t:Tag)
    WITH i, t
    OPTIONAL MATCH (i)-[all_rs:INTERESTED_IN_SUB]->(st:SubTag)<-[:CONTAINS]-(t)
    WITH i, t, sum(coalesce(all_rs.weight, 0.5)) AS total_st
    WHERE total_st > 0
    MATCH (i)-[norm_rs:INTERESTED_IN_SUB]->(st:SubTag)<-[:CONTAINS]-(t)
    SET norm_rs.weight = coalesce(norm_rs.weight, 0.5) / total_st
    """
    tx.run(query, user_id=user_id, tags=tags)

def _add_pitch_node(tx, pitch_id, sub_tags_dict):
    query = """
    MERGE (p:PitchDeck {pitchId: $pitch_id})
    WITH p
    UNWIND keys($sub_tags_dict) AS parent_tag_name
    MERGE (t:Tag {name: parent_tag_name})
    MERGE (p)-[:TAGGED_WITH]->(t)
    WITH p, t, parent_tag_name, $sub_tags_dict AS full_dict
    UNWIND full_dict[parent_tag_name] AS sub_tag_name
    MERGE (st:SubTag {name: sub_tag_name})
    MERGE (t)-[:CONTAINS]->(st)
    MERGE (p)-[:HAS_SUBTAG]->(st)
    """
    tx.run(query, pitch_id=pitch_id, sub_tags_dict=sub_tags_dict)



def _prune_stale_nodes(tx, valid_investor_ids, valid_pitch_ids):
    """Deletes nodes in Neo4j that no longer exist in Supabase, and cleans up orphaned tags."""
    
    # 1. Delete stale investors
    tx.run("""
        MATCH (i:Investor)
        WHERE NOT i.userId IN $valid_investor_ids
        DETACH DELETE i
    """, valid_investor_ids=valid_investor_ids)

    # 2. Delete stale pitch decks
    tx.run("""
        MATCH (p:PitchDeck)
        WHERE NOT p.pitchId IN $valid_pitch_ids
        DETACH DELETE p
    """, valid_pitch_ids=valid_pitch_ids)

    # 3. Clean up orphaned SubTags (SubTags with no connections)
    tx.run("""
        MATCH (st:SubTag)
        WHERE NOT ()-->(st) AND NOT (st)-->()
        DELETE st
    """)

    # 4. Clean up orphaned Tags (Tags with no connections)
    tx.run("""
        MATCH (t:Tag)
        WHERE NOT ()-->(t) AND NOT (t)-->()
        DELETE t
    """)

def sync_supabase_to_neo4j():
    """
    Performs a full refresh of the Neo4j graph from Supabase data.
    Includes pruning of deleted records and ensures the correct order of operations
    (Pitches first to build taxonomy, Investors second to link to it).
    """
    logger.info("[Neo4j] Starting Supabase to Neo4j Sync...")
    
    if not supabase:
        logger.error("[Neo4j] Supabase client not initialized.")
        return
    if not NEO4J_URI:
        logger.error("[Neo4j] URI not configured.")
        return

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        with driver.session() as session:
            # --- Fetch Source Data ---
            investors = supabase.table("investors").select("*").execute().data or []
            pitches = supabase.table("pitchdecks").select("*").execute().data or []

            valid_investor_ids = [inv.get("user_id") for inv in investors if inv.get("user_id")]
            valid_pitch_ids = [pitch.get("pitchdeckid") for pitch in pitches if pitch.get("pitchdeckid")]

            # --- 1. PRUNE STALE DATA ---
            logger.info("[Neo4j] Pruning stale records...")
            session.execute_write(_prune_stale_nodes, valid_investor_ids, valid_pitch_ids)

            # --- 2. SYNC PITCHES FIRST (Builds the Tag/SubTag Taxonomy) ---
            loaded, skipped = 0, 0
            for pitch in pitches:
                p_id = pitch.get("pitchdeckid")
                analysis = pitch.get("analysis")

                # Safely handle stringified JSON
                if isinstance(analysis, str):
                    try: 
                        analysis = json.loads(analysis)
                    except Exception: 
                        analysis = {}
                
                sub_tags = analysis.get("sub_tags", {}) if isinstance(analysis, dict) else {}

                if p_id and sub_tags:
                    session.execute_write(_add_pitch_node, p_id, sub_tags)
                    loaded += 1
                else:
                    skipped += 1

            # --- 3. SYNC INVESTORS SECOND (Links to the built taxonomy) ---
            for inv in investors:
                session.execute_write(_add_investor_node, inv.get("user_id"), inv.get("tags", []))
            
            logger.info(f"[Neo4j] Sync Complete: {len(investors)} Investors, {loaded} Pitches ({skipped} skipped).")
            
    except Exception as e:
        logger.error(f"[Neo4j] Sync Failed: {e}")
    finally:
        driver.close()



def update_graph_edge_weights(
    user_id: str,
    tag_names: list[str],
    subtag_names: list[str],
    reward: float,
    alpha: float,
):
    if not NEO4J_URI:
        return
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    query = """
    // ── PHASE 1: MACRO TAGS ───────────────────────────────────────────────────
    MATCH (i:Investor {userId: $userId})-[rt:INTERESTED_IN]->(t:Tag)
    WHERE t.name IN $tagNames
    SET
        rt.impressions  = coalesce(rt.impressions, 0) + 1,
        rt.last_updated = datetime()                       // ← Task 3 addition
    WITH i, rt,
         coalesce(rt.weight, 0.5) + ($alpha * ($reward - coalesce(rt.weight, 0.5))) AS raw_t
    SET rt.weight = CASE WHEN raw_t < 0.01 THEN 0.01 ELSE raw_t END

    WITH i
    MATCH (i)-[all_rt:INTERESTED_IN]->(:Tag)
    WITH i, sum(coalesce(all_rt.weight, 0.5)) AS total_t
    MATCH (i)-[norm_rt:INTERESTED_IN]->(:Tag)
    SET norm_rt.weight = coalesce(norm_rt.weight, 0.5) / total_t

    // ── PHASE 2: MICRO SUBTAGS ────────────────────────────────────────────────
    WITH i
    UNWIND $subtagNames AS st_name
    MATCH (st:SubTag {name: st_name})
    MERGE (i)-[rs:INTERESTED_IN_SUB]->(st)
    ON CREATE SET rs.weight = 0.5, rs.impressions = 0, rs.last_updated = datetime()

    SET
        rs.impressions  = rs.impressions + 1,
        rs.last_updated = datetime()                       // ← Task 3 addition
    WITH i, rs,
         coalesce(rs.weight, 0.5) + ($alpha * ($reward - coalesce(rs.weight, 0.5))) AS raw_st
    SET rs.weight = CASE WHEN raw_st < 0.01 THEN 0.01 ELSE raw_st END

    WITH i
    MATCH (i)-[all_rs:INTERESTED_IN_SUB]->(st:SubTag)<-[:CONTAINS]-(t:Tag)
    WHERE t.name IN $tagNames
    WITH i, t, sum(coalesce(all_rs.weight, 0.5)) AS total_st
    MATCH (i)-[norm_rs:INTERESTED_IN_SUB]->(st:SubTag)<-[:CONTAINS]-(t)
    SET norm_rs.weight = coalesce(norm_rs.weight, 0.5) / total_st

    RETURN "Success"
    """

    try:
        with driver.session() as session:
            session.run(
                query,
                userId=user_id,
                tagNames=tag_names,
                subtagNames=subtag_names,
                reward=reward,
                alpha=alpha,
            )
            logger.info("[RL Update] User %s hierarchical update + decay clock reset.", user_id)
    except Exception as e:
        logger.error("[Neo4j] Error updating hierarchical weights: %s", e)
    finally:
        driver.close()

def get_sibling_subtags(
    subtag_names: list[str],
    exclude: Optional[list[str]] = None,
    limit: int = 30,
) -> list[str]:
    """
    For a list of SubTag names, find their siblings in Neo4j —
    i.e. other SubTags that share at least one parent Tag.

    Used as the hierarchical fallback when Qdrant returns too few candidates.

    Args:
        subtag_names: The investor's current filter_tags (SubTag names).
        exclude:      Tags to omit from the result (e.g. tags already searched).
        limit:        Cap on returned sibling names.

    Returns:
        List of sibling SubTag name strings, ordered by parent Tag frequency
        (siblings sharing more parents with the query set rank higher).
    """
    if not NEO4J_URI or not subtag_names:
        return []

    exclude_set = set(subtag_names) | set(exclude or [])

    # Rank siblings by how many of the investor's subtags share the same parent.
    # A sibling that appears under 3 matching parent tags ranks above one that
    # appears under only 1 — it is more "central" to the investor's interests.
    query = """
    UNWIND $subtag_names AS name
    MATCH (st:SubTag {name: name})<-[:CONTAINS]-(t:Tag)-[:CONTAINS]->(sibling:SubTag)
    WHERE NOT sibling.name IN $exclude
    RETURN sibling.name AS SiblingSubTag, count(DISTINCT t) AS shared_parents
    ORDER BY shared_parents DESC, SiblingSubTag ASC
    LIMIT $limit
    """

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            result = session.run(
                query,
                subtag_names=subtag_names,
                exclude=list(exclude_set),
                limit=limit,
            )
            siblings = [r["SiblingSubTag"] for r in result]
        logger.info(
            "[Neo4j] Sibling fallback: %d input subtags → %d siblings found.",
            len(subtag_names), len(siblings),
        )
        return siblings
    except Exception as e:
        logger.error("[Neo4j] get_sibling_subtags failed: %s", e)
        return []
    finally:
        driver.close()