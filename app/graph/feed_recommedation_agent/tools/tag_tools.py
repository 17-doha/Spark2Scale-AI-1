"""
Tag Tools
=========
Functions that query the Supabase `investors` table for tag data.

Database reference:
    investors.tags  — text[] column storing each investor's interest tags.
"""

from typing import Optional
import json
from neo4j import GraphDatabase
from app.core.config import config
from app.core.supabase_client import supabase
from app.core.logger import get_logger

logger = get_logger(__name__)

# Neo4j Details
NEO4J_URI = config.NEO4J_URI
NEO4J_USER = config.NEO4J_USERNAME
NEO4J_PASSWORD = config.NEO4J_PASSWORD


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

def get_investor_subtags(user_id: str) -> list[str]:
    """
    Fetches a simple list of unique sub-tag names for a specific investor.
    Used by the FastAPI endpoint to personalize recommendations.
    """
    if not NEO4J_URI:
        logger.warning("[Neo4j] URI not configured, skipping sub-tag retrieval.")
        return []

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    query = """
    MATCH (i:Investor {userId: $userId})-[r:INTERESTED_IN]->(t:Tag)-[:CONTAINS]->(st:SubTag)
    RETURN DISTINCT st.name AS SubTag
    ORDER BY SubTag ASC
    """
    
    try:
        with driver.session() as session:
            result = session.run(query, userId=user_id)
            subtags_list = [record["SubTag"] for record in result]
            logger.info(f"[Neo4j] Found {len(subtags_list)} sub-tags for investor {user_id}.")
            return subtags_list
    except Exception as e:
        logger.error(f"[Neo4j] Error fetching subtags: {e}")
        return []
    finally:
        driver.close()


def _add_investor_node(tx, user_id, tags):
    if not tags: return
    query = """
    MERGE (i:Investor {userId: $user_id})
    WITH i
    UNWIND $tags AS tag_name
    MERGE (t:Tag {name: tag_name})
    MERGE (i)-[r:INTERESTED_IN]->(t)
    ON CREATE SET r.weight = 1.0
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


def sync_supabase_to_neo4j():
    """
    Performs a full refresh of the Neo4j graph from Supabase data.
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
            # --- Sync Investors ---
            investors = supabase.table("investors").select("*").execute().data
            for inv in investors:
                session.execute_write(_add_investor_node, inv.get("user_id"), inv.get("tags", []))
            
            # --- Sync Pitches ---
            pitches = supabase.table("pitchdecks").select("*").execute().data
            loaded, skipped = 0, 0

            for pitch in pitches:
                p_id = pitch.get("pitchdeckid")
                analysis = pitch.get("analysis")

                # Handle potential stringified JSON
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
            
            logger.info(f"[Neo4j] Sync Complete: {len(investors)} Investors, {loaded} Pitches ({skipped} skipped).")
            
    except Exception as e:
        logger.error(f"[Neo4j] Sync Failed: {e}")
    finally:
        driver.close()