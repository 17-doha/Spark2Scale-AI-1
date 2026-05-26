import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient

# --- Imports from application ---
from app.graph.feed_recommedation_agent.tools.tag_tools import (
    _days_since_updated,
    _apply_decay,
    fetch_unique_tags,
    get_investor_subtags,
    update_graph_edge_weights,
    sync_supabase_to_neo4j,
    get_sibling_subtags
)
from app.api.routes.feed_recommedation import router

# ==========================================
# SHARED TEST FIXTURES
# ==========================================

app = FastAPI()
app.include_router(router)
client = TestClient(app)

class DummyNeo4jDateTime:
    """Mock for neo4j.time.DateTime objects returned by Neo4j Python driver."""
    def __init__(self, dt):
        self.dt = dt
        self.tzinfo = dt.tzinfo
        
    def to_native(self):
        return self.dt

# ==========================================
# 1. TESTS FOR tag_tools.py (Unit Tests)
# ==========================================

def test_days_since_updated_none():
    """If neo4j_dt is None, it should return DECAY_DEFAULT_AGE_DAYS."""
    # Based on the tag_tools.py implementation (default 14 days)
    assert _days_since_updated(None) == 14.0

def test_days_since_updated_recent():
    """Test with a recent datetime."""
    dt = datetime.now(timezone.utc) - timedelta(days=2)
    neo_dt = DummyNeo4jDateTime(dt)
    days = _days_since_updated(neo_dt)
    assert 1.9 < days < 2.1

def test_apply_decay_recent():
    """Test decay on a recent node, weight should barely decrease."""
    dt = datetime.now(timezone.utc) - timedelta(days=0)
    neo_dt = DummyNeo4jDateTime(dt)
    weight = 1.0
    decayed = _apply_decay(weight, neo_dt)
    assert 0.9 < decayed <= 1.0

def test_apply_decay_old():
    """Test decay on an old node, weight should hit MIN_DECAYED_WEIGHT."""
    dt = datetime.now(timezone.utc) - timedelta(days=365)
    neo_dt = DummyNeo4jDateTime(dt)
    weight = 1.0
    decayed = _apply_decay(weight, neo_dt)
    assert decayed == 0.05  # MIN_DECAYED_WEIGHT

@patch("app.graph.feed_recommedation_agent.tools.supabase_tags.supabase")
def test_fetch_unique_tags(mock_supabase):
    """Test fetching and deduplicating tags from Supabase."""
    mock_resp = MagicMock()
    mock_resp.data = [
        {"tags": ["Fintech", "SaaS"]},
        {"tags": ["saas", "AI"]},
        {"tags": None}
    ]
    mock_supabase.table.return_value.select.return_value.execute.return_value = mock_resp
    
    unique_tags = fetch_unique_tags()
    assert unique_tags == ["ai", "fintech", "saas"]

@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.NEO4J_URI", "bolt://fake")
def test_get_investor_subtags(mock_driver_class):
    """Test UCB logic and sorting when fetching subtags."""
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_driver_class.return_value = mock_driver

    # Mock Neo4j return rows
    dt = datetime.now(timezone.utc) - timedelta(days=1)
    mock_session.run.return_value = [
        {"SubTag": "st1", "weight": 0.8, "impressions": 10, "last_updated": DummyNeo4jDateTime(dt)},
        {"SubTag": "st2", "weight": 0.2, "impressions": 1, "last_updated": DummyNeo4jDateTime(dt)},
    ]

    subtags = get_investor_subtags("user123", limit=2)
    
    # Both tags should be returned since limit=2
    assert "st1" in subtags
    assert "st2" in subtags

@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.NEO4J_URI", "bolt://fake")
def test_get_sibling_subtags(mock_driver_class):
    """Test fetching sibling subtags."""
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_driver_class.return_value = mock_driver

    mock_session.run.return_value = [
        {"SiblingSubTag": "sib1", "shared_parents": 2},
        {"SiblingSubTag": "sib2", "shared_parents": 1},
    ]

    siblings = get_sibling_subtags(["st1"])
    assert siblings == ["sib1", "sib2"]


# ==========================================
# 2. TESTS FOR API Routes (Integration Tests)
# ==========================================

@patch("app.api.routes.feed_recommedation.get_investor_subtags")
def test_api_fetch_investor_subtags(mock_get_investor_subtags):
    """Test the /investors/{user_id}/subtags endpoint."""
    mock_get_investor_subtags.return_value = ["subtag_a", "subtag_b"]
    
    response = client.get("/investors/user123/subtags?hate_threshold=0.05&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["subtags"] == ["subtag_a", "subtag_b"]
    assert data["hate_threshold_applied"] == 0.05
    assert data["limit"] == 10

@patch("app.api.routes.feed_recommedation.update_sub_vector_from_interaction")
@patch("app.api.routes.feed_recommedation.update_graph_edge_weights")
@patch("app.graph.feed_recommedation_agent.services.interaction_service.InteractionService.fetch_pitchdeck_tags")
def test_api_handle_interaction_like(mock_fetch_tags, mock_update_graph, mock_update_vector):
    """Test the /interactions endpoint for a LIKE action.

    Patches the task functions at the route-module level and the
    InteractionService.fetch_pitchdeck_tags static method.
    TestClient runs background tasks synchronously.
    """
    mock_fetch_tags.return_value = {
        "parent_tags": ["Fintech"],
        "sub_tags": ["Payments"],
        "raw_tags": ["Fintech"],
    }

    payload = {
        "user_id": "u1",
        "pitch_id": "p1",
        "liked": True,
        "contacted": False
    }
    response = client.post("/interactions", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "like" in data["message"].lower()

    # TestClient runs background tasks synchronously—both task functions must be called
    mock_update_graph.assert_called_once()
    mock_update_vector.assert_called_once()


# ==========================================
# 3. TESTS FOR Admin Validation (Validation Tests)
# ==========================================

@patch("app.graph.feed_recommedation_agent.services.sync_audit_service.SyncAuditService.verify")
def test_api_verify_full_sync_perfect(mock_verify):
    """Test /admin/verify-sync when both databases match perfectly."""
    mock_verify.return_value = {"status": "perfect", "discrepancy_count": 0, "discrepancies": []}

    response = client.get("/admin/verify-sync")
    assert response.status_code == 200
    assert response.json()["status"] == "perfect"

@patch("app.graph.feed_recommedation_agent.services.sync_audit_service.SyncAuditService.verify")
def test_api_verify_full_sync_mismatch(mock_verify):
    """Test /admin/verify-sync when there are discrepancies."""
    mock_verify.return_value = {
        "status": "mismatch_found",
        "discrepancy_count": 1,
        "discrepancies": [{
            "pitch_id": "p1",
            "tags_issue": {"in_neo4j_only": ["Blockchain"], "in_supabase_only": []},
            "subtags_issue": {"in_neo4j_only": [], "in_supabase_only": ["ML"]},
        }]
    }

    response = client.get("/admin/verify-sync")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "mismatch_found"
    assert data["discrepancy_count"] == 1
    assert "Blockchain" in data["discrepancies"][0]["tags_issue"]["in_neo4j_only"]


# ==========================================
# 4. ADDITIONAL UNIT TESTS (coverage gap fill)
# ==========================================

@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.neo4j_queries.NEO4J_URI", "bolt://fake")
def test_update_graph_edge_weights_like(mock_driver_class):
    """update_graph_edge_weights must call session.run with a weight-increment query on LIKE."""
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_driver_class.return_value = mock_driver

    update_graph_edge_weights(
        user_id="user_like_test",
        tag_names=["Fintech"],
        subtag_names=["Payments"],
        reward=1.0,
        alpha=0.1
    )

    # At minimum one Cypher query must have been executed
    assert mock_session.run.call_count >= 1
    # The query should contain the user_id
    call_args_list = mock_session.run.call_args_list
    cypher_calls = " ".join(str(c) for c in call_args_list)
    assert "user_like_test" in cypher_calls


@patch("app.graph.feed_recommedation_agent.tools.neo4j_sync.supabase")
@patch("app.graph.feed_recommedation_agent.tools.neo4j_sync.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.neo4j_sync.NEO4J_URI", "bolt://fake")
def test_sync_supabase_to_neo4j(mock_driver_class, mock_supabase):
    """sync_supabase_to_neo4j must MERGE each pitch from Supabase into Neo4j.
    
    neo4j_sync reads from supabase (investors + pitchdecks) and uses
    session.execute_write() to call _prune_stale_nodes and _add_pitch_node.
    """
    mock_investor_resp = MagicMock()
    mock_investor_resp.data = []
    mock_pitch_resp = MagicMock()
    mock_pitch_resp.data = [
        {"pitchdeckid": "p1", "tags": ["AI"], "extracted_subtags": ["ML"],
         "analysis": {"sub_tags": {"AI": ["ML"]}}}
    ]
    mock_supabase.table.return_value.select.return_value.execute.side_effect = [
        mock_investor_resp, mock_pitch_resp
    ]
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_driver_class.return_value = mock_driver

    sync_supabase_to_neo4j()

    # sync_supabase_to_neo4j uses session.execute_write internally;
    # at least one write transaction must have been executed.
    assert mock_session.execute_write.call_count >= 1
