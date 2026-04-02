from fastapi import APIRouter, Request
from app.core.limiter import api_limiter
from app.core.qdrant_client import get_qdrant, init_qdrant_collections, COLLECTIONS
from app.graph.feed_recommedation_agent.tools import build_and_store_all
from app.graph.feed_recommedation_agent.tools.pitchdeck_tools import build_and_store_all_pitchdecks

router = APIRouter()

@router.get("/health")
def vdb_health_status():
    """Check Vector Database health and status of collections."""
    client = get_qdrant()
    try:
        existing = {c.name for c in client.get_collections().collections}
        return {
            "status": "online",
            "required_collections": COLLECTIONS,
            "existing_collections": list(existing),
            "missing_collections": list(set(COLLECTIONS) - existing)
        }
    except Exception as e:
        return {"status": "offline", "error": str(e)}

@router.delete("/collections")
def delete_all_collections():
    """Danger: Delete all Vector Database collections."""
    client = get_qdrant()
    for name in COLLECTIONS:
        client.delete_collection(collection_name=name)
    return {"message": "All collections deleted.", "collections": COLLECTIONS}

@router.post("/collections/init")
def initialize_collections():
    """Initialize missing collections using the configured schema."""
    init_qdrant_collections()
    return {"message": "Collections initialized successfully."}

@router.post("/investor-embedding/batch")
@api_limiter.limit("5/minute")
async def upsert_all_investor_embeddings(request: Request):
    """Batch-sync all investors from Supabase → Qdrant [investors]."""
    results = await build_and_store_all()
    success = sum(1 for v in results.values() if v)
    return {"total": len(results), "success": success, "failed": len(results) - success}

@router.post("/pitchdeck-embedding/batch")
@api_limiter.limit("5/minute")
async def upsert_all_pitchdeck_embeddings(request: Request):
    """Batch-sync all pitchdecks from Supabase → Qdrant [pitchdecks]."""
    results = await build_and_store_all_pitchdecks()
    success = sum(1 for v in results.values() if v)
    return {"total": len(results), "success": success, "failed": len(results) - success}
