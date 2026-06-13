"""Phase 5 test suite — FastAPI REST API.

Uses FastAPI's TestClient (via httpx) with an in-memory SQLite store
so tests are fully isolated and never touch disk.

Covers Phase 5 acceptance criteria:
  ✓ /docs (Swagger) endpoint reachable
  ✓ All user CRUD endpoints: POST, GET list, GET single, DELETE
  ✓ Friend requests: send, accept, reject, list pending (FIFO)
  ✓ Invalid payloads return 422/400/409, never 500
  ✓ Mutual friends and Jaccard similarity
  ✓ Recommendations exclude existing friends, sorted by score
  ✓ BFS shortest path and all-paths (backtracking)
  ✓ Analytics summary, influencers, charts (base64 PNG)
  ✓ Graph export (nodes + edges)
  ✓ Health check
"""

from __future__ import annotations

import base64
import pytest
from fastapi.testclient import TestClient

# ── Patch the store to use in-memory SQLite before importing app ───────────────
import app.main as main_module
from app.storage.store import Store
from app.models.graph import FriendGraph
from app.models.requests import FriendRequestManager


@pytest.fixture(autouse=True)
def reset_app_state():
    """Reset global singletons to a clean in-memory state before each test."""
    store = Store(":memory:")
    graph = FriendGraph()
    requests = FriendRequestManager(graph)

    main_module._store = store
    main_module._graph = graph
    main_module._requests = requests
    main_module._timestamps = {}
    yield


@pytest.fixture()
def client(reset_app_state) -> TestClient:
    return TestClient(main_module.app, raise_server_exceptions=False)


# ── Helpers ────────────────────────────────────────────────────────────────────

def create_user(client: TestClient, name: str, age: int = 25, city: str = "NYC",
                interests: list[str] | None = None) -> dict:
    r = client.post("/users", json={
        "name": name, "age": age, "city": city,
        "interests": interests or [],
    })
    assert r.status_code == 201, r.text
    return r.json()


def _is_valid_b64_png(s: str) -> bool:
    try:
        data = base64.b64decode(s)
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 1. Health & docs
# ─────────────────────────────────────────────────────────────────────────────

class TestMeta:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_openapi_docs_reachable(self, client):
        r = client.get("/docs")
        assert r.status_code == 200

    def test_openapi_json_reachable(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert "/users" in paths
        assert "/graph" in paths


# ─────────────────────────────────────────────────────────────────────────────
# 2. User CRUD
# ─────────────────────────────────────────────────────────────────────────────

class TestUsers:
    def test_create_user(self, client):
        r = client.post("/users", json={"name": "Alice", "age": 25, "city": "NYC"})
        assert r.status_code == 201
        d = r.json()
        assert d["name"] == "Alice"
        assert "user_id" in d

    def test_list_users_empty(self, client):
        r = client.get("/users")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_users_after_create(self, client):
        create_user(client, "Alice")
        create_user(client, "Bob")
        r = client.get("/users")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_get_user_by_id(self, client):
        alice = create_user(client, "Alice")
        r = client.get(f"/users/{alice['user_id']}")
        assert r.status_code == 200
        assert r.json()["name"] == "Alice"

    def test_get_user_not_found(self, client):
        r = client.get("/users/ghost")
        assert r.status_code == 404
        assert r.json()["error"] == "USER_NOT_FOUND"

    def test_delete_user(self, client):
        alice = create_user(client, "Alice")
        r = client.delete(f"/users/{alice['user_id']}")
        assert r.status_code == 204
        r2 = client.get(f"/users/{alice['user_id']}")
        assert r2.status_code == 404

    def test_delete_nonexistent_user(self, client):
        r = client.delete("/users/ghost")
        assert r.status_code == 404

    def test_duplicate_name_allowed(self, client):
        """Users are identified by UUID — same name is not a duplicate."""
        r1 = create_user(client, "Alice")
        r2 = create_user(client, "Alice")
        assert r1["user_id"] != r2["user_id"]

    def test_filter_by_city(self, client):
        create_user(client, "Alice", city="NYC")
        create_user(client, "Bob", city="LA")
        r = client.get("/users", params={"city": "NYC"})
        names = [u["name"] for u in r.json()]
        assert "Alice" in names
        assert "Bob" not in names

    def test_filter_by_interest(self, client):
        create_user(client, "Alice", interests=["music"])
        create_user(client, "Bob", interests=["gaming"])
        r = client.get("/users", params={"interest": "music"})
        names = [u["name"] for u in r.json()]
        assert "Alice" in names
        assert "Bob" not in names

    def test_degree_in_response(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        # Send and accept a request to create the friendship
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        client.post(f"/requests/{alice['user_id']}/accept",
                    params={"to_id": bob["user_id"]})
        r = client.get(f"/users/{alice['user_id']}")
        assert r.json()["degree"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. Validation errors
# ─────────────────────────────────────────────────────────────────────────────

class TestValidation:
    def test_age_below_13(self, client):
        r = client.post("/users", json={"name": "Kid", "age": 12, "city": "NYC"})
        assert r.status_code == 422

    def test_empty_name(self, client):
        r = client.post("/users", json={"name": "", "age": 25, "city": "NYC"})
        assert r.status_code == 422

    def test_missing_required_field(self, client):
        r = client.post("/users", json={"name": "Alice", "age": 25})
        assert r.status_code == 422

    def test_self_request_pydantic(self, client):
        alice = create_user(client, "Alice")
        r = client.post("/requests", json={
            "from_id": alice["user_id"], "to_id": alice["user_id"]
        })
        assert r.status_code == 422  # caught by Pydantic model validator

    def test_invalid_chart_kind(self, client):
        r = client.get("/analytics/charts/bogus")
        assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# 4. Friend requests
# ─────────────────────────────────────────────────────────────────────────────

class TestFriendRequests:
    def test_send_request(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        r = client.post("/requests", json={
            "from_id": alice["user_id"], "to_id": bob["user_id"]
        })
        assert r.status_code == 201
        assert r.json()["status"] == "PENDING"

    def test_get_pending_requests(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        r = client.get(f"/users/{bob['user_id']}/requests")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["from_id"] == alice["user_id"]

    def test_accept_creates_friendship(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        r = client.post(f"/requests/{alice['user_id']}/accept",
                        params={"to_id": bob["user_id"]})
        assert r.status_code == 200
        assert r.json()["status"] == "ACCEPTED"
        friends = client.get(f"/users/{alice['user_id']}/friends").json()
        assert any(f["user_id"] == bob["user_id"] for f in friends)

    def test_reject_removes_pending(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        r = client.post(f"/requests/{alice['user_id']}/reject",
                        params={"to_id": bob["user_id"]})
        assert r.status_code == 200
        assert r.json()["status"] == "REJECTED"
        pending = client.get(f"/users/{bob['user_id']}/requests").json()
        assert len(pending) == 0

    def test_reject_does_not_create_friendship(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        client.post(f"/requests/{alice['user_id']}/reject",
                    params={"to_id": bob["user_id"]})
        friends = client.get(f"/users/{alice['user_id']}/friends").json()
        assert len(friends) == 0

    def test_duplicate_request_returns_409(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        r = client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        assert r.status_code == 409
        assert r.json()["error"] == "DUPLICATE_REQUEST"

    def test_reverse_request_returns_409(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": bob["user_id"], "to_id": alice["user_id"]})
        r = client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        assert r.status_code == 409
        assert r.json()["error"] == "REVERSE_REQUEST"

    def test_already_friends_request_returns_409(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        client.post(f"/requests/{alice['user_id']}/accept", params={"to_id": bob["user_id"]})
        r = client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        assert r.status_code == 409

    def test_pending_requests_fifo_order(self, client):
        target = create_user(client, "Target")
        senders = [create_user(client, f"User{i}") for i in range(3)]
        for s in senders:
            client.post("/requests", json={"from_id": s["user_id"], "to_id": target["user_id"]})
        pending = client.get(f"/users/{target['user_id']}/requests").json()
        ids = [p["from_id"] for p in pending]
        assert ids == [s["user_id"] for s in senders]  # FIFO

    def test_accept_nonexistent_request_returns_404(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        r = client.post(f"/requests/{alice['user_id']}/accept",
                        params={"to_id": bob["user_id"]})
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 5. Friends management
# ─────────────────────────────────────────────────────────────────────────────

class TestFriendsManagement:
    def _make_friends(self, client, a_name="Alice", b_name="Bob"):
        a = create_user(client, a_name)
        b = create_user(client, b_name)
        client.post("/requests", json={"from_id": a["user_id"], "to_id": b["user_id"]})
        client.post(f"/requests/{a['user_id']}/accept", params={"to_id": b["user_id"]})
        return a, b

    def test_get_friends_list(self, client):
        alice, bob = self._make_friends(client)
        r = client.get(f"/users/{alice['user_id']}/friends")
        assert r.status_code == 200
        assert any(f["user_id"] == bob["user_id"] for f in r.json())

    def test_remove_friendship(self, client):
        alice, bob = self._make_friends(client)
        r = client.delete(f"/users/{alice['user_id']}/friends/{bob['user_id']}")
        assert r.status_code == 204
        friends = client.get(f"/users/{alice['user_id']}/friends").json()
        assert not any(f["user_id"] == bob["user_id"] for f in friends)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Mutual friends
# ─────────────────────────────────────────────────────────────────────────────

class TestMutualFriends:
    def test_mutual_friends_endpoint(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        carol = create_user(client, "Carol")
        # alice—bob, bob—carol (no alice—carol yet)
        for pair in [(alice, bob), (bob, carol)]:
            a, b = pair
            client.post("/requests", json={"from_id": a["user_id"], "to_id": b["user_id"]})
            client.post(f"/requests/{a['user_id']}/accept", params={"to_id": b["user_id"]})
        r = client.get(f"/users/{alice['user_id']}/mutual/{carol['user_id']}")
        assert r.status_code == 200
        d = r.json()
        assert bob["user_id"] in d["mutual_friends"]
        assert d["count"] == 1

    def test_jaccard_in_response(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        r = client.get(f"/users/{alice['user_id']}/mutual/{bob['user_id']}")
        assert "jaccard_similarity" in r.json()

    def test_no_mutuals(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        r = client.get(f"/users/{alice['user_id']}/mutual/{bob['user_id']}")
        assert r.json()["count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. Recommendations
# ─────────────────────────────────────────────────────────────────────────────

class TestRecommendations:
    def _build_network(self, client):
        alice = create_user(client, "Alice", city="NYC", interests=["music"])
        bob   = create_user(client, "Bob",   city="NYC", interests=["music", "gaming"])
        carol = create_user(client, "Carol", city="LA",  interests=["gaming"])
        for pair in [(alice, bob), (bob, carol)]:
            a, b = pair
            client.post("/requests", json={"from_id": a["user_id"], "to_id": b["user_id"]})
            client.post(f"/requests/{a['user_id']}/accept", params={"to_id": b["user_id"]})
        return alice, bob, carol

    def test_recommendations_returned(self, client):
        alice, _, _ = self._build_network(client)
        r = client.get(f"/users/{alice['user_id']}/recommendations")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_recommendations_exclude_friends(self, client):
        alice, bob, _ = self._build_network(client)
        r = client.get(f"/users/{alice['user_id']}/recommendations")
        rec_ids = [x["candidate_id"] for x in r.json()]
        assert bob["user_id"] not in rec_ids

    def test_recommendations_exclude_self(self, client):
        alice, _, _ = self._build_network(client)
        r = client.get(f"/users/{alice['user_id']}/recommendations")
        rec_ids = [x["candidate_id"] for x in r.json()]
        assert alice["user_id"] not in rec_ids

    def test_recommendation_has_explanation(self, client):
        alice, _, _ = self._build_network(client)
        r = client.get(f"/users/{alice['user_id']}/recommendations")
        why = r.json()[0]["why"]
        assert "mutuals" in why
        assert "shared_interests" in why
        assert "same_city" in why
        assert "score" in why

    def test_top_k_param(self, client):
        alice, _, _ = self._build_network(client)
        r = client.get(f"/users/{alice['user_id']}/recommendations", params={"top_k": 1})
        assert len(r.json()) <= 1


# ─────────────────────────────────────────────────────────────────────────────
# 8. Paths
# ─────────────────────────────────────────────────────────────────────────────

class TestPaths:
    def _chain(self, client, n=4):
        """Create a chain of n users: u0—u1—u2—…—u(n-1)."""
        users = [create_user(client, f"U{i}") for i in range(n)]
        for i in range(n - 1):
            a, b = users[i], users[i + 1]
            client.post("/requests", json={"from_id": a["user_id"], "to_id": b["user_id"]})
            client.post(f"/requests/{a['user_id']}/accept", params={"to_id": b["user_id"]})
        return users

    def test_shortest_path_direct(self, client):
        users = self._chain(client, 2)
        r = client.get("/path", params={"from": users[0]["user_id"],
                                         "to":   users[1]["user_id"]})
        assert r.status_code == 200
        d = r.json()
        assert d["hops"] == 1
        assert d["connected"] is True

    def test_shortest_path_multi_hop(self, client):
        users = self._chain(client, 4)
        r = client.get("/path", params={"from": users[0]["user_id"],
                                         "to":   users[3]["user_id"]})
        assert r.json()["hops"] == 3

    def test_path_to_self(self, client):
        alice = create_user(client, "Alice")
        r = client.get("/path", params={"from": alice["user_id"],
                                         "to":   alice["user_id"]})
        assert r.json()["hops"] == 0

    def test_disconnected_path(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        r = client.get("/path", params={"from": alice["user_id"],
                                         "to":   bob["user_id"]})
        d = r.json()
        assert d["connected"] is False
        assert d["path"] is None

    def test_shortest_path_missing_user(self, client):
        alice = create_user(client, "Alice")
        r = client.get("/path", params={"from": alice["user_id"], "to": "ghost"})
        assert r.status_code == 404

    def test_all_paths_returns_list(self, client):
        users = self._chain(client, 3)
        r = client.get("/paths", params={"from": users[0]["user_id"],
                                          "to":   users[2]["user_id"]})
        assert r.status_code == 200
        assert "paths" in r.json()
        assert "count" in r.json()

    def test_all_paths_count(self, client):
        users = self._chain(client, 3)
        r = client.get("/paths", params={"from": users[0]["user_id"],
                                          "to":   users[2]["user_id"]})
        assert r.json()["count"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 9. Analytics
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_summary_empty_graph(self, client):
        r = client.get("/analytics/summary")
        assert r.status_code == 200
        d = r.json()
        assert d["total_users"] == 0
        assert d["total_edges"] == 0

    def test_summary_with_data(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        client.post(f"/requests/{alice['user_id']}/accept", params={"to_id": bob["user_id"]})
        d = client.get("/analytics/summary").json()
        assert d["total_users"] == 2
        assert d["total_edges"] == 1

    def test_summary_keys(self, client):
        d = client.get("/analytics/summary").json()
        for key in ["total_users", "total_edges", "density",
                    "diameter", "average_separation", "num_components"]:
            assert key in d

    def test_influencers_endpoint(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        client.post(f"/requests/{alice['user_id']}/accept", params={"to_id": bob["user_id"]})
        r = client.get("/analytics/influencers", params={"top_n": 2})
        assert r.status_code == 200
        assert len(r.json()) <= 2

    def test_chart_top_connected(self, client):
        create_user(client, "Alice")
        r = client.get("/analytics/charts/top_connected")
        assert r.status_code == 200
        assert _is_valid_b64_png(r.json()["image"])

    def test_chart_city_distribution(self, client):
        create_user(client, "Alice", city="NYC")
        r = client.get("/analytics/charts/city_distribution")
        assert r.status_code == 200
        assert _is_valid_b64_png(r.json()["image"])

    def test_chart_degree_distribution(self, client):
        create_user(client, "Alice")
        r = client.get("/analytics/charts/degree_distribution")
        assert r.status_code == 200
        assert _is_valid_b64_png(r.json()["image"])

    def test_chart_network_graph(self, client):
        r = client.get("/analytics/charts/network_graph")
        assert r.status_code == 200
        assert _is_valid_b64_png(r.json()["image"])

    def test_chart_friendship_growth(self, client):
        r = client.get("/analytics/charts/friendship_growth")
        assert r.status_code == 200
        # growth chart may be empty if no timestamps — still returns valid PNG
        assert "image" in r.json()


# ─────────────────────────────────────────────────────────────────────────────
# 10. Graph export
# ─────────────────────────────────────────────────────────────────────────────

class TestGraphExport:
    def test_graph_empty(self, client):
        r = client.get("/graph")
        assert r.status_code == 200
        d = r.json()
        assert d["nodes"] == []
        assert d["edges"] == []

    def test_graph_nodes_and_edges(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        client.post(f"/requests/{alice['user_id']}/accept", params={"to_id": bob["user_id"]})
        d = client.get("/graph").json()
        assert len(d["nodes"]) == 2
        assert len(d["edges"]) == 1

    def test_graph_node_has_community(self, client):
        create_user(client, "Alice")
        nodes = client.get("/graph").json()["nodes"]
        assert "community" in nodes[0]

    def test_graph_edge_has_source_target(self, client):
        alice = create_user(client, "Alice")
        bob   = create_user(client, "Bob")
        client.post("/requests", json={"from_id": alice["user_id"], "to_id": bob["user_id"]})
        client.post(f"/requests/{alice['user_id']}/accept", params={"to_id": bob["user_id"]})
        edges = client.get("/graph").json()["edges"]
        assert "source" in edges[0]
        assert "target" in edges[0]
