import pytest
import math
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

# Import the functions to test
from app.graph.feed_recommedation_agent.tools.tag_tools import (
    _days_since_updated,
    _apply_decay,
    get_investor_subtags,
    DECAY_DEFAULT_AGE_DAYS,
    MIN_DECAYED_WEIGHT
)
from app.graph.feed_recommedation_agent.node import sibling_fallback_node
from app.graph.feed_recommedation_agent.tools.contrastive import (
    triplet_update,
    _l2_normalize
)

@patch("app.graph.feed_recommedation_agent.tools.tag_tools.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.tag_tools.NEO4J_URI", "mock_uri")
def test_get_investor_subtags_ucb_split(mock_driver):
    """
    Test that the top 80% are prioritized by decayed_weight (exploitation)
    and the remaining 20% are prioritized by UCB score (exploration).
    """
    mock_session = MagicMock()
    mock_driver.return_value.session.return_value.__enter__.return_value = mock_session

    now = datetime.now(timezone.utc)
    mock_rows = [
        # Exploitation candidates (high weight, high impressions)
        {"SubTag": "Tag_Exp1", "weight": 0.9, "impressions": 100, "last_updated": now},
        {"SubTag": "Tag_Exp2", "weight": 0.85, "impressions": 80, "last_updated": now},
        {"SubTag": "Tag_Exp3", "weight": 0.8, "impressions": 90, "last_updated": now},
        {"SubTag": "Tag_Exp4", "weight": 0.75, "impressions": 70, "last_updated": now},
        {"SubTag": "Tag_Exp5", "weight": 0.7, "impressions": 60, "last_updated": now},
        
        # Exploration candidates (low weight, 0 impressions -> Infinite UCB)
        {"SubTag": "Tag_Expl1", "weight": 0.1, "impressions": 0, "last_updated": now},
        {"SubTag": "Tag_Expl2", "weight": 0.15, "impressions": 0, "last_updated": now},
        {"SubTag": "Tag_Expl3", "weight": 0.2, "impressions": 0, "last_updated": now},
        {"SubTag": "Tag_Expl4", "weight": 0.25, "impressions": 0, "last_updated": now},
        {"SubTag": "Tag_Expl5", "weight": 0.3, "impressions": 0, "last_updated": now},
    ]
    
    mock_session.run.return_value = mock_rows

    limit = 10
    result = get_investor_subtags("user1", limit=limit)
    
    assert len(result) == 10
    assert "Tag_Expl1" in result[-2:] or "Tag_Expl2" in result[-2:]

@pytest.mark.asyncio
@patch("app.graph.feed_recommedation_agent.node.get_qdrant")
@patch("app.graph.feed_recommedation_agent.node.get_sibling_subtags")
async def test_sibling_fallback_node(mock_get_siblings, mock_get_qdrant):
    """
    Test that if candidates < TOP_K, sibling tags are fetched and searched.
    """
    state = {
        "candidates": [
            {"pitchdeck_id": "p1", "tags": ["A"], "vector_score": 0.9},
            {"pitchdeck_id": "p2", "tags": ["A"], "vector_score": 0.85}
        ], 
        "filter_tags": ["A"],
        "investor_vector": [0.1, 0.2, 0.3]
    }
    
    mock_get_siblings.return_value = ["Sibling_B", "Sibling_C"]
    
    mock_qdrant_client = MagicMock()
    mock_point1 = MagicMock()
    mock_point1.payload = {"pitchdeck_id": "p3", "startup_id": "s3", "tags": ["Sibling_B"]}
    mock_point1.score = 0.8
    
    mock_point2 = MagicMock()
    mock_point2.payload = {"pitchdeck_id": "p1", "startup_id": "s1", "tags": ["Sibling_B"]}
    mock_point2.score = 0.7
    
    mock_qdrant_client.query_points.return_value.points = [mock_point1, mock_point2]
    mock_get_qdrant.return_value = mock_qdrant_client
    
    with patch("app.graph.feed_recommedation_agent.node.TOP_K", 10):
        result = await sibling_fallback_node(state)
        
    assert result["fallback_triggered"] is True
    assert result["sibling_tags"] == ["Sibling_B", "Sibling_C"]
    assert len(result["candidates"]) == 3
    assert result["candidates"][2]["pitchdeck_id"] == "p3"
    assert result["candidates"][2]["from_fallback"] is True

def test_time_decay_math():
    """
    Test the exponential time decay on weights.
    """
    now = datetime.now(timezone.utc)
    base_weight = 1.0
    
    fresh_weight = _apply_decay(base_weight, now)
    assert fresh_weight == base_weight
    
    old_30_days = now - timedelta(days=30)
    decayed_weight = _apply_decay(base_weight, old_30_days)
    assert math.isclose(decayed_weight, 0.5, rel_tol=1e-3)
    
    none_weight = _apply_decay(base_weight, None)
    assert MIN_DECAYED_WEIGHT < none_weight < base_weight

@patch("app.graph.feed_recommedation_agent.tools.contrastive.get_qdrant")
def test_triplet_update(mock_get_qdrant):
    """
    Verify the math and logic of the triplet margin update.
    E_new = E_old + alpha * (E_pos - E_old) - gamma * (E_neg - E_old)
    """
    mock_client = MagicMock()
    mock_get_qdrant.return_value = mock_client
    
    e_old = [0.1, 0.2, 0.3]
    mock_retrieved_point = MagicMock()
    mock_retrieved_point.vector = e_old
    mock_retrieved_point.payload = {"impressions": 5, "investor_id": "user1", "tag_name": "Tech"}
    mock_client.retrieve.return_value = [mock_retrieved_point]
    
    e_pos = [0.2, 0.3, 0.4]
    e_neg = [-0.1, -0.2, -0.3]
    alpha = 0.1
    gamma = 0.05
    
    e_old_np = np.array(e_old, dtype=np.float32)
    e_pos_np = np.array(e_pos, dtype=np.float32)
    e_neg_np = np.array(e_neg, dtype=np.float32)
    
    delta = alpha * (e_pos_np - e_old_np) - gamma * (e_neg_np - e_old_np)
    raw_new = e_old_np + delta
    norm = np.linalg.norm(raw_new)
    expected_new = (raw_new / norm).tolist()
    
    result = triplet_update("user1", "Tech", e_pos=e_pos, e_neg=e_neg, alpha=alpha, gamma=gamma)
    
    assert result is True
    mock_client.upsert.assert_called_once()
    called_points = mock_client.upsert.call_args[1]["points"]
    assert len(called_points) == 1
    assert np.allclose(called_points[0].vector, expected_new, atol=1e-5)
    assert called_points[0].payload["impressions"] == 6
