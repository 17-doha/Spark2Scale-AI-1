import json
from typing import List, Dict, Any
from supabase import create_client, Client
from neo4j import GraphDatabase
from app.core.config import config
from app.utils.logger import logger

# ==========================================
# 1. CONNECTION INITIALIZATION
# ==========================================
# Neo4j Details
NEO4J_URI = config.NEO4J_URI
NEO4J_USER = config.NEO4J_USERNAME
NEO4J_PASSWORD = config.NEO4J_PASSWORD

# Supabase Details
SUPABASE_URL = config.SUPABASE_URL
SUPABASE_KEY = config.SUPABASE_KEY 

# ==========================================
# 2. RETRIEVAL LOGIC (For the API)
# ==========================================

def get_investor_subtags(user_id: str) -> List[str]:
    """
    Fetches a simple list of unique sub-tag names for a specific investor.
    Used by the FastAPI endpoint to personalize recommendations.
    """
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
            return subtags_list
    except Exception as e:
        logger.error(f"Error fetching subtags from Neo4j: {e}")
        return []
    finally:
        driver.close()

# ==========================================
# 3. SYNC LOGIC (Internal DB Management)
# ==========================================

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
    logger.info("Starting Supabase to Neo4j Sync...")
    
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
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
                    try: analysis = json.loads(analysis)
                    except: analysis = {}
                
                sub_tags = analysis.get("sub_tags", {}) if isinstance(analysis, dict) else {}

                if p_id and sub_tags:
                    session.execute_write(_add_pitch_node, p_id, sub_tags)
                    loaded += 1
                else:
                    skipped += 1
            
            logger.info(f"Sync Complete: {len(investors)} Investors, {loaded} Pitches ({skipped} skipped).")
            
    except Exception as e:
        logger.error(f"Sync Failed: {e}")
    finally:
        driver.close()

# ==========================================
# 4. MANUAL TESTING
# ==========================================
if __name__ == "__main__":
    # Option 1: Run a sync
    # sync_supabase_to_neo4j()

    # Option 2: Test retrieval
    test_id = "a903b1bb-2eac-4cb3-a647-a428efbde025"
    tags = get_investor_subtags(test_id)
    print(f"Sub-tags for {test_id}: {tags}")