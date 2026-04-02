"""
Jina Embedding Module
=====================
Converts text → embedding vectors using the Jina AI embeddings API.
Model is configured via EMBEDDING_MODEL env var (default: jina-embeddings-v2-base-en).
Embedding dimension: 768 (jina-embeddings-v2-base-en).
"""

import os
import aiohttp
import numpy as np
from typing import Optional
from app.core.logger import get_logger

logger = get_logger(__name__)

JINA_API_KEY   = os.getenv("JINA_API_KEY", "")
JINA_MODEL     = os.getenv("EMBEDDING_MODEL", "jina-embeddings-v2-base-en")
JINA_API_URL   = "https://api.jina.ai/v1/embeddings"
EMBEDDING_DIM  = 768  # fixed for jina-embeddings-v2-base-en


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of texts in a single Jina API call.

    Args:
        texts: List of strings to embed.

    Returns:
        List of float vectors, one per input text.

    Raises:
        ValueError: If the API key is missing.
        RuntimeError: On non-200 API response.
    """
    if not JINA_API_KEY:
        raise ValueError("JINA_API_KEY is not set in environment variables.")
    if not texts:
        return []

    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": JINA_MODEL, "input": texts}

    async with aiohttp.ClientSession() as session:
        async with session.post(JINA_API_URL, json=payload, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Jina API error {resp.status}: {body}")
            data = await resp.json()

    # data["data"] is sorted by index
    embeddings = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
    logger.info(f"[Jina] Embedded {len(embeddings)} texts with model '{JINA_MODEL}'.")
    return embeddings


async def embed_text(text: str) -> list[float]:
    """Convenience wrapper: embed a single string."""
    results = await embed_texts([text])
    return results[0]


def aggregate_embeddings(embeddings: list[list[float]], strategy: str = "mean") -> list[float]:
    """
    Aggregate multiple embeddings into one representative vector.

    Args:
        embeddings: List of float vectors (all same dimension).
        strategy:   'mean' (default) or 'sum'.

    Returns:
        Single float vector of the same dimension.
    """
    if not embeddings:
        return [0.0] * EMBEDDING_DIM

    matrix = np.array(embeddings, dtype=np.float32)
    if strategy == "sum":
        vec = matrix.sum(axis=0)
    else:
        vec = matrix.mean(axis=0)

    # L2-normalise so cosine similarity == dot product
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec.tolist()