"""
Neo4j Write-Path Sync
=====================
Functions that perform full Supabase → Neo4j synchronisation:
  - ``sync_supabase_to_neo4j``  — bulk sync of investors and pitchdecks
  - ``_add_investor_node``      — upsert one investor + tag edges
  - ``_add_pitch_node``         — upsert one pitchdeck + tag/subtag edges
  - ``_prune_stale_nodes``      — delete Neo4j records absent from Supabase

Single Responsibility: Neo4j write-path sync only.
"""

import json

from neo4j import GraphDatabase

from app.core.config import config
from app.core.supabase_client import supabase
from app.core.logger import get_logger

logger = get_logger(__name__)

# Neo4j connection details
NEO4J_URI      = config.NEO4J_URI
NEO4J_USER     = config.NEO4J_USERNAME
NEO4J_PASSWORD = config.NEO4J_PASSWORD


def _add_investor_node(tx, user_id, tags):
    """Upsert one investor and its tag/subtag edges in Neo4j."""
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
        rt.last_updated = datetime()
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
        rs.last_updated = datetime()
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
    """Upsert one pitchdeck and its tag/subtag edges in Neo4j."""
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
