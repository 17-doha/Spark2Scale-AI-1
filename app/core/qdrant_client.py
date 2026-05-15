"""
app/core/qdrant_client.py
=========================
Qdrant singleton client + one-time collection initializer.

Collections created:
  • tags        — one point per unique tag string (shared by investors & pitchdecks)
  • investors   — one point per investor (aggregated tag embeddings)
  • pitchdecks  — one point per pitchdeck (aggregated tag embeddings)

All vectors: 768-dim, Cosine distance (jina-embeddings-v2-base-en).
"""

import os
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    PayloadSchemaType,
)
from app.core.logger import get_logger
# from app.core.metrics import qdrant_query_duration, qdrant_upsert_duration
import time

logger = get_logger(__name__)

QDRANT_URL     = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

EMBEDDING_DIM        = 1024
VDB_SEARCH_ALGORITHM = os.getenv("VDB_SEARCH_ALGORITHM", "COSINE").upper()
COLLECTIONS          = ["tags", "investors", "pitchdecks"]

_qdrant: QdrantClient | None = None

def get_qdrant_with_metrics():
    client = get_qdrant()
    
    original_query = client.query_points
    original_upsert = client.upsert

    def timed_query(collection_name, **kwargs):
        start = time.time()
        try:
            return original_query(collection_name=collection_name, **kwargs)
        finally:
            qdrant_query_duration.labels(
                collection=collection_name
            ).observe(time.time() - start)

    def timed_upsert(collection_name, **kwargs):
        start = time.time()
        try:
            return original_upsert(collection_name=collection_name, **kwargs)
        finally:
            qdrant_upsert_duration.labels(
                collection=collection_name
            ).observe(time.time() - start)

    client.query_points = timed_query
    client.upsert = timed_upsert
    return client

def get_qdrant() -> QdrantClient:
    """Return the shared QdrantClient, creating it on first call."""
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30)
        logger.info("[Qdrant] Client initialised → %s", QDRANT_URL)
    return _qdrant

# ── Collection initializer ───────────────────────────────────────────────────

def init_qdrant_collections() -> None:
    """
    Idempotent — creates each collection only if it does not already exist.
    Call once at application startup.
    """
    client = get_qdrant()
    existing = {c.name for c in client.get_collections().collections}

    if VDB_SEARCH_ALGORITHM == "DOT":
        distance_metric = Distance.DOT
    elif VDB_SEARCH_ALGORITHM == "EUCLID":
        distance_metric = Distance.EUCLID
    else:
        distance_metric = Distance.COSINE

    for name in COLLECTIONS:
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=distance_metric),
            )
            logger.info("[Qdrant] Created collection '%s' (%d-dim, %s).", name, EMBEDDING_DIM, VDB_SEARCH_ALGORITHM)
        else:
            logger.info("[Qdrant] Collection '%s' already exists.", name)

        # Ensure 'tags' payload index exists for investors and pitchdecks
        if name in ["investors", "pitchdecks"]:
            client.create_payload_index(
                collection_name=name,
                field_name="tags",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info("[Qdrant] Ensured 'keyword' index for 'tags' in '%s'.", name)