"""
Neo4j Read / Update Queries
============================
Functions that read or update Neo4j graph data:
  - ``get_investor_subtags``  — UCB-scored subtag retrieval with time decay
  - ``get_sibling_subtags``   — hierarchical fallback sibling lookup
  - ``update_graph_edge_weights`` — RL reward-based edge weight updates

Single Responsibility: Neo4j read/update-path queries only.
"""

import math
import os
from typing import Optional

from neo4j import GraphDatabase

from app.core.config import config
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.tools.decay import (
    _apply_decay,
    DECAY_LAMBDA,
)

logger = get_logger(__name__)

# Neo4j connection details
NEO4J_URI      = config.NEO4J_URI
NEO4J_USER     = config.NEO4J_USERNAME
NEO4J_PASSWORD = config.NEO4J_PASSWORD

# UCB hyperparameters
UCB_C              = float(os.getenv("UCB_C", "1.414"))
UCB_EXPLOIT_RATIO  = float(os.getenv("UCB_EXPLOIT_RATIO", "0.8"))


def get_investor_subtags(
    user_id: str,
    hate_threshold: float = 0.01,
    limit: int = 50,
) -> list[str]:
    """
    Retrieve an investor's subtags from Neo4j, scored with time-decayed
    UCB (Upper Confidence Bound) for exploration/exploitation balance.

    Returns a list of subtag names: top 80% by decayed weight (exploit),
    bottom 20% by UCB score (explore).
    """
    if not NEO4J_URI:
        return []

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # Returns last_updated so Python can apply decay
    query = """
    MATCH (i:Investor {userId: $userId})-[rs:INTERESTED_IN_SUB]->(st:SubTag)
          <-[:CONTAINS]-(t:Tag)<-[rt:INTERESTED_IN]-(i)
    WHERE coalesce(rt.weight, 0.5) >= $threshold
    RETURN
        st.name                          AS SubTag,
        coalesce(rs.weight, 0.5)         AS weight,
        coalesce(rs.impressions, 0)      AS impressions,
        rs.last_updated                  AS last_updated
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

    # Apply time decay to raw weight before any scoring
    for r in rows:
        r["decayed_weight"] = _apply_decay(r["weight"], r["last_updated"])

    # UCB scoring (on decayed weight)
    N = sum(r["impressions"] for r in rows)

    for r in rows:
        n_i = r["impressions"]
        w_d = r["decayed_weight"]
        if n_i == 0 or N == 0:
            r["ucb"] = float("inf")
        else:
            r["ucb"] = w_d + UCB_C * math.sqrt(math.log(N) / n_i)

    # 80/20 exploit/explore split
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


def update_graph_edge_weights(
    user_id: str,
    tag_names: list[str],
    subtag_names: list[str],
    reward: float,
    alpha: float,
):
    """
    Apply RL reward-based weight updates to investor→Tag and investor→SubTag
    edges in Neo4j. Normalises weights after update and resets the decay clock.
    """
    if not NEO4J_URI:
        return
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    query = """
    // ── PHASE 1: MACRO TAGS ───────────────────────────────────────────────────
    MATCH (i:Investor {userId: $userId})-[rt:INTERESTED_IN]->(t:Tag)
    WHERE t.name IN $tagNames
    SET
        rt.impressions  = coalesce(rt.impressions, 0) + 1,
        rt.last_updated = datetime()
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
        rs.last_updated = datetime()
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
