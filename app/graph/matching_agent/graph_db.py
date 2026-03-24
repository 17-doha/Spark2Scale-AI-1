from neo4j import GraphDatabase

class RecommendationGraph:
    def __init__(self, uri, user, password):
        # Establish the connection to your AuraDB cluster
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        # Always good practice to close the connection when done
        self.driver.close()

    # --- WRITING DATA TO NEO4J ---

    def add_pitch_tags(self, pitch_id, tags_dict):
        """
        Takes the tags and sub-tags from a pitch and adds them to the graph.
        tags_dict format: {"Consumer & Commerce": ["Marketplace"], "Specialized Industry Tech": ["Proptech"]}
        """
        def _create_tags(tx, parent_tag, sub_tags):
            query = """
            MERGE (t:Tag {name: $parent_tag})
            WITH t
            UNWIND $sub_tags AS sub_tag_name
            MERGE (st:SubTag {name: sub_tag_name})
            MERGE (t)-[:CONTAINS]->(st)
            """
            tx.run(query, parent_tag=parent_tag, sub_tags=sub_tags)

        with self.driver.session() as session:
            for parent, subs in tags_dict.items():
                session.execute_write(_create_tags, parent, subs)
        print(f"Tags added for pitch {pitch_id}")

    def add_investor(self, user_id, initial_tags):
        """
        Adds a new investor and links them to their initial tags with a weight of 1.0.
        """
        def _create_investor(tx, uid, tags):
            query = """
            MERGE (i:Investor {userId: $uid})
            WITH i
            UNWIND $tags AS tag_name
            MERGE (t:Tag {name: tag_name})
            MERGE (i)-[r:INTERESTED_IN]->(t)
            ON CREATE SET r.weight = 1.0
            """
            tx.run(query, uid=uid, tags=tags)

        with self.driver.session() as session:
            session.execute_write(_create_investor, user_id, initial_tags)
        print(f"Investor {user_id} added to graph.")

    # --- READING DATA FROM NEO4J ---

    def get_investor_subtags(self, user_id):
        """
        This is how the final sub-tags are passed back to your Python code!
        Returns a list of dictionaries with the sub-tag and its current weight.
        """
        def _fetch_subtags(tx, uid):
            query = """
            MATCH (i:Investor {userId: $uid})-[r:INTERESTED_IN]->(t:Tag)-[:CONTAINS]->(st:SubTag)
            RETURN st.name AS SubTag, t.name AS ParentTag, r.weight AS Weight
            ORDER BY r.weight DESC
            """
            result = tx.run(query, uid=uid)
            # Format the Neo4j result into a standard Python list of dictionaries
            return [{"sub_tag": record["SubTag"], "parent_tag": record["ParentTag"], "weight": record["Weight"]} for record in result]

        with self.driver.session() as session:
            sub_tags_list = session.execute_read(_fetch_subtags, user_id)
            return sub_tags_list