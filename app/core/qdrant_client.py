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

logger = get_logger(__name__)

# ── Credentials (set in .env) ────────────────────────────────────────────────
QDRANT_URL     = os.getenv(
    "QDRANT_URL",
    "https://1ac0a374-33ed-48a6-bffd-602069b65316.us-east4-0.gcp.cloud.qdrant.io",
)
QDRANT_API_KEY = os.getenv(
    "QDRANT_API_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6ODVhYjgzOWYtZmEwYS00MDFkLTkxOGEtZDBjNmMyZjBkZWE3In0"
    ".S9sOqICOGAfq9rjeRSyF9mD_peaKIrX48PHE-4nBh7o",
)

EMBEDDING_DIM        = 1024         # fixed for jina-embeddings-v3
VDB_SEARCH_ALGORITHM = os.getenv("VDB_SEARCH_ALGORITHM", "COSINE").upper()
COLLECTIONS          = ["tags", "investors", "pitchdecks"]

# ── Singleton ────────────────────────────────────────────────────────────────
_qdrant: QdrantClient | None = None

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