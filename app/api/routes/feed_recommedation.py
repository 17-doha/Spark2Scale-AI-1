"""
app/api/routes/feed_recommedation.py
=====================================
Key change: both /similar-investors and /recommend now run tag-filtered
Qdrant searches via the LangGraph pipeline — no new endpoints.
"""

from fastapi import APIRouter, HTTPException, Request, Query
from app.core.limiter import api_limiter
from app.core.logger import get_logger
from app.graph.feed_recommedation_agent.schema import (
    InvestorEmbeddingRequest,
    InvestorEmbeddingResponse,
    SimilarInvestorsResponse,
    PitchdeckEmbeddingRequest,
    PitchdeckEmbeddingResponse,
    RecommendedPitchdecksResponse,
)
from app.graph.feed_recommedation_agent.tools.pitchdeck_tools import (
    build_and_store_pitchdeck_embedding,
)
from app.graph.feed_recommedation_agent.tools.tag_tools import (
    fetch_investor_tags,
    get_investor_subtags,
    sync_supabase_to_neo4j,
    update_graph_edge_weights
)
from app.graph.feed_recommedation_agent.tools import (
    build_and_store_investor_embedding,
    build_investor_embedding,
)
from app.graph.feed_recommedation_agent.tools.contrastive import (
    build_investor_sub_vectors,
    update_sub_vector_from_interaction,
)
from app.graph.feed_recommedation_agent.workflow import filtered_search_app
from app.core.qdrant_client import get_qdrant
from qdrant_client.models import Filter, FieldCondition, MatchAny
import os

from fastapi import BackgroundTasks
from pydantic import BaseModel, json
from app.graph.feed_recommedation_agent.rewards import REWARD_MATRIX, InteractionType
from app.core.supabase_client import supabase
from neo4j import GraphDatabase
from app.core.config import config

NEO4J_URI = config.NEO4J_URI
NEO4J_USER = config.NEO4J_USERNAME
NEO4J_PASSWORD = config.NEO4J_PASSWORD
router = APIRouter()
logger = get_logger(__name__)
TOP_K  = int(os.getenv("TOP_K", "10"))


class InteractionPayload(BaseModel):
    user_id: str
    pitch_id: str
    liked: bool
    contacted: bool

# ════════════════════════════════════════════════════════════════════════════
#  INVESTOR sync
# ════════════════════════════════════════════════════════════════════════════

@router.post("/investor-embedding", response_model=InvestorEmbeddingResponse)
@api_limiter.limit("30/minute")
async def upsert_investor_embedding(request: Request, payload: InvestorEmbeddingRequest):
    tags = fetch_investor_tags(payload.investor_id)
    if not tags:
        raise HTTPException(status_code=404, detail="Investor not found or has no tags.")
    ok = await build_and_store_investor_embedding(payload.investor_id)
    return InvestorEmbeddingResponse(
        investor_id = payload.investor_id,
        tags        = tags,
        stored      = ok,
        message     = "Stored successfully." if ok else "Failed to store embedding.",
    )


# ════════════════════════════════════════════════════════════════════════════
#  PITCHDECK sync
# ════════════════════════════════════════════════════════════════════════════

@router.post("/pitchdeck-embedding", response_model=PitchdeckEmbeddingResponse)
@api_limiter.limit("30/minute")
async def upsert_pitchdeck_embedding(request: Request, payload: PitchdeckEmbeddingRequest):
    ok = await build_and_store_pitchdeck_embedding(payload.pitchdeck_id)
    return PitchdeckEmbeddingResponse(
        pitchdeck_id = payload.pitchdeck_id,
        stored       = ok,
        message      = "Stored successfully." if ok else "Pitchdeck not found or failed.",
    )


# ════════════════════════════════════════════════════════════════════════════
#  SIMILAR INVESTORS  — tag-filtered
# ════════════════════════════════════════════════════════════════════════════

@router.get("/similar-investors/{investor_id}", response_model=SimilarInvestorsResponse)
@api_limiter.limit("60/minute")
async def get_similar_investors(request: Request, investor_id: str, k: int = TOP_K):
    """
    Top-K investors most similar to the given investor.
    ANN search runs only within investors whose tags overlap with filter_tags.
    """
    vector = await build_investor_embedding(investor_id)
    if vector is None:
        raise HTTPException(status_code=404, detail="Investor has no tags.")

    subtags = get_investor_subtags(investor_id)
    qdrant_filter = (
        Filter(should=[FieldCondition(key="tags", match=MatchAny(any=subtags))])
        if subtags else None
    )

    try:
        res = get_qdrant().query_points(
            collection_name = "investors",
            query           = vector,
            query_filter    = qdrant_filter,
            limit           = k + 1,         # +1 so we can drop self
            with_payload    = True,
        )
        results = [
            {
                "investor_id": h.payload.get("investor_id"),
                "similarity" : round(h.score, 4),
                "tags"       : h.payload.get("tags", []),
            }
            for h in res.points
            if h.payload.get("investor_id") != investor_id
        ][:k]
    except Exception as e:
        logger.error("[similar-investors] Qdrant search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return SimilarInvestorsResponse(investor_id=investor_id, results=results, k=k)

# ════════════════════════════════════════════════════════════════════════════
#  INTERACTIONS - Tags
# ════════════════════════════════════════════════════════════════════════════

@router.post("/interactions")
async def handle_interaction(payload: InteractionPayload, background_tasks: BackgroundTasks):
    if payload.contacted:
        action_type  = InteractionType.CONTACT
        interaction  = "contact"
    elif payload.liked:
        action_type  = InteractionType.LIKE
        interaction  = "like"
    else:
        action_type  = InteractionType.DISLIKE
        interaction  = "dislike"

    config_rl = REWARD_MATRIX.get(action_type)

    # Fetch pitchdeck analysis (tags + subtags)
    try:
        response  = supabase.table("pitchdecks").select("analysis, tags").eq(
            "pitchdeckid", payload.pitch_id
        ).single().execute()

        raw_tags  = response.data.get("tags") or []           # MainTag list
        analysis  = response.data.get("analysis", {})
        if isinstance(analysis, str):
            import json as _json
            analysis = _json.loads(analysis)

        tags_dict  = analysis.get("sub_tags", {}) if isinstance(analysis, dict) else {}
        parent_tags = list(tags_dict.keys())
        sub_tags    = [st for sts in tags_dict.values() for st in sts]

    except Exception as e:
        logger.error("Failed to fetch tags for pitch %s: %s", payload.pitch_id, e)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Task 3 (existing): update Neo4j graph edge weights
    background_tasks.add_task(
        update_graph_edge_weights,
        user_id     = payload.user_id,
        tag_names   = parent_tags,
        subtag_names = sub_tags,
        reward      = config_rl.reward,
        alpha       = config_rl.alpha,
    )

    # Task 4 (new): triplet sub-vector update
    background_tasks.add_task(
        update_sub_vector_from_interaction,
        investor_id    = payload.user_id,
        pitchdeck_id   = payload.pitch_id,
        interaction    = interaction,
        pitchdeck_tags = raw_tags or parent_tags,
    )

    return {
        "status"  : "success",
        "message" : (
            f"Registered {action_type.value}. "
            f"Neo4j + sub-vector update running in background for tags: {', '.join(parent_tags)}."
        ),
    }

@router.post("/sub-vectors/build/{investor_id}")
@api_limiter.limit("10/minute")
async def build_sub_vectors(request: Request, investor_id: str):
    """
    Build or rebuild per-MainTag sub-vectors for one investor.
    Call this once after onboarding, then let the /interactions endpoint
    keep vectors current via triplet updates.
    """
    results = await build_investor_sub_vectors(investor_id)
    ok      = sum(v for v in results.values())
    return {
        "investor_id": investor_id,
        "total"      : len(results),
        "stored"     : ok,
        "failed"     : len(results) - ok,
        "detail"     : results,
    }
@router.post("/admin/sync-neo4j")
async def trigger_manual_neo4j_sync(background_tasks: BackgroundTasks):
    """
    Manually triggers a full two-way sync between Supabase and Neo4j.
    This will add missing records and delete records in Neo4j that 
    were removed from Supabase.
    """
   

    background_tasks.add_task(sync_supabase_to_neo4j)
    
    return {
        "status": "success",
        "message": "Full Supabase -> Neo4j sync started in the background. Check your logs for completion."
    }

@router.get("/admin/verify-sync")
async def verify_full_sync():
    """
    Audits the sync status between Supabase and Neo4j for BOTH tags and sub-tags.
    Returns a detailed list of any pitch decks that have mismatched data.
    """
    logger.info("[Audit] Starting Full Supabase vs Neo4j Sync Verification...")

    # 1. Fetch Supabase Data
    supa_resp = supabase.table("pitchdecks").select("pitchdeckid, tags, extracted_subtags").execute()
    
    supa_data = {}
    for row in (supa_resp.data or []):
        p_id = row.get("pitchdeckid")
        main_tags = row.get("tags") or []
        sub_tags = row.get("extracted_subtags") or []
        
        if p_id:
            supa_data[p_id] = {
                "tags": set(main_tags),
                "subtags": set(sub_tags)
            }

    # 2. Fetch Neo4j Data
    # Using DISTINCT in collect() prevents duplicates from the Cartesian product of the two OPTIONAL MATCHes
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
                    "subtags": set(n_subtags)
                }
    except Exception as e:
        logger.error(f"[Audit] Neo4j fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to connect to Neo4j.")
    finally:
        driver.close()

    # 3. Compare the Data
    discrepancies = []
    all_pitch_ids = set(supa_data.keys()).union(set(neo4j_data.keys()))

    for pid in all_pitch_ids:
        # Default to empty sets if a pitchdeck exists in one DB but not the other
        s_record = supa_data.get(pid, {"tags": set(), "subtags": set()})
        n_record = neo4j_data.get(pid, {"tags": set(), "subtags": set()})

        tags_match = s_record["tags"] == n_record["tags"]
        subtags_match = s_record["subtags"] == n_record["subtags"]

        if not tags_match or not subtags_match:
            issue = {"pitchdeck_id": pid}
            
            if not tags_match:
                issue["tags_issue"] = {
                    "in_supabase_only": list(s_record["tags"] - n_record["tags"]),
                    "in_neo4j_only": list(n_record["tags"] - s_record["tags"])
                }
                
            if not subtags_match:
                issue["subtags_issue"] = {
                    "in_supabase_only": list(s_record["subtags"] - n_record["subtags"]),
                    "in_neo4j_only": list(n_record["subtags"] - s_record["subtags"])
                }
                
            discrepancies.append(issue)

    # 4. Return Results
    if not discrepancies:
        return {
            "status": "perfect",
            "message": f"All {len(all_pitch_ids)} pitch decks have perfectly synced Tags AND SubTags!"
        }

    return {
        "status": "mismatch_found",
        "total_checked": len(all_pitch_ids),
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies
    }

@router.get("/investors/{user_id}/subtags")
async def fetch_investor_subtags(
    user_id: str,
    hate_threshold: float = Query(default=0.01),
    limit: int = Query(default=50, ge=1, le=200),
):
    subtags = get_investor_subtags(
        user_id=user_id,
        hate_threshold=hate_threshold,
        limit=limit,
    )
    return {
        "status": "success",
        "user_id": user_id,
        "hate_threshold_applied": hate_threshold,
        "limit": limit,
        "subtag_count": len(subtags),
        "subtags": subtags,
    }

# ════════════════════════════════════════════════════════════════════════════
#  RECOMMEND  — full filtered LangGraph pipeline
# ════════════════════════════════════════════════════════════════════════════

@router.get("/recommend/{investor_id}", response_model=RecommendedPitchdecksResponse)
@api_limiter.limit("60/minute")
async def recommend_pitchdecks(request: Request, investor_id: str, k: int = TOP_K):
    """
    Top-K pitchdeck recommendations for a given investor.

    Runs the full LangGraph:
      1. generate_filter_tags   — tag pre-filter list (mock → swap later)
      2. build_investor_vector  — investor's aggregated embedding
      3. filtered_vector_search — Qdrant ANN within the filtered subset only
      4. rerank_candidates      — Jina cross-encoder re-scores → top-K
      5. format_output          — final shaping
    """
    result = await filtered_search_app.ainvoke({
        "investor_id"    : investor_id,
        "filter_tags"    : [],
        "investor_vector": None,
        "candidates"     : [],
        "final_results"  : [],
        "errors"         : [],
    })

    final_results = result.get("final_results", [])
    errors        = result.get("errors", [])

    if not final_results and errors:
        raise HTTPException(status_code=404, detail=errors[0])

    return RecommendedPitchdecksResponse(
        investor_id = investor_id,
        results     = final_results[:k],
        k           = k,
    )


# ════════════════════════════════════════════════════════════════════════════
#  SUPABASE WEBHOOKS
# ════════════════════════════════════════════════════════════════════════════

@router.post("/webhook/investor")
async def webhook_investor(request: Request):
    body        = await request.json()
    event_type  = body.get("type", "")
    investor_id = body.get("record", {}).get("user_id")

    if not investor_id:
        return {"status": "skipped", "reason": "No user_id in record."}
    if event_type not in ("INSERT", "UPDATE"):
        return {"status": "skipped", "reason": f"Event '{event_type}' not handled."}

    ok = await build_and_store_investor_embedding(investor_id)
    return {"status": "synced" if ok else "failed", "investor_id": investor_id, "event": event_type}


@router.post("/webhook/pitchdeck")
async def webhook_pitchdeck(request: Request):
    body         = await request.json()
    event_type   = body.get("type", "")
    pitchdeck_id = body.get("record", {}).get("pitchdeckid")

    if not pitchdeck_id:
        return {"status": "skipped", "reason": "No pitchdeckid in record."}
    if event_type not in ("INSERT", "UPDATE"):
        return {"status": "skipped", "reason": f"Event '{event_type}' not handled."}

    ok = await build_and_store_pitchdeck_embedding(pitchdeck_id)
    return {"status": "synced" if ok else "failed", "pitchdeck_id": pitchdeck_id, "event": event_type}