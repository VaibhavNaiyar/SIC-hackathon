"""Phase 4 test suite — Analytics, Visualization & Persistence.

Covers Phase 4 acceptance criteria:
  ✓ Diameter and avg separation match hand-computed fixture values
  ✓ Floyd-Warshall distance matrix is correct
  ✓ Charts generate headlessly and return valid base64 PNG strings
  ✓ Restarting (load_state) reloads the exact same graph from SQLite
  ✓ Upsert / delete operations on users, friendships, requests
  ✓ save_state + load_state round-trip for graph and pending requests
  ✓ City distribution, degree stats, influencer leaderboard
  ✓ Friendship growth time-series with timestamps
"""

from __future__ import annotations

import base64
import math
from datetime import datetime, timezone, timedelta

import numpy as np
import pytest

from app.models.graph import FriendGraph
from app.models.requests import FriendRequestManager
from app.models.user import User
from app.services.analytics import NetworkAnalytics, detect_communities
from app.storage.store import Store
from app.viz.charts import (
    chart_city_distribution,
    chart_degree_distribution,
    chart_friendship_growth,
    chart_network_graph,
    chart_top_connected,
    _empty_chart,
)


# ── Fixture helpers ────────────────────────────────────────────────────────────


def u(uid: str, city: str = "NYC", interests: set[str] | None = None) -> User:
    return User(
        name=uid.capitalize(), age=25, city=city,
        interests=interests or set(), user_id=uid,
    )


def _is_valid_b64_png(s: str) -> bool:
    """Return True if s is a non-empty base64 string that decodes to a PNG."""
    try:
        data = base64.b64decode(s)
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    except Exception:
        return False


@pytest.fixture()
def line5() -> FriendGraph:
    """Line graph: 0—1—2—3—4  (diameter=4, avg_sep=2.0 for connected pairs)."""
    g = FriendGraph()
    for i in range(5):
        g.add_user(u(str(i)))
    for i in range(4):
        g.add_friend(str(i), str(i + 1))
    return g


@pytest.fixture()
def triangle() -> FriendGraph:
    """Triangle: a—b—c—a  (diameter=1, avg_sep=1.0)."""
    g = FriendGraph()
    for uid in ["a", "b", "c"]:
        g.add_user(u(uid))
    g.add_friend("a", "b")
    g.add_friend("b", "c")
    g.add_friend("a", "c")
    return g


@pytest.fixture()
def social() -> FriendGraph:
    """6-user graph with multiple cities and interests."""
    g = FriendGraph()
    specs = [
        ("alice", "NYC", {"music", "hiking"}),
        ("bob",   "NYC", {"music", "gaming"}),
        ("carol", "LA",  {"gaming", "cooking"}),
        ("dave",  "NYC", {"hiking", "cooking"}),
        ("eve",   "LA",  {"music", "gaming"}),
        ("frank", "NYC", {"hiking", "music"}),
    ]
    for uid, city, interests in specs:
        g.add_user(u(uid, city=city, interests=interests))
    g.add_friend("alice", "bob")
    g.add_friend("alice", "dave")
    g.add_friend("bob", "carol")
    g.add_friend("bob", "eve")
    g.add_friend("dave", "frank")
    return g


@pytest.fixture()
def store(tmp_path):
    """In-memory SQLite store (tmp_path keeps tests isolated)."""
    return Store(":memory:")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Floyd-Warshall / distance matrix
# ─────────────────────────────────────────────────────────────────────────────


class TestFloydWarshall:
    def test_line_graph_distances(self, line5: FriendGraph):
        an = NetworkAnalytics(line5)
        D = an.floyd_warshall()
        ids = sorted(line5.user_ids())
        idx = {uid: i for i, uid in enumerate(ids)}
        # Nodes are "0","1","2","3","4" sorted → indices 0..4
        assert D[idx["0"], idx["4"]] == pytest.approx(4.0)
        assert D[idx["0"], idx["2"]] == pytest.approx(2.0)
        assert D[idx["1"], idx["3"]] == pytest.approx(2.0)

    def test_diagonal_is_zero(self, line5: FriendGraph):
        D = NetworkAnalytics(line5).floyd_warshall()
        assert np.all(np.diag(D) == 0.0)

    def test_direct_edges_are_one(self, triangle: FriendGraph):
        D = NetworkAnalytics(triangle).floyd_warshall()
        ids = sorted(triangle.user_ids())
        idx = {uid: i for i, uid in enumerate(ids)}
        assert D[idx["a"], idx["b"]] == pytest.approx(1.0)
        assert D[idx["b"], idx["c"]] == pytest.approx(1.0)

    def test_triangle_all_distances_one(self, triangle: FriendGraph):
        D = NetworkAnalytics(triangle).floyd_warshall()
        n = len(D)
        for i in range(n):
            for j in range(n):
                if i != j:
                    assert D[i, j] == pytest.approx(1.0)

    def test_matrix_is_symmetric(self, social: FriendGraph):
        D = NetworkAnalytics(social).floyd_warshall()
        assert np.allclose(D, D.T)

    def test_disconnected_pair_is_inf(self):
        g = FriendGraph()
        g.add_user(u("x"))
        g.add_user(u("y"))
        an = NetworkAnalytics(g)
        D = an.floyd_warshall()
        ids = sorted(g.user_ids())
        idx = {uid: i for i, uid in enumerate(ids)}
        assert math.isinf(D[idx["x"], idx["y"]])

    def test_empty_graph_returns_empty_matrix(self):
        g = FriendGraph()
        D = NetworkAnalytics(g).floyd_warshall()
        assert D.shape == (0, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Diameter & average separation
# ─────────────────────────────────────────────────────────────────────────────


class TestDiameterAndSeparation:
    def test_line5_diameter(self, line5: FriendGraph):
        assert NetworkAnalytics(line5).diameter() == pytest.approx(4.0)

    def test_triangle_diameter(self, triangle: FriendGraph):
        assert NetworkAnalytics(triangle).diameter() == pytest.approx(1.0)

    def test_single_user_diameter(self):
        g = FriendGraph()
        g.add_user(u("solo"))
        assert NetworkAnalytics(g).diameter() == pytest.approx(0.0)

    def test_empty_graph_diameter(self):
        assert NetworkAnalytics(FriendGraph()).diameter() == pytest.approx(0.0)

    def test_line5_avg_separation(self, line5: FriendGraph):
        # Hand-computed: sum of all pairwise distances / number of pairs
        # Pairs and distances for 0-1-2-3-4:
        # (0,1)=1 (0,2)=2 (0,3)=3 (0,4)=4
        # (1,2)=1 (1,3)=2 (1,4)=3
        # (2,3)=1 (2,4)=2
        # (3,4)=1
        # sum=20, pairs=10  →  avg=2.0
        assert NetworkAnalytics(line5).average_separation() == pytest.approx(2.0)

    def test_triangle_avg_separation(self, triangle: FriendGraph):
        # All 3 pairs have distance 1 → avg = 1.0
        assert NetworkAnalytics(triangle).average_separation() == pytest.approx(1.0)

    def test_disconnected_graph_avg_excludes_inf(self):
        g = FriendGraph()
        for uid in ["a", "b", "c", "x"]:
            g.add_user(u(uid))
        g.add_friend("a", "b")
        g.add_friend("b", "c")
        # x is isolated — inf pairs excluded from average
        avg = NetworkAnalytics(g).average_separation()
        assert 0 < avg < math.inf


# ─────────────────────────────────────────────────────────────────────────────
# 3. Density
# ─────────────────────────────────────────────────────────────────────────────


class TestDensity:
    def test_triangle_density_is_one(self, triangle: FriendGraph):
        # 3 nodes, 3 edges, max=3 → density=1.0
        assert NetworkAnalytics(triangle).density() == pytest.approx(1.0)

    def test_line5_density(self, line5: FriendGraph):
        # 5 nodes, 4 edges, max=10 → density=0.4
        assert NetworkAnalytics(line5).density() == pytest.approx(0.4)

    def test_empty_graph_density(self):
        assert NetworkAnalytics(FriendGraph()).density() == pytest.approx(0.0)

    def test_single_user_density(self):
        g = FriendGraph()
        g.add_user(u("solo"))
        assert NetworkAnalytics(g).density() == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. DataFrames
# ─────────────────────────────────────────────────────────────────────────────


class TestDataFrames:
    def test_users_df_columns(self, social: FriendGraph):
        import pandas as pd
        df = NetworkAnalytics(social).users_dataframe()
        assert set(df.columns) >= {"user_id", "name", "city", "degree"}

    def test_users_df_row_count(self, social: FriendGraph):
        df = NetworkAnalytics(social).users_dataframe()
        assert len(df) == 6

    def test_edges_df_columns(self, social: FriendGraph):
        df = NetworkAnalytics(social).edges_dataframe()
        assert set(df.columns) >= {"user_a", "user_b"}

    def test_edges_df_row_count(self, social: FriendGraph):
        df = NetworkAnalytics(social).edges_dataframe()
        assert len(df) == 5  # 5 unique edges

    def test_city_distribution(self, social: FriendGraph):
        cd = NetworkAnalytics(social).city_distribution()
        cities = set(cd["city"].tolist())
        assert "NYC" in cities and "LA" in cities
        nyc_count = cd.loc[cd["city"] == "NYC", "count"].values[0]
        la_count = cd.loc[cd["city"] == "LA", "count"].values[0]
        assert nyc_count == 4
        assert la_count == 2

    def test_most_connected_sorted(self, social: FriendGraph):
        mc = NetworkAnalytics(social).most_connected(top_n=3)
        assert mc["degree"].is_monotonic_decreasing

    def test_degree_stats_keys(self, social: FriendGraph):
        stats = NetworkAnalytics(social).degree_stats()
        assert {"mean", "median", "max", "min"} == set(stats.keys())

    def test_summary_keys(self, social: FriendGraph):
        s = NetworkAnalytics(social).summary()
        for key in ["total_users", "total_edges", "density",
                    "num_components", "diameter", "average_separation"]:
            assert key in s

    def test_friendship_growth_with_timestamps(self, social: FriendGraph):
        from datetime import timedelta
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ts = {}
        for i, uid in enumerate(sorted(social.user_ids())):
            for nid in social.neighbors(uid):
                key = (min(uid, nid), max(uid, nid))
                if key not in ts:
                    ts[key] = base + timedelta(days=i)
        an = NetworkAnalytics(social, timestamps=ts)
        growth = an.friendship_growth()
        assert not growth.empty
        assert "cumulative_edges" in growth.columns
        assert growth["cumulative_edges"].iloc[-1] == 5

    def test_top_influencers_returns_list(self, social: FriendGraph):
        inf_list = NetworkAnalytics(social).top_influencers(top_n=3)
        assert len(inf_list) <= 3
        assert "user_id" in inf_list[0]
        assert "degree" in inf_list[0]

    def test_top_influencers_sorted_by_degree(self, social: FriendGraph):
        inf_list = NetworkAnalytics(social).top_influencers(top_n=10)
        degrees = [x["degree"] for x in inf_list]
        assert degrees == sorted(degrees, reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Charts — headless PNG generation
# ─────────────────────────────────────────────────────────────────────────────


class TestCharts:
    def test_top_connected_is_valid_png(self, social: FriendGraph):
        mc = NetworkAnalytics(social).most_connected()
        b64 = chart_top_connected(mc)
        assert _is_valid_b64_png(b64)

    def test_city_distribution_is_valid_png(self, social: FriendGraph):
        cd = NetworkAnalytics(social).city_distribution()
        b64 = chart_city_distribution(cd)
        assert _is_valid_b64_png(b64)

    def test_degree_distribution_is_valid_png(self, social: FriendGraph):
        df = NetworkAnalytics(social).users_dataframe()
        b64 = chart_degree_distribution(df)
        assert _is_valid_b64_png(b64)

    def test_network_graph_is_valid_png(self, social: FriendGraph):
        nodes = [{"id": u.user_id, "name": u.name} for u in social.users()]
        edges = []
        seen = set()
        for uid in social.user_ids():
            for nid in social.neighbors(uid):
                key = (min(uid, nid), max(uid, nid))
                if key not in seen:
                    seen.add(key)
                    edges.append(key)
        b64 = chart_network_graph(nodes, edges)
        assert _is_valid_b64_png(b64)

    def test_network_graph_with_communities(self, social: FriendGraph):
        labels = detect_communities(social)
        nodes = [{"id": u.user_id, "name": u.name} for u in social.users()]
        edges = []
        seen = set()
        for uid in social.user_ids():
            for nid in social.neighbors(uid):
                key = (min(uid, nid), max(uid, nid))
                if key not in seen:
                    seen.add(key)
                    edges.append(key)
        b64 = chart_network_graph(nodes, edges, community_labels=labels)
        assert _is_valid_b64_png(b64)

    def test_friendship_growth_chart_valid_png(self, social: FriendGraph):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        ts = {}
        for i, uid in enumerate(sorted(social.user_ids())):
            for nid in social.neighbors(uid):
                key = (min(uid, nid), max(uid, nid))
                if key not in ts:
                    ts[key] = base + timedelta(days=i)
        an = NetworkAnalytics(social, timestamps=ts)
        b64 = chart_friendship_growth(an.friendship_growth())
        assert _is_valid_b64_png(b64)

    def test_empty_chart_is_valid_png(self):
        import pandas as pd
        b64 = chart_top_connected(pd.DataFrame())
        assert _is_valid_b64_png(b64)

    def test_empty_chart_helper(self):
        b64 = _empty_chart("test message")
        assert _is_valid_b64_png(b64)

    def test_charts_are_non_empty_strings(self, social: FriendGraph):
        mc = NetworkAnalytics(social).most_connected()
        b64 = chart_top_connected(mc)
        assert len(b64) > 100  # real image, not trivially small


# ─────────────────────────────────────────────────────────────────────────────
# 6. SQLite Store — unit operations
# ─────────────────────────────────────────────────────────────────────────────


class TestStoreOperations:
    def test_upsert_and_reload_user(self, store: Store):
        user = u("alice", city="NYC", interests={"music"})
        store.upsert_user(user)
        g, _, _ = store.load_state()
        assert g.has_user("alice")
        assert g.get_user("alice").name == "Alice"
        assert g.get_user("alice").interests == {"music"}

    def test_upsert_updates_existing_user(self, store: Store):
        user = u("alice", city="NYC")
        store.upsert_user(user)
        user2 = User(name="Alice Updated", age=30, city="LA", user_id="alice")
        store.upsert_user(user2)
        g, _, _ = store.load_state()
        assert g.get_user("alice").name == "Alice Updated"
        assert g.get_user("alice").city == "LA"

    def test_delete_user(self, store: Store):
        store.upsert_user(u("alice"))
        store.delete_user("alice")
        g, _, _ = store.load_state()
        assert not g.has_user("alice")

    def test_upsert_friendship(self, store: Store):
        store.upsert_user(u("alice"))
        store.upsert_user(u("bob"))
        store.upsert_friendship("alice", "bob")
        g, _, _ = store.load_state()
        assert g.are_friends("alice", "bob")

    def test_upsert_friendship_canonical_order(self, store: Store):
        """Friendship (b,a) and (a,b) should not create duplicate rows."""
        store.upsert_user(u("alice"))
        store.upsert_user(u("bob"))
        store.upsert_friendship("bob", "alice")
        store.upsert_friendship("alice", "bob")  # duplicate — should be ignored
        g, _, _ = store.load_state()
        assert g.edge_count() == 1

    def test_delete_friendship(self, store: Store):
        store.upsert_user(u("alice"))
        store.upsert_user(u("bob"))
        store.upsert_friendship("alice", "bob")
        store.delete_friendship("alice", "bob")
        g, _, _ = store.load_state()
        assert not g.are_friends("alice", "bob")

    def test_upsert_request(self, store: Store):
        store.upsert_user(u("alice"))
        store.upsert_user(u("bob"))
        store.upsert_request("alice", "bob", status="PENDING")
        g, mgr, _ = store.load_state()
        pending = mgr.pending_for("bob")
        assert len(pending) == 1
        assert pending[0].from_id == "alice"

    def test_clear_all(self, store: Store):
        store.upsert_user(u("alice"))
        store.clear_all()
        g, _, _ = store.load_state()
        assert len(g) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. save_state / load_state round-trips
# ─────────────────────────────────────────────────────────────────────────────


class TestSaveLoadState:
    def test_users_survive_round_trip(self, social: FriendGraph, store: Store):
        mgr = FriendRequestManager(social)
        store.save_state(social, mgr)
        g2, _, _ = store.load_state()
        assert g2.user_ids() == social.user_ids()

    def test_friendships_survive_round_trip(self, social: FriendGraph, store: Store):
        mgr = FriendRequestManager(social)
        store.save_state(social, mgr)
        g2, _, _ = store.load_state()
        assert g2.edge_count() == social.edge_count()
        assert g2.are_friends("alice", "bob")
        assert g2.are_friends("bob", "carol")

    def test_bidirectionality_preserved(self, social: FriendGraph, store: Store):
        mgr = FriendRequestManager(social)
        store.save_state(social, mgr)
        g2, _, _ = store.load_state()
        for uid in social.user_ids():
            for nid in social.neighbors(uid):
                assert g2.are_friends(uid, nid)
                assert g2.are_friends(nid, uid)

    def test_user_profile_data_preserved(self, social: FriendGraph, store: Store):
        mgr = FriendRequestManager(social)
        store.save_state(social, mgr)
        g2, _, _ = store.load_state()
        alice = g2.get_user("alice")
        assert alice.name == "Alice"
        assert alice.city == "NYC"
        assert alice.interests == {"music", "hiking"}

    def test_pending_requests_survive_round_trip(self, social: FriendGraph, store: Store):
        mgr = FriendRequestManager(social)
        # carol → alice (not yet friends)
        mgr.send_request("carol", "alice")
        store.save_state(social, mgr)
        g2, mgr2, _ = store.load_state()
        pending = mgr2.pending_for("alice")
        assert len(pending) == 1
        assert pending[0].from_id == "carol"

    def test_timestamps_survive_round_trip(self, social: FriendGraph, store: Store):
        base = datetime(2024, 6, 1, tzinfo=timezone.utc)
        ts = {}
        for i, uid in enumerate(sorted(social.user_ids())):
            for nid in social.neighbors(uid):
                key = (min(uid, nid), max(uid, nid))
                if key not in ts:
                    ts[key] = base + timedelta(days=i)
        mgr = FriendRequestManager(social)
        store.save_state(social, mgr, timestamps=ts)
        _, _, loaded_ts = store.load_state()
        assert len(loaded_ts) == social.edge_count()

    def test_empty_graph_round_trip(self, store: Store):
        g = FriendGraph()
        mgr = FriendRequestManager(g)
        store.save_state(g, mgr)
        g2, mgr2, _ = store.load_state()
        assert len(g2) == 0
        assert mgr2.total_pending() == 0

    def test_multiple_saves_are_idempotent(self, social: FriendGraph, store: Store):
        mgr = FriendRequestManager(social)
        store.save_state(social, mgr)
        store.save_state(social, mgr)
        g2, _, _ = store.load_state()
        assert g2.edge_count() == social.edge_count()

    def test_load_after_adding_user(self, store: Store):
        g = FriendGraph()
        g.add_user(u("alice"))
        mgr = FriendRequestManager(g)
        store.save_state(g, mgr)

        g.add_user(u("bob"))
        g.add_friend("alice", "bob")
        store.save_state(g, mgr)

        g2, _, _ = store.load_state()
        assert g2.has_user("bob")
        assert g2.are_friends("alice", "bob")
