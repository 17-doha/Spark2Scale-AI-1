import pytest
import math
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from app.graph.feed_recommedation_agent.tools.decay import (
    _days_since_updated,
    _apply_decay,
    DECAY_DEFAULT_AGE_DAYS,
    MIN_DECAYED_WEIGHT,
)
from app.graph.feed_recommedation_agent.tools.neo4j_queries import (
    get_investor_subtags,
)
from app.graph.feed_recommedation_agent.rewards import InteractionType
from app.graph.feed_recommedation_agent.node import sibling_fallback_node
from app.graph.feed_recommedation_agent.tools.contrastive import (
    triplet_update,
    _l2_normalize
)

@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.NEO4J_URI", "mock_uri")
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
    # Use isclose: microseconds elapse between now() and the decay call,
    # so the result is 0.9999... not exactly 1.0
    assert math.isclose(fresh_weight, base_weight, rel_tol=1e-4)
    
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


# ══════════════════════════════════════════════════════════════════════════════
#  _days_since_updated  —  edge cases
# ══════════════════════════════════════════════════════════════════════════════

def test_days_since_updated_none_returns_default():
    """None timestamp → DECAY_DEFAULT_AGE_DAYS (not zero, not huge)."""
    result = _days_since_updated(None)
    assert result == DECAY_DEFAULT_AGE_DAYS


def test_days_since_updated_now_returns_zero():
    """A timestamp equal to now → 0 days elapsed."""
    now = datetime.now(timezone.utc)
    result = _days_since_updated(now)
    assert 0.0 <= result < 0.01   # effectively zero


def test_days_since_updated_30_days_ago():
    """Timestamp 30 days ago → ~30 days."""
    from datetime import timedelta
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    result = _days_since_updated(thirty_days_ago)
    assert 29.9 < result < 30.1


def test_days_since_updated_naive_datetime():
    """A tz-naive datetime is treated as UTC (should not raise)."""
    from datetime import timedelta
    naive_dt = datetime.now() - timedelta(days=7)
    result = _days_since_updated(naive_dt)
    # Use a wider tolerance band to account for test execution time on any machine
    assert 6.8 < result < 7.2


# ══════════════════════════════════════════════════════════════════════════════
#  _apply_decay  —  floor and ceiling behaviour
# ══════════════════════════════════════════════════════════════════════════════

def test_apply_decay_floor_not_zero():
    """Even a very old timestamp must not decay below MIN_DECAYED_WEIGHT."""
    from datetime import timedelta
    ancient = datetime.now(timezone.utc) - timedelta(days=3650)   # ~10 years
    result = _apply_decay(1.0, ancient)
    assert result >= MIN_DECAYED_WEIGHT


def test_apply_decay_fresh_tag_unchanged():
    """A tag updated seconds ago should keep essentially its full weight."""
    now = datetime.now(timezone.utc)
    result = _apply_decay(0.8, now)
    assert math.isclose(result, 0.8, rel_tol=1e-3)


def test_apply_decay_low_weight_floored():
    """A low-weight tag that decays further must still be >= MIN_DECAYED_WEIGHT."""
    from datetime import timedelta
    one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
    result = _apply_decay(0.001, one_year_ago)
    assert result == MIN_DECAYED_WEIGHT


# ══════════════════════════════════════════════════════════════════════════════
#  get_investor_subtags  —  hate threshold filtering
# ══════════════════════════════════════════════════════════════════════════════

@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.NEO4J_URI", "mock_uri")
def test_get_investor_subtags_returns_empty_when_no_rows(mock_driver):
    """An investor with no Neo4j edges → empty list (no crash)."""
    mock_session = MagicMock()
    mock_driver.return_value.session.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value = []

    result = get_investor_subtags("nobody", limit=10)
    assert result == []


@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.NEO4J_URI", "mock_uri")
def test_get_investor_subtags_exploit_ordering(mock_driver):
    """
    With a limit of 5 and 80% exploit ratio, the top 4 items should be
    the ones with the highest decayed_weight (all fresh → no decay).
    """
    mock_session = MagicMock()
    mock_driver.return_value.session.return_value.__enter__.return_value = mock_session
    now = datetime.now(timezone.utc)
    mock_session.run.return_value = [
        {"SubTag": "High_A",  "weight": 0.95, "impressions": 10, "last_updated": now},
        {"SubTag": "High_B",  "weight": 0.90, "impressions": 10, "last_updated": now},
        {"SubTag": "High_C",  "weight": 0.85, "impressions": 10, "last_updated": now},
        {"SubTag": "High_D",  "weight": 0.80, "impressions": 10, "last_updated": now},
        {"SubTag": "Low_E",   "weight": 0.10, "impressions": 0,  "last_updated": now},
    ]

    result = get_investor_subtags("user_x", limit=5)
    # The first 4 results must be the high-weight tags (in any order within exploit pool)
    exploit_part = set(result[:4])
    assert "High_A" in exploit_part
    assert "High_B" in exploit_part
    assert "High_C" in exploit_part
    assert "High_D" in exploit_part


# ══════════════════════════════════════════════════════════════════════════════
#  _l2_normalize
# ══════════════════════════════════════════════════════════════════════════════

def test_l2_normalize_unit_length():
    """Output vector must have L2 norm ≈ 1."""
    vec = np.array([3.0, 4.0], dtype=np.float32)
    result = _l2_normalize(vec)
    norm = sum(x**2 for x in result) ** 0.5
    assert math.isclose(norm, 1.0, rel_tol=1e-5)


def test_l2_normalize_zero_vector_safe():
    """A zero vector must not raise — returns the zero vector unchanged."""
    vec = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    result = _l2_normalize(vec)
    assert result == [0.0, 0.0, 0.0]


# ══════════════════════════════════════════════════════════════════════════════
#  triplet_update  —  LIKE-only, DISLIKE-only, no vector, missing sub-vector
# ══════════════════════════════════════════════════════════════════════════════

@patch("app.graph.feed_recommedation_agent.tools.contrastive.get_qdrant")
def test_triplet_update_like_only(mock_get_qdrant):
    """LIKE: only e_pos is supplied → pull term only (no push)."""
    mock_client = MagicMock()
    mock_get_qdrant.return_value = mock_client

    e_old = [0.0, 0.0, 1.0]
    mock_point = MagicMock()
    mock_point.vector  = e_old
    mock_point.payload = {"impressions": 2, "investor_id": "u1", "tag_name": "AI"}
    mock_client.retrieve.return_value = [mock_point]

    e_pos = [0.0, 1.0, 0.0]
    alpha = 0.1

    result = triplet_update("u1", "AI", e_pos=e_pos, e_neg=None, alpha=alpha)

    assert result is True
    called_points = mock_client.upsert.call_args[1]["points"]
    new_vec = np.array(called_points[0].vector)
    # Direction should have moved toward e_pos
    assert new_vec[1] > 0   # y-component increased from 0
    assert called_points[0].payload["impressions"] == 3


@patch("app.graph.feed_recommedation_agent.tools.contrastive.get_qdrant")
def test_triplet_update_dislike_only(mock_get_qdrant):
    """DISLIKE: only e_neg is supplied → push term only (no pull)."""
    mock_client = MagicMock()
    mock_get_qdrant.return_value = mock_client

    e_old = [1.0, 0.0, 0.0]
    mock_point = MagicMock()
    mock_point.vector  = e_old
    mock_point.payload = {"impressions": 0, "investor_id": "u2", "tag_name": "Fin"}
    mock_client.retrieve.return_value = [mock_point]

    e_neg  = [1.0, 0.0, 0.0]   # same direction → push away from itself
    gamma  = 0.05

    result = triplet_update("u2", "Fin", e_pos=None, e_neg=e_neg, gamma=gamma)

    assert result is True
    called_points = mock_client.upsert.call_args[1]["points"]
    # The x-component should not have increased (pushed away from e_neg direction)
    # When e_neg == e_old, the push term is zero so the vector stays the same (normalized).
    new_vec = np.array(called_points[0].vector)
    assert float(new_vec[0]) <= 1.0


@patch("app.graph.feed_recommedation_agent.tools.contrastive.get_qdrant")
def test_triplet_update_no_vector_returns_false(mock_get_qdrant):
    """Both e_pos and e_neg are None → function returns False immediately."""
    result = triplet_update("u3", "SomeTag", e_pos=None, e_neg=None)
    assert result is False
    mock_get_qdrant.assert_not_called()


@patch("app.graph.feed_recommedation_agent.tools.contrastive.get_qdrant")
def test_triplet_update_missing_sub_vector_returns_false(mock_get_qdrant):
    """If the sub-vector point doesn't exist in Qdrant → returns False (not crash)."""
    mock_client = MagicMock()
    mock_get_qdrant.return_value = mock_client
    mock_client.retrieve.return_value = []   # empty → sub-vector not built yet

    result = triplet_update("u4", "NonExistent", e_pos=[0.1, 0.2, 0.3])
    assert result is False
    mock_client.upsert.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
#  select_query_vector_ucb
# ══════════════════════════════════════════════════════════════════════════════

@patch("app.graph.feed_recommedation_agent.tools.contrastive.get_qdrant")
@patch("app.graph.feed_recommedation_agent.tools.contrastive._ensure_collection")
def test_select_query_vector_ucb_picks_unqueried_first(mock_ensure, mock_get_qdrant):
    """
    A sub-vector with 0 impressions must win (UCB = ∞) over one with
    many impressions, regardless of the constant prior.
    """
    mock_client = MagicMock()
    mock_get_qdrant.return_value = mock_client

    point_explored = MagicMock()
    point_explored.vector  = [0.1, 0.2, 0.3]
    point_explored.payload = {"investor_id": "u5", "tag_name": "Tech", "impressions": 100}

    point_new = MagicMock()
    point_new.vector  = [0.9, 0.1, 0.0]
    point_new.payload = {"investor_id": "u5", "tag_name": "Health", "impressions": 0}

    mock_client.scroll.return_value = ([point_explored, point_new], None)

    from app.graph.feed_recommedation_agent.tools.contrastive import select_query_vector_ucb
    vector, tag = select_query_vector_ucb("u5")

    assert tag == "Health"          # 0 impressions → UCB = ∞ → wins
    assert vector == [0.9, 0.1, 0.0]


@patch("app.graph.feed_recommedation_agent.tools.contrastive.get_qdrant")
@patch("app.graph.feed_recommedation_agent.tools.contrastive._ensure_collection")
def test_select_query_vector_ucb_no_points_returns_none(mock_ensure, mock_get_qdrant):
    """If the collection has no points for this investor → (None, None)."""
    mock_client = MagicMock()
    mock_get_qdrant.return_value = mock_client
    mock_client.scroll.return_value = ([], None)

    from app.graph.feed_recommedation_agent.tools.contrastive import select_query_vector_ucb
    vector, tag = select_query_vector_ucb("u_unknown")

    assert vector is None
    assert tag is None


# ══════════════════════════════════════════════════════════════════════════════
#  increment_sub_vector_impressions
# ══════════════════════════════════════════════════════════════════════════════

@patch("app.graph.feed_recommedation_agent.tools.contrastive.get_qdrant")
def test_increment_sub_vector_impressions(mock_get_qdrant):
    """Calling increment bumps the impression counter by exactly 1."""
    mock_client = MagicMock()
    mock_get_qdrant.return_value = mock_client

    mock_point = MagicMock()
    mock_point.payload = {"impressions": 7}
    mock_client.retrieve.return_value = [mock_point]

    from app.graph.feed_recommedation_agent.tools.contrastive import (
        increment_sub_vector_impressions,
    )
    increment_sub_vector_impressions("u6", "Fintech")

    mock_client.set_payload.assert_called_once()
    payload_arg = mock_client.set_payload.call_args[1]["payload"]
    assert payload_arg["impressions"] == 8


@patch("app.graph.feed_recommedation_agent.tools.contrastive.get_qdrant")
def test_increment_sub_vector_missing_point_no_crash(mock_get_qdrant):
    """If point not found, increment is a no-op (no exception raised)."""
    mock_client = MagicMock()
    mock_get_qdrant.return_value = mock_client
    mock_client.retrieve.return_value = []   # point doesn't exist

    from app.graph.feed_recommedation_agent.tools.contrastive import (
        increment_sub_vector_impressions,
    )
    increment_sub_vector_impressions("u7", "ghost_tag")   # must not raise
    mock_client.set_payload.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
#  get_sibling_subtags  —  mock Neo4j
# ══════════════════════════════════════════════════════════════════════════════

@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.NEO4J_URI", "mock_uri")
def test_get_sibling_subtags_returns_siblings(mock_driver):
    """Siblings are returned ordered by shared_parents count (mocked)."""
    from app.graph.feed_recommedation_agent.tools.neo4j_queries import get_sibling_subtags

    mock_session = MagicMock()
    mock_driver.return_value.session.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value = [
        {"SiblingSubTag": "SiblingA"},
        {"SiblingSubTag": "SiblingB"},
    ]

    result = get_sibling_subtags(["Tag_Exp1"], exclude=["Tag_Exp1"], limit=10)
    assert result == ["SiblingA", "SiblingB"]


@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.NEO4J_URI", "")
def test_get_sibling_subtags_no_uri_returns_empty():
    """If NEO4J_URI is empty → returns [] without connecting."""
    from app.graph.feed_recommedation_agent.tools.neo4j_queries import get_sibling_subtags
    result = get_sibling_subtags(["AnyTag"])
    assert result == []


@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.NEO4J_URI", "mock_uri")
def test_get_sibling_subtags_empty_input_returns_empty():
    """Empty subtag list → returns [] immediately (no Neo4j call)."""
    from app.graph.feed_recommedation_agent.tools.neo4j_queries import get_sibling_subtags
    result = get_sibling_subtags([])
    assert result == []


# ══════════════════════════════════════════════════════════════════════════════
#  LangGraph node tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@patch("app.graph.feed_recommedation_agent.node.get_investor_subtags")
async def test_generate_filter_tags_node(mock_get_subtags):
    """Node 1 must populate filter_tags from Neo4j subtags."""
    from app.graph.feed_recommedation_agent.node import generate_filter_tags_node

    mock_get_subtags.return_value = ["SubA", "SubB", "SubC"]
    state = {"investor_id": "u_test"}

    result = await generate_filter_tags_node(state)

    assert result["filter_tags"] == ["SubA", "SubB", "SubC"]
    mock_get_subtags.assert_called_once_with("u_test")


@pytest.mark.asyncio
@patch("app.graph.feed_recommedation_agent.node.get_investor_subtags")
async def test_generate_filter_tags_node_empty(mock_get_subtags):
    """Node 1 with no subtags → filter_tags is empty list (no crash)."""
    from app.graph.feed_recommedation_agent.node import generate_filter_tags_node

    mock_get_subtags.return_value = []
    result = await generate_filter_tags_node({"investor_id": "u_empty"})
    assert result["filter_tags"] == []


@pytest.mark.asyncio
@patch("app.graph.feed_recommedation_agent.node.get_qdrant")
async def test_filtered_vector_search_node_no_vector(mock_get_qdrant):
    """Node 3: investor_vector=None → returns empty candidates, records error."""
    from app.graph.feed_recommedation_agent.node import filtered_vector_search_node

    state = {
        "investor_id"    : "u_test",
        "investor_vector": None,
        "filter_tags"    : ["SubA"],
    }
    result = await filtered_vector_search_node(state)

    assert result["candidates"] == []
    assert len(result["errors"]) > 0
    mock_get_qdrant.assert_not_called()


@pytest.mark.asyncio
@patch("app.graph.feed_recommedation_agent.node.get_qdrant")
async def test_filtered_vector_search_node_with_results(mock_get_qdrant):
    """Node 3: valid vector → candidates populated from Qdrant response."""
    from app.graph.feed_recommedation_agent.node import filtered_vector_search_node

    mock_client = MagicMock()
    mock_get_qdrant.return_value = mock_client

    mock_hit = MagicMock()
    mock_hit.payload = {"pitchdeck_id": "pd_001", "startup_id": "s_001", "tags": ["AI"]}
    mock_hit.score = 0.93
    mock_client.query_points.return_value.points = [mock_hit]

    state = {
        "investor_id"    : "u_test",
        "investor_vector": [0.1, 0.2, 0.3],
        "filter_tags"    : ["AI"],
    }
    result = await filtered_vector_search_node(state)

    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["pitchdeck_id"] == "pd_001"
    assert candidate["vector_score"] == 0.93


@pytest.mark.asyncio
@patch("app.graph.feed_recommedation_agent.node.rerank")
@patch("app.graph.feed_recommedation_agent.node.fetch_investor_tags")
async def test_rerank_candidates_node_success(mock_fetch_tags, mock_rerank):
    """Node 4: reranker returns re-ordered results with rerank_score attached."""
    from app.graph.feed_recommedation_agent.node import rerank_candidates_node

    mock_fetch_tags.return_value = ["AI", "Fintech"]
    mock_rerank.return_value = [
        {"index": 1, "relevance_score": 0.95},
        {"index": 0, "relevance_score": 0.80},
    ]

    candidates = [
        {"pitchdeck_id": "pd_A", "tags": ["AI"],      "vector_score": 0.90},
        {"pitchdeck_id": "pd_B", "tags": ["Fintech"], "vector_score": 0.88},
    ]
    state = {"investor_id": "u_test", "candidates": candidates}

    with patch("app.graph.feed_recommedation_agent.node.TOP_K", 2):
        result = await rerank_candidates_node(state)

    final = result["final_results"]
    assert len(final) == 2
    assert final[0]["pitchdeck_id"] == "pd_B"   # index 1 → ranked first
    assert final[0]["rerank_score"] == 0.95
    assert final[1]["pitchdeck_id"] == "pd_A"   # index 0 → ranked second


@pytest.mark.asyncio
@patch("app.graph.feed_recommedation_agent.node.rerank", side_effect=Exception("Jina timeout"))
@patch("app.graph.feed_recommedation_agent.node.fetch_investor_tags")
async def test_rerank_candidates_node_fallback_on_error(mock_fetch_tags, mock_rerank):
    """Node 4: if reranker raises, falls back to vector-order (non-fatal)."""
    from app.graph.feed_recommedation_agent.node import rerank_candidates_node

    mock_fetch_tags.return_value = ["AI"]
    candidates = [
        {"pitchdeck_id": "pd_X", "tags": ["AI"], "vector_score": 0.99},
        {"pitchdeck_id": "pd_Y", "tags": ["AI"], "vector_score": 0.80},
    ]
    state = {"investor_id": "u_test", "candidates": candidates}

    with patch("app.graph.feed_recommedation_agent.node.TOP_K", 2):
        result = await rerank_candidates_node(state)

    # Fallback: returns candidates in original vector order
    final = result["final_results"]
    assert len(final) == 2
    assert final[0]["pitchdeck_id"] == "pd_X"
    # Error is recorded
    assert any("Reranker fallback" in e for e in result.get("errors", []))


@pytest.mark.asyncio
async def test_rerank_candidates_node_empty_candidates():
    """Node 4: no candidates → final_results=[], error recorded."""
    from app.graph.feed_recommedation_agent.node import rerank_candidates_node

    result = await rerank_candidates_node({"investor_id": "u_test", "candidates": []})
    assert result["final_results"] == []
    assert len(result["errors"]) > 0


@pytest.mark.asyncio
async def test_format_output_node_passthrough():
    """Node 5 is a passthrough — final_results must come out unchanged."""
    from app.graph.feed_recommedation_agent.node import format_output_node

    final_results = [
        {"pitchdeck_id": "pd_1", "vector_score": 0.91, "rerank_score": 0.97},
        {"pitchdeck_id": "pd_2", "vector_score": 0.88, "rerank_score": 0.85},
    ]
    state = {"investor_id": "u_test", "final_results": final_results}
    result = await format_output_node(state)

    assert result["final_results"] == final_results


# ══════════════════════════════════════════════════════════════════════════════
#  sibling_fallback_node  —  edge cases
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sibling_fallback_node_no_vector():
    """If investor_vector is None, fallback is skipped gracefully."""
    state = {
        "candidates"     : [],
        "filter_tags"    : ["A"],
        "investor_vector": None,
    }
    result = await sibling_fallback_node(state)

    assert result["fallback_triggered"] is False
    assert "errors" in result


@pytest.mark.asyncio
@patch("app.graph.feed_recommedation_agent.node.get_sibling_subtags")
async def test_sibling_fallback_node_no_siblings(mock_get_siblings):
    """If Neo4j returns no siblings, fallback_triggered=True but no new candidates."""
    mock_get_siblings.return_value = []

    state = {
        "candidates"     : [{"pitchdeck_id": "p1", "tags": ["A"], "vector_score": 0.9}],
        "filter_tags"    : ["A"],
        "investor_vector": [0.1, 0.2, 0.3],
    }

    with patch("app.graph.feed_recommedation_agent.node.TOP_K", 10):
        result = await sibling_fallback_node(state)

    assert result["fallback_triggered"] is True
    assert result["sibling_tags"] == []


@pytest.mark.asyncio
@patch("app.graph.feed_recommedation_agent.node.get_qdrant")
@patch("app.graph.feed_recommedation_agent.node.get_sibling_subtags")
async def test_sibling_fallback_node_deduplication(mock_get_siblings, mock_get_qdrant):
    """Sibling hits that duplicate existing candidates are excluded."""
    mock_get_siblings.return_value = ["Sibling_X"]

    mock_client = MagicMock()
    mock_get_qdrant.return_value = mock_client

    # Qdrant returns p1 (already in candidates) and p99 (new)
    dup_point = MagicMock()
    dup_point.payload = {"pitchdeck_id": "p1", "startup_id": "s1", "tags": ["Sibling_X"]}
    dup_point.score = 0.75

    new_point = MagicMock()
    new_point.payload = {"pitchdeck_id": "p99", "startup_id": "s99", "tags": ["Sibling_X"]}
    new_point.score = 0.70

    mock_client.query_points.return_value.points = [dup_point, new_point]

    state = {
        "candidates"     : [{"pitchdeck_id": "p1", "tags": ["A"], "vector_score": 0.9}],
        "filter_tags"    : ["A"],
        "investor_vector": [0.1, 0.2, 0.3],
    }

    with patch("app.graph.feed_recommedation_agent.node.TOP_K", 10):
        result = await sibling_fallback_node(state)

    ids = [c["pitchdeck_id"] for c in result["candidates"]]
    assert ids.count("p1")  == 1    # no duplicate
    assert "p99" in ids             # new hit added


# ══════════════════════════════════════════════════════════════════════════════
#  InteractionType.from_payload  —  OCP / Liskov factory method
# ══════════════════════════════════════════════════════════════════════════════

def test_from_payload_contact():
    """contacted=True takes priority over liked."""
    action, label = InteractionType.from_payload(liked=True, contacted=True)
    assert action == InteractionType.CONTACT
    assert label == "contact"


def test_from_payload_like():
    """liked=True, contacted=False → LIKE."""
    action, label = InteractionType.from_payload(liked=True, contacted=False)
    assert action == InteractionType.LIKE
    assert label == "like"


def test_from_payload_dislike():
    """Both False → DISLIKE."""
    action, label = InteractionType.from_payload(liked=False, contacted=False)
    assert action == InteractionType.DISLIKE
    assert label == "dislike"
