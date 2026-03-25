import os
import json  # <-- Added this to handle stringified data!
from supabase import create_client, Client
from neo4j import GraphDatabase

# ==========================================
# 1. CREDENTIALS (UPDATE THESE)
# ==========================================
# Supabase
SUPABASE_URL="https://xdkxbibtoggcjvgtktaf.supabase.co"
SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhka3hiaWJ0b2dnY2p2Z3RrdGFmIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NDA3OTY0MywiZXhwIjoyMDc5NjU1NjQzfQ.Cy90Npb42y4xaLkzg5Tjz1z2Qc6XwRxPPos-NAxZqHA"


# Neo4j
NEO4J_URI = "neo4j+s://ae2b5466.databases.neo4j.io"
NEO4J_USER = "ae2b5466"
NEO4J_PASSWORD = "6heq_R40e5nOPkVpsGlOMu-Nfz-h6LY_ZZLjQhAj6wk"

# ==========================================
# 2. NEO4J FUNCTIONS 
# ==========================================
def add_investor(tx, user_id, tags):
    if not tags: return # Skip if no tags
    
    query = """
    MERGE (i:Investor {userId: $user_id})
    WITH i
    UNWIND $tags AS tag_name
    MERGE (t:Tag {name: tag_name})
    MERGE (i)-[r:INTERESTED_IN]->(t)
    ON CREATE SET r.weight = 1.0
    """
    tx.run(query, user_id=user_id, tags=tags)

def add_pitch(tx, pitch_id, sub_tags_dict):
    if not sub_tags_dict: return # Skip if no analysis/subtags
    
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

# ==========================================
# 3. THE SYNC LOGIC
# ==========================================
if __name__ == "__main__":
    print("🔄 Starting Supabase to Neo4j Sync...")
    
    # Initialize clients
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        with driver.session() as session:
            # --- SYNC INVESTORS ---
            print("Fetching investors from Supabase...")
            investors_response = supabase.table("investors").select("*").execute()
            real_investors = investors_response.data
            
            for inv in real_investors:
                user_id = inv.get("user_id")
                tags = inv.get("tags", [])
                if user_id:
                    session.execute_write(add_investor, user_id, tags)
            print(f"✅ Successfully loaded {len(real_investors)} real investors into Neo4j.")
            
            # --- SYNC PITCH DECKS ---
            print("\nFetching pitch decks from Supabase...")
            pitches_response = supabase.table("pitchdecks").select("*").execute()
            real_pitches = pitches_response.data
            print("\nRAW DATA KEYS:", real_pitches[0].keys())
            
            loaded_count = 0
            skipped_count = 0
            error_count = 0
            
            for pitch in real_pitches:
                pitch_id = pitch.get("pitchdeckid")
                analysis = pitch.get("analysis")
                
                # 1. Fix Stringified JSON if Supabase returned it as text
                if isinstance(analysis, str):
                    try:
                        analysis = json.loads(analysis)
                    except json.JSONDecodeError:
                        analysis = {}
                
                # 2. Safely extract sub_tags
                sub_tags = {}
                if isinstance(analysis, dict):
                    sub_tags = analysis.get("sub_tags", {})
                
                # 3. Execute or report why it failed
                if pitch_id and sub_tags:
                    try:
                        session.execute_write(add_pitch, pitch_id, sub_tags)
                        loaded_count += 1
                    except Exception as e:
                        print(f"❌ Cypher error on pitch {pitch_id}: {e}")
                        error_count += 1
                else:
                    # Print the exact data it rejected so we can inspect it
                    print(f"⚠️ Skipped pitch {pitch_id} | Analysis Data: {analysis}")
                    skipped_count += 1
                    
            print(f"\n✅ Successfully loaded: {loaded_count}")
            print(f"⚠️ Skipped (No valid sub-tags): {skipped_count}")
            print(f"❌ Errors (Failed to insert): {error_count}")
            
        print("\n🎉 Sync complete! Your graph is now populated with live data.")
        
    except Exception as e:
        print(f"❌ Error during sync: {e}")
    finally:
        driver.close()