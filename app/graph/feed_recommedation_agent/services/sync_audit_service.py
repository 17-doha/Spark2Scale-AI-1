"""
Sync Audit Service
==================
Compares data between Supabase and Neo4j to detect discrepancies.

Extracted from the ``/admin/verify-sync`` route handler to follow the
Single Responsibility Principle. This is pure comparison logic — no HTTP
concerns, easily testable in isolation.
"""

from neo4j import GraphDatabase

from app.core.config import config
from app.core.supabase_client import supabase
from app.core.logger import get_logger

logger = get_logger(__name__)

NEO4J_URI      = config.NEO4J_URI
NEO4J_USER     = config.NEO4J_USERNAME
NEO4J_PASSWORD = config.NEO4J_PASSWORD


class SyncAuditService:
    """
    Audits the synchronisation state between Supabase and Neo4j for
    both tags and sub-tags across all pitch decks.
    """

    @staticmethod
    def _fetch_supabase_data() -> dict[str, dict]:
        """Fetch all pitchdeck tag data from Supabase."""
        supa_resp = supabase.table("pitchdecks").select(
            "pitchdeckid, tags, extracted_subtags"
        ).execute()

        supa_data = {}
        for row in (supa_resp.data or []):
            p_id = row.get("pitchdeckid")
            main_tags = row.get("tags") or []
            sub_tags = row.get("extracted_subtags") or []

            if p_id:
                supa_data[p_id] = {
                    "tags": set(main_tags),
                    "subtags": set(sub_tags),
                }
        return supa_data

    @staticmethod
    def _fetch_neo4j_data() -> dict[str, dict]:
        """Fetch all pitchdeck tag data from Neo4j."""
        neo4j_query = """
        MATCH (p:PitchDeck)
        OPTIONAL MATCH (p)-[:TAGGED_WITH]->(t:Tag)
        OPTIONAL MATCH (p)-[:HAS_SUBTAG]->(st:SubTag)
        RETURN p.pitchId AS pitch_id,
               collect(DISTINCT t.name) AS tags,
               collect(DISTINCT st.name) AS sub_tags
        """
        neo4j_data = {}

        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        try:
            with driver.session() as session:
                result = session.run(neo4j_query)
                for record in result:
                    p_id = record["pitch_id"]
                    n_tags = [t for t in record["tags"] if t is not None]
                    n_subtags = [st for st in record["sub_tags"] if st is not None]

                    neo4j_data[p_id] = {
                        "tags": set(n_tags),
                        "subtags": set(n_subtags),
                    }
        except Exception as e:
            logger.error(f"[Audit] Neo4j fetch failed: {e}")
            raise RuntimeError("Failed to connect to Neo4j.") from e
        finally:
            driver.close()

        return neo4j_data

    @staticmethod
    def _compare_data(
        supa_data: dict[str, dict],
        neo4j_data: dict[str, dict],
    ) -> list[dict]:
        """Compare Supabase and Neo4j data, returning list of discrepancies."""
        discrepancies = []
        all_pitch_ids = set(supa_data.keys()).union(set(neo4j_data.keys()))

        for pid in all_pitch_ids:
            s_record = supa_data.get(pid, {"tags": set(), "subtags": set()})
            n_record = neo4j_data.get(pid, {"tags": set(), "subtags": set()})

            tags_match = s_record["tags"] == n_record["tags"]
            subtags_match = s_record["subtags"] == n_record["subtags"]

            if not tags_match or not subtags_match:
                issue = {"pitchdeck_id": pid}

                if not tags_match:
                    issue["tags_issue"] = {
                        "in_supabase_only": list(s_record["tags"] - n_record["tags"]),
                        "in_neo4j_only": list(n_record["tags"] - s_record["tags"]),
                    }

                if not subtags_match:
                    issue["subtags_issue"] = {
                        "in_supabase_only": list(s_record["subtags"] - n_record["subtags"]),
                        "in_neo4j_only": list(n_record["subtags"] - s_record["subtags"]),
                    }

                discrepancies.append(issue)

        return discrepancies

    @classmethod
    def verify(cls) -> dict:
        """
        Run a full audit comparing Supabase and Neo4j tag data.

        Returns:
            Dict with 'status', 'message'/'total_checked'/'discrepancies'.

        Raises:
            RuntimeError: If Neo4j connection fails.
        """
        logger.info("[Audit] Starting Full Supabase vs Neo4j Sync Verification...")

        supa_data  = cls._fetch_supabase_data()
        neo4j_data = cls._fetch_neo4j_data()

        discrepancies  = cls._compare_data(supa_data, neo4j_data)
        all_pitch_ids  = set(supa_data.keys()).union(set(neo4j_data.keys()))

        if not discrepancies:
            return {
                "status": "perfect",
                "message": f"All {len(all_pitch_ids)} pitch decks have perfectly synced Tags AND SubTags!",
            }

        return {
            "status": "mismatch_found",
            "total_checked": len(all_pitch_ids),
            "discrepancy_count": len(discrepancies),
            "discrepancies": discrepancies,
        }
