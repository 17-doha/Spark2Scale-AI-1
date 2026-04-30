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

@patch("app.graph.feed_recommedation_agent.tools.tag_tools.supabase")
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

@patch("app.graph.feed_recommedation_agent.tools.tag_tools.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.tag_tools.NEO4J_URI", "bolt://fake")
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

@patch("app.graph.feed_recommedation_agent.tools.tag_tools.GraphDatabase.driver")
@patch("app.graph.feed_recommedation_agent.tools.tag_tools.NEO4J_URI", "bolt://fake")
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

@patch("app.api.routes.feed_recommedation.supabase")
@patch("app.api.routes.feed_recommedation.BackgroundTasks.add_task")
def test_api_handle_interaction_like(mock_add_task, mock_supabase):
    """Test the /interactions endpoint for a LIKE action."""
    mock_resp = MagicMock()
    mock_resp.data = {
        "tags": ["Fintech"],
        "analysis": {"sub_tags": {"Fintech": ["Payments"]}}
    }
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_resp

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
    
    # Check if background tasks were added (update_graph_edge_weights & update_sub_vector_from_interaction)
    assert mock_add_task.call_count == 2


# ==========================================
# 3. TESTS FOR Admin Validation (Validation Tests)
# ==========================================

@patch("app.api.routes.feed_recommedation.supabase")
@patch("app.api.routes.feed_recommedation.GraphDatabase.driver")
@patch("app.api.routes.feed_recommedation.NEO4J_URI", "bolt://fake")
def test_api_verify_full_sync_perfect(mock_driver_class, mock_supabase):
    """Test /admin/verify-sync when both databases match perfectly."""
    # Supabase Mock
    mock_supa_resp = MagicMock()
    mock_supa_resp.data = [
        {"pitchdeckid": "p1", "tags": ["AI"], "extracted_subtags": ["ML"]},
    ]
    mock_supabase.table.return_value.select.return_value.execute.return_value = mock_supa_resp

    # Neo4j Mock
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_driver_class.return_value = mock_driver

    mock_session.run.return_value = [
        {"pitch_id": "p1", "tags": ["AI"], "sub_tags": ["ML"]},
    ]

    response = client.get("/admin/verify-sync")
    assert response.status_code == 200
    assert response.json()["status"] == "perfect"

@patch("app.api.routes.feed_recommedation.supabase")
@patch("app.api.routes.feed_recommedation.GraphDatabase.driver")
@patch("app.api.routes.feed_recommedation.NEO4J_URI", "bolt://fake")
def test_api_verify_full_sync_mismatch(mock_driver_class, mock_supabase):
    """Test /admin/verify-sync when there are discrepancies."""
    # Supabase Mock
    mock_supa_resp = MagicMock()
    mock_supa_resp.data = [
        {"pitchdeckid": "p1", "tags": ["AI"], "extracted_subtags": ["ML"]},
    ]
    mock_supabase.table.return_value.select.return_value.execute.return_value = mock_supa_resp

    # Neo4j Mock
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_driver_class.return_value = mock_driver

    mock_session.run.return_value = [
        {"pitch_id": "p1", "tags": ["AI", "Blockchain"], "sub_tags": []},
    ]

    response = client.get("/admin/verify-sync")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "mismatch_found"
    assert data["discrepancy_count"] == 1
    assert "Blockchain" in data["discrepancies"][0]["tags_issue"]["in_neo4j_only"]
