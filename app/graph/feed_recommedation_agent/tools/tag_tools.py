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

def get_investor_subtags(user_id: str, hate_threshold: float = 0.01) -> list[str]:
    """
    Fetches SubTags explicitly tied to the investor.
    Calculates a 'Global Score' (Parent Weight * SubTag Weight) for perfect sorting.
    Filters out any sub-niches where the Parent Tag dropped below the threshold.
    """
    if not NEO4J_URI: return []
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    query = """
    // 1. Match the Investor, the SubTag, AND the Parent Tag
    MATCH (i:Investor {userId: $userId})-[rs:INTERESTED_IN_SUB]->(st:SubTag)<-[:CONTAINS]-(t:Tag)<-[rt:INTERESTED_IN]-(i)
    
    // 2. Extract weights safely
    WITH st.name AS SubTag, 
         coalesce(rt.weight, 0.5) AS parent_weight, 
         coalesce(rs.weight, 0.5) AS local_sub_weight
    
    // 3. Filter out hated categories (using the parent weight)
    WHERE parent_weight >= $threshold
    
    // 4. Calculate the true Global Priority Score and Sort
    RETURN SubTag
    ORDER BY (parent_weight * local_sub_weight) DESC, SubTag ASC
    """
    
    try:
        with driver.session() as session:
            result = session.run(query, userId=user_id, threshold=hate_threshold)
            return [record["SubTag"] for record in result]
    except Exception as e:
        logger.error(f"[Neo4j] Error fetching sorted subtags: {e}")
        return []
    finally:
        driver.close()


def _add_investor_node(tx, user_id, tags):
    # If the investor removed ALL their tags, wipe their connections completely
    if not tags: 
        tx.run("""
        MATCH (i:Investor {userId: $user_id})-[r]->()
        WHERE type(r) IN ['INTERESTED_IN', 'INTERESTED_IN_SUB']
        DELETE r
        """, user_id=user_id)
        return

    query = """
    // 1. Ensure Investor exists
    MERGE (i:Investor {userId: $user_id})
    WITH i

    // 2. CLEANSING: Delete Macro-Tags they no longer follow
    OPTIONAL MATCH (i)-[r_tag:INTERESTED_IN]->(t_old:Tag)
    WHERE NOT t_old.name IN $tags
    DELETE r_tag
    WITH DISTINCT i  // <-- FIX: Prevents Cartesian memory duplication

    // 3. CLEANSING: Delete Micro-SubTags if their Parent Tag is gone
    OPTIONAL MATCH (i)-[r_sub:INTERESTED_IN_SUB]->(st:SubTag)
    WHERE NOT EXISTS {
        MATCH (valid_t:Tag)-[:CONTAINS]->(st)
        WHERE valid_t.name IN $tags
    }
    DELETE r_sub
    WITH DISTINCT i  // <-- FIX: Prevents Cartesian memory duplication

    // 4. SYNC: Add or update valid Macro-Tags (Preserves RL weights!)
    UNWIND $tags AS tag_name
    MERGE (t:Tag {name: tag_name})
    MERGE (i)-[rt:INTERESTED_IN]->(t)
    ON CREATE SET rt.weight = 0.5, rt.impressions = 0
    WITH DISTINCT i

    // 5. NORMALIZE: Recalculate all Macro-Tags back to exactly 1.0
    MATCH (i)-[all_rt:INTERESTED_IN]->(:Tag)
    WITH i, sum(coalesce(all_rt.weight, 0.5)) AS total_t
    WHERE total_t > 0
    MATCH (i)-[norm_rt:INTERESTED_IN]->(:Tag)
    SET norm_rt.weight = coalesce(norm_rt.weight, 0.5) / total_t
    WITH DISTINCT i

    // 6. SYNC: Add or update valid Micro-SubTags (Preserves RL weights!)
    OPTIONAL MATCH (i)-[:INTERESTED_IN]->(t:Tag)-[:CONTAINS]->(st:SubTag)
    WITH i, st WHERE st IS NOT NULL
    MERGE (i)-[rs:INTERESTED_IN_SUB]->(st)
    ON CREATE SET rs.weight = 0.5, rs.impressions = 0
    WITH DISTINCT i

    // 7. NORMALIZE: Recalculate SubTags back to exactly 1.0 (Per Parent Category)
    MATCH (i)-[:INTERESTED_IN]->(t:Tag)
    WITH i, t
    OPTIONAL MATCH (i)-[all_rs:INTERESTED_IN_SUB]->(st:SubTag)<-[:CONTAINS]-(t)
    WITH i, t, sum(coalesce(all_rs.weight, 0.5)) AS total_st
    WHERE total_st > 0
    MATCH (i)-[norm_rs:INTERESTED_IN_SUB]->(st:SubTag)<-[:CONTAINS]-(t)
    SET norm_rs.weight = coalesce(norm_rs.weight, 0.5) / total_st
    """
    
    # Executes sequentially in one shot
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



def update_graph_edge_weights(user_id: str, tag_names: list[str], subtag_names: list[str], reward: float, alpha: float):
    if not NEO4J_URI: return
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    query = """
    // ==========================================
    // PHASE 1: MACRO-LEVEL (TAGS)
    // ==========================================
    MATCH (i:Investor {userId: $userId})-[rt:INTERESTED_IN]->(t:Tag)
    WHERE t.name IN $tagNames
    SET rt.impressions = coalesce(rt.impressions, 0) + 1
    WITH i, rt, coalesce(rt.weight, 0.5) + ($alpha * ($reward - coalesce(rt.weight, 0.5))) AS raw_t
    SET rt.weight = CASE WHEN raw_t < 0.01 THEN 0.01 ELSE raw_t END
    
    // Normalize ALL Tags to 1.0
    WITH i
    MATCH (i)-[all_rt:INTERESTED_IN]->(:Tag)
    WITH i, sum(coalesce(all_rt.weight, 0.5)) AS total_t
    MATCH (i)-[norm_rt:INTERESTED_IN]->(:Tag)
    SET norm_rt.weight = coalesce(norm_rt.weight, 0.5) / total_t

    // ==========================================
    // PHASE 2: MICRO-LEVEL (SUB-TAGS)
    // ==========================================
    WITH i
    UNWIND $subtagNames AS st_name
    MATCH (st:SubTag {name: st_name})
    
    // Merge just in case they interacted with a brand new subtag
    MERGE (i)-[rs:INTERESTED_IN_SUB]->(st)
    ON CREATE SET rs.weight = 0.5, rs.impressions = 0
    
    SET rs.impressions = rs.impressions + 1
    WITH i, rs, coalesce(rs.weight, 0.5) + ($alpha * ($reward - coalesce(rs.weight, 0.5))) AS raw_st
    SET rs.weight = CASE WHEN raw_st < 0.01 THEN 0.01 ELSE raw_st END
    
    // Normalize SubTags PER Parent Tag to 1.0
    WITH i
    MATCH (i)-[all_rs:INTERESTED_IN_SUB]->(st:SubTag)<-[:CONTAINS]-(t:Tag)
    WHERE t.name IN $tagNames  // Only re-normalize the categories that were altered
    WITH i, t, sum(coalesce(all_rs.weight, 0.5)) AS total_st
    MATCH (i)-[norm_rs:INTERESTED_IN_SUB]->(st:SubTag)<-[:CONTAINS]-(t)
    SET norm_rs.weight = coalesce(norm_rs.weight, 0.5) / total_st
    
    RETURN "Success"
    """
    
    try:
        with driver.session() as session:
            session.run(query, userId=user_id, tagNames=tag_names, subtagNames=subtag_names, reward=reward, alpha=alpha)
            logger.info(f"[RL Update] User {user_id} Hierarchical Update Complete.")
    except Exception as e:
        logger.error(f"[Neo4j] Error updating hierarchical weights: {e}")
    finally:
        driver.close()