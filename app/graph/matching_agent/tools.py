from neo4j import GraphDatabase
# from app.core.config import config
# 1. Connection Details
# URI = config.NEO4J_URI
# USER = config.NEO4J_USERNAME
# PASSWORD = config.NEO4J_PASSWORD

URI = "neo4j+s://ae2b5466.databases.neo4j.io"
USER = "ae2b5466"
PASSWORD ="6heq_R40e5nOPkVpsGlOMu-Nfz-h6LY_ZZLjQhAj6wk"
def get_investor_subtags(user_id):
    """
    Fetches recommended sub-tags for a specific investor based on their weighted tags.
    """
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    
    # The Cypher query: 
    # Finds the investor -> follows their INTERESTED_IN edges to Tags 
    # -> follows CONTAINS edges to get the final SubTags.
    query = """
    MATCH (i:Investor {userId: $userId})-[r:INTERESTED_IN]->(t:Tag)-[:CONTAINS]->(st:SubTag)
    RETURN st.name AS SubTag, t.name AS ParentTag, r.weight AS Weight
    ORDER BY r.weight DESC
    """
    
    try:
        with driver.session() as session:
            result = session.run(query, userId=user_id)
            
            # Format the output into a clean list of dictionaries for your agent
            recommendations = [
                {
                    "sub_tag": record["SubTag"],
                    "parent_tag": record["ParentTag"],
                    "weight": record["Weight"]
                }
                for record in result
            ]
            
            return recommendations
            
    except Exception as e:
        print(f"Error fetching recommendations: {e}")
        return []
        
    finally:
        driver.close()

# --- How to use it in your code ---
if __name__ == "__main__":
    # Test it with one of your investor UUIDs
    target_investor = "a903b1bb-2eac-4cb3-a647-a428efbde025" 
    
    my_recommended_subtags = get_investor_subtags(target_investor)
    
    print(f"Recommendations for {target_investor}:")
    for item in my_recommended_subtags:
        print(item)