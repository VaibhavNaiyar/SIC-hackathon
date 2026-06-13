"""Phase 3 test suite — Algorithms Layer.

Covers the Phase 3 acceptance criteria:
  ✓ BFS path is provably shortest on a known fixture graph
  ✓ BFS returns None for disconnected pairs
  ✓ BFS reconstructs correct parent chain (no shortcuts)
  ✓ Backtracking returns ALL simple paths, never revisits a node within a path
  ✓ Recommendations exclude current friends and are sorted by score descending
  ✓ Recommendation explanations are accurate (mutuals, interests, city)
  ✓ Mutual friends = set intersection
  ✓ Jaccard similarity in [0, 1]
  ✓ Union-Find / community detection labels connected components correctly
"""

from __future__ import annotations

import pytest

from app.errors import UserNotFoundError
from app.models.graph import FriendGraph
from app.models.user import User
from app.services.analytics import UnionFind, connected_components, detect_communities
from app.services.pathfinder import PathResult, all_simple_paths, shortest_path
from app.services.recommender import (
    RecommendationEngine,
    jaccard_similarity,
    mutual_friends,
)


# ── Fixture helpers ────────────────────────────────────────────────────────────


def u(uid: str, *, city: str = "NYC", interests: set[str] | None = None) -> User:
    return User(
        name=uid.capitalize(),
        age=25,
        city=city,
        interests=interests or set(),
        user_id=uid,
    )


def make_line_graph(n: int) -> FriendGraph:
    """Build a line graph: 0 — 1 — 2 — … — (n-1)."""
    g = FriendGraph()
    for i in range(n):
        g.add_user(u(str(i)))
    for i in range(n - 1):
        g.add_friend(str(i), str(i + 1))
    return g


@pytest.fixture()
def diamond() -> FriendGraph:
    """Diamond graph:
         a
        / \\
       b   c
        \\ /
         d
    shortest a→d = 2 hops (via b or via c)
    """
    g = FriendGraph()
    for uid in ["a", "b", "c", "d"]:
        g.add_user(u(uid))
    g.add_friend("a", "b")
    g.add_friend("a", "c")
    g.add_friend("b", "d")
    g.add_friend("c", "d")
    return g


@pytest.fixture()
def two_components() -> FriendGraph:
    """Two disconnected triangles: {p,q,r} and {x,y,z}."""
    g = FriendGraph()
    for uid in ["p", "q", "r", "x", "y", "z"]:
        g.add_user(u(uid))
    g.add_friend("p", "q")
    g.add_friend("q", "r")
    g.add_friend("p", "r")
    g.add_friend("x", "y")
    g.add_friend("y", "z")
    g.add_friend("x", "z")
    return g


@pytest.fixture()
def social() -> FriendGraph:
    """Social graph for recommendation tests.

    Layout:
        alice — bob — carol
          |         \\
        dave         eve
          |
        frank

    Users are in NYC except carol (LA) and eve (LA).
    Interests:
        alice: {music, hiking}
        bob:   {music, gaming}
        carol: {gaming, cooking}
        dave:  {hiking, cooking}
        eve:   {music, gaming}
        frank: {hiking, music}
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# 1. BFS shortest path
# ─────────────────────────────────────────────────────────────────────────────


class TestShortestPath:
    def test_direct_friends_one_hop(self, diamond: FriendGraph):
        r = shortest_path(diamond, "a", "b")
        assert r.path == ["a", "b"]
        assert r.hops == 1

    def test_shortest_two_hops_diamond(self, diamond: FriendGraph):
        """BFS must return a 2-hop path, not the longer route."""
        r = shortest_path(diamond, "a", "d")
        assert r.hops == 2
        assert r.path[0] == "a"
        assert r.path[-1] == "d"
        assert len(r.path) == 3

    def test_shortest_path_on_line_graph(self):
        """Line graph 0-1-2-3-4: shortest 0→4 should be 4 hops."""
        g = make_line_graph(5)
        r = shortest_path(g, "0", "4")
        assert r.hops == 4
        assert r.path == ["0", "1", "2", "3", "4"]

    def test_path_to_self_is_zero_hops(self, diamond: FriendGraph):
        r = shortest_path(diamond, "a", "a")
        assert r.path == ["a"]
        assert r.hops == 0

    def test_disconnected_returns_none(self, two_components: FriendGraph):
        r = shortest_path(two_components, "p", "x")
        assert r.path is None
        assert r.hops == -1
        assert r.connected is False

    def test_degrees_label_one_hop(self, diamond: FriendGraph):
        r = shortest_path(diamond, "a", "b")
        assert r.degrees == "1 degree of separation"

    def test_degrees_label_two_hops(self, diamond: FriendGraph):
        r = shortest_path(diamond, "a", "d")
        assert "2 degrees" in r.degrees

    def test_degrees_label_disconnected(self, two_components: FriendGraph):
        r = shortest_path(two_components, "p", "x")
        assert r.degrees == "Not connected"

    def test_path_nodes_are_all_valid_users(self, diamond: FriendGraph):
        r = shortest_path(diamond, "a", "d")
        for uid in r.path:
            assert diamond.has_user(uid)

    def test_path_nodes_form_valid_edges(self, diamond: FriendGraph):
        """Each consecutive pair in the path must be friends."""
        r = shortest_path(diamond, "a", "d")
        for i in range(len(r.path) - 1):
            assert diamond.are_friends(r.path[i], r.path[i + 1])

    def test_missing_source_raises(self, diamond: FriendGraph):
        with pytest.raises(UserNotFoundError):
            shortest_path(diamond, "ghost", "a")

    def test_missing_target_raises(self, diamond: FriendGraph):
        with pytest.raises(UserNotFoundError):
            shortest_path(diamond, "a", "ghost")

    def test_to_dict(self, diamond: FriendGraph):
        d = shortest_path(diamond, "a", "b").to_dict()
        assert d["hops"] == 1
        assert d["connected"] is True
        assert "path" in d

    def test_larger_graph_correct_length(self):
        """Star graph: centre connected to 10 leaves, each leaf distance 2 from others."""
        g = FriendGraph()
        g.add_user(u("centre"))
        for i in range(10):
            g.add_user(u(f"leaf{i}"))
            g.add_friend("centre", f"leaf{i}")
        r = shortest_path(g, "leaf0", "leaf9")
        assert r.hops == 2
        assert r.path == ["leaf0", "centre", "leaf9"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. DFS + backtracking — all simple paths
# ─────────────────────────────────────────────────────────────────────────────


class TestAllSimplePaths:
    def test_returns_list(self, diamond: FriendGraph):
        paths = all_simple_paths(diamond, "a", "d")
        assert isinstance(paths, list)

    def test_diamond_two_paths(self, diamond: FriendGraph):
        """Diamond has exactly 2 simple paths a→d: via b and via c."""
        paths = all_simple_paths(diamond, "a", "d")
        assert len(paths) == 2
        path_sets = [tuple(p) for p in paths]
        assert ("a", "b", "d") in path_sets
        assert ("a", "c", "d") in path_sets

    def test_all_paths_start_and_end_correctly(self, diamond: FriendGraph):
        for path in all_simple_paths(diamond, "a", "d"):
            assert path[0] == "a"
            assert path[-1] == "d"

    def test_no_repeated_nodes_within_path(self, diamond: FriendGraph):
        for path in all_simple_paths(diamond, "a", "d"):
            assert len(path) == len(set(path)), f"Repeated node in path: {path}"

    def test_path_to_self_returns_single_element_path(self, diamond: FriendGraph):
        paths = all_simple_paths(diamond, "a", "a")
        assert paths == [["a"]]

    def test_disconnected_returns_empty(self, two_components: FriendGraph):
        paths = all_simple_paths(two_components, "p", "x")
        assert paths == []

    def test_max_depth_prunes_long_paths(self):
        """Line graph 0-1-2-3-4: max_depth=2 should find no path from 0 to 4."""
        g = make_line_graph(5)
        paths = all_simple_paths(g, "0", "4", max_depth=2)
        assert paths == []

    def test_max_depth_allows_short_paths(self):
        g = make_line_graph(5)
        paths = all_simple_paths(g, "0", "2", max_depth=2)
        assert [["0", "1", "2"]] == paths

    def test_every_path_uses_valid_edges(self, diamond: FriendGraph):
        for path in all_simple_paths(diamond, "a", "d"):
            for i in range(len(path) - 1):
                assert diamond.are_friends(path[i], path[i + 1])

    def test_missing_source_raises(self, diamond: FriendGraph):
        with pytest.raises(UserNotFoundError):
            all_simple_paths(diamond, "ghost", "a")

    def test_missing_target_raises(self, diamond: FriendGraph):
        with pytest.raises(UserNotFoundError):
            all_simple_paths(diamond, "a", "ghost")

    def test_triangle_three_paths_not_found_at_depth_1(self):
        """Triangle a-b-c: only 1-hop paths at max_depth=1."""
        g = FriendGraph()
        for uid in ["a", "b", "c"]:
            g.add_user(u(uid))
        g.add_friend("a", "b")
        g.add_friend("b", "c")
        g.add_friend("a", "c")
        paths_d1 = all_simple_paths(g, "a", "c", max_depth=1)
        assert paths_d1 == [["a", "c"]]
        paths_d2 = all_simple_paths(g, "a", "c", max_depth=2)
        assert len(paths_d2) == 2  # a→c and a→b→c


# ─────────────────────────────────────────────────────────────────────────────
# 3. Mutual friends
# ─────────────────────────────────────────────────────────────────────────────


class TestMutualFriends:
    def test_direct_mutual(self, social: FriendGraph):
        # alice friends: bob, dave
        # carol friends: bob, eve
        # mutual(alice, carol) = {bob}
        m = mutual_friends(social, "alice", "carol")
        assert m == {"bob"}

    def test_no_mutuals(self, social: FriendGraph):
        # frank friends: dave
        # carol friends: bob, eve
        # no overlap
        m = mutual_friends(social, "frank", "carol")
        assert m == set()

    def test_mutual_is_symmetric(self, social: FriendGraph):
        assert mutual_friends(social, "alice", "carol") == mutual_friends(
            social, "carol", "alice"
        )

    def test_mutual_with_self_returns_own_friends(self, social: FriendGraph):
        # mutual(alice, alice) = friends(alice) ∩ friends(alice) = friends(alice)
        m = mutual_friends(social, "alice", "alice")
        assert m == social.get_friends("alice")

    def test_missing_user_raises(self, social: FriendGraph):
        with pytest.raises(UserNotFoundError):
            mutual_friends(social, "ghost", "alice")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Jaccard similarity
# ─────────────────────────────────────────────────────────────────────────────


class TestJaccardSimilarity:
    def test_identical_friend_sets(self):
        g = FriendGraph()
        for uid in ["a", "b", "c", "d"]:
            g.add_user(u(uid))
        g.add_friend("a", "c")
        g.add_friend("a", "d")
        g.add_friend("b", "c")
        g.add_friend("b", "d")
        j = jaccard_similarity(g, "a", "b")
        assert j == pytest.approx(1.0)

    def test_no_overlap(self, two_components: FriendGraph):
        # p's friends: {q, r}, x's friends: {y, z} — no overlap
        j = jaccard_similarity(two_components, "p", "x")
        assert j == pytest.approx(0.0)

    def test_partial_overlap(self, social: FriendGraph):
        # alice friends: {bob, dave}
        # carol friends: {bob}   (only edge: bob-carol)
        # intersection={bob}=1, union={bob,dave}=2 → 1/2
        j = jaccard_similarity(social, "alice", "carol")
        assert j == pytest.approx(1 / 2)

    def test_range_zero_to_one(self, social: FriendGraph):
        ids = list(social.user_ids())
        for a in ids:
            for b in ids:
                j = jaccard_similarity(social, a, b)
                assert 0.0 <= j <= 1.0

    def test_both_isolated_returns_zero(self):
        g = FriendGraph()
        g.add_user(u("x"))
        g.add_user(u("y"))
        assert jaccard_similarity(g, "x", "y") == pytest.approx(0.0)

    def test_missing_user_raises(self, social: FriendGraph):
        with pytest.raises(UserNotFoundError):
            jaccard_similarity(social, "ghost", "alice")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Friend recommendations
# ─────────────────────────────────────────────────────────────────────────────


class TestRecommendationEngine:
    def test_recommendations_exclude_existing_friends(self, social: FriendGraph):
        engine = RecommendationEngine(social)
        recs = engine.recommend("alice")
        existing = social.get_friends("alice")
        rec_ids = {r.candidate_id for r in recs}
        assert rec_ids.isdisjoint(existing)

    def test_recommendations_exclude_self(self, social: FriendGraph):
        engine = RecommendationEngine(social)
        recs = engine.recommend("alice")
        assert all(r.candidate_id != "alice" for r in recs)

    def test_recommendations_sorted_by_score_descending(self, social: FriendGraph):
        engine = RecommendationEngine(social)
        recs = engine.recommend("alice")
        scores = [r.why.score for r in recs]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_respected(self, social: FriendGraph):
        engine = RecommendationEngine(social)
        recs = engine.recommend("alice", top_k=2)
        assert len(recs) <= 2

    def test_explanation_mutuals_accurate(self, social: FriendGraph):
        """alice → carol recommendation should cite bob as mutual."""
        engine = RecommendationEngine(social)
        recs = engine.recommend("alice")
        carol_rec = next((r for r in recs if r.candidate_id == "carol"), None)
        assert carol_rec is not None
        assert "bob" in carol_rec.why.mutuals

    def test_explanation_shared_interests_accurate(self, social: FriendGraph):
        """alice {music,hiking} and frank {hiking,music} share both interests."""
        engine = RecommendationEngine(social)
        recs = engine.recommend("alice")
        frank_rec = next((r for r in recs if r.candidate_id == "frank"), None)
        assert frank_rec is not None
        assert set(frank_rec.why.shared_interests) == {"music", "hiking"}

    def test_explanation_same_city_flag(self, social: FriendGraph):
        engine = RecommendationEngine(social)
        recs = engine.recommend("alice")
        frank_rec = next((r for r in recs if r.candidate_id == "frank"), None)
        carol_rec = next((r for r in recs if r.candidate_id == "carol"), None)
        assert frank_rec is not None and frank_rec.why.same_city is True   # NYC==NYC
        assert carol_rec is not None and carol_rec.why.same_city is False  # NYC≠LA

    def test_isolated_user_gets_no_recommendations(self):
        g = FriendGraph()
        g.add_user(u("lone"))
        engine = RecommendationEngine(g)
        assert engine.recommend("lone") == []

    def test_missing_user_raises(self, social: FriendGraph):
        with pytest.raises(UserNotFoundError):
            RecommendationEngine(social).recommend("ghost")

    def test_to_dict_shape(self, social: FriendGraph):
        engine = RecommendationEngine(social)
        recs = engine.recommend("alice", top_k=1)
        d = recs[0].to_dict()
        assert "candidate_id" in d
        assert "why" in d
        assert "mutuals" in d["why"]
        assert "shared_interests" in d["why"]
        assert "same_city" in d["why"]
        assert "score" in d["why"]

    def test_score_increases_with_more_mutuals(self):
        """Manually construct a graph where we know exact scores."""
        g = FriendGraph()
        # target user
        g.add_user(u("target", city="NYC", interests={"a"}))
        # shared_friend — shares 2 mutuals with candidate
        g.add_user(u("m1", city="NYC"))
        g.add_user(u("m2", city="NYC"))
        # candidate_a: 2 mutuals, no interests, same city
        g.add_user(u("cand_a", city="NYC", interests=set()))
        # candidate_b: 0 mutuals, no interests, same city
        g.add_user(u("cand_b", city="NYC", interests=set()))

        g.add_friend("target", "m1")
        g.add_friend("target", "m2")
        g.add_friend("m1", "cand_a")
        g.add_friend("m2", "cand_a")
        g.add_friend("m1", "cand_b")  # only 1 mutual

        engine = RecommendationEngine(g)
        recs = engine.recommend("target", top_k=5)
        ids = [r.candidate_id for r in recs]
        # cand_a has 2 mutuals so should rank above cand_b (1 mutual)
        assert ids.index("cand_a") < ids.index("cand_b")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Union-Find
# ─────────────────────────────────────────────────────────────────────────────


class TestUnionFind:
    def test_all_singletons_initially(self):
        uf = UnionFind(["a", "b", "c"])
        assert not uf.connected("a", "b")
        assert not uf.connected("b", "c")

    def test_union_connects(self):
        uf = UnionFind(["a", "b", "c"])
        uf.union("a", "b")
        assert uf.connected("a", "b")
        assert not uf.connected("a", "c")

    def test_transitivity(self):
        uf = UnionFind(["a", "b", "c"])
        uf.union("a", "b")
        uf.union("b", "c")
        assert uf.connected("a", "c")

    def test_union_returns_false_if_same_set(self):
        uf = UnionFind(["a", "b"])
        uf.union("a", "b")
        assert uf.union("a", "b") is False

    def test_union_returns_true_if_merged(self):
        uf = UnionFind(["a", "b"])
        assert uf.union("a", "b") is True

    def test_path_compression(self):
        """After find(), every node should point directly to the root."""
        uf = UnionFind(["a", "b", "c", "d"])
        uf.union("a", "b")
        uf.union("b", "c")
        uf.union("c", "d")
        root = uf.find("d")
        # After path compression all parents should point to root
        for node in ["a", "b", "c", "d"]:
            uf.find(node)
        assert uf._parent["d"] == root  # compressed

    def test_component_size(self):
        uf = UnionFind(["a", "b", "c", "d"])
        uf.union("a", "b")
        uf.union("a", "c")
        assert uf.component_size("a") == 3
        assert uf.component_size("d") == 1

    def test_components_dict(self):
        uf = UnionFind(["a", "b", "c", "x", "y"])
        uf.union("a", "b")
        uf.union("b", "c")
        uf.union("x", "y")
        comps = uf.components()
        sizes = sorted(len(v) for v in comps.values())
        assert sizes == [2, 3]


# ─────────────────────────────────────────────────────────────────────────────
# 7. Community detection on graph
# ─────────────────────────────────────────────────────────────────────────────


class TestCommunityDetection:
    def test_empty_graph(self):
        g = FriendGraph()
        assert detect_communities(g) == {}
        assert connected_components(g) == []

    def test_single_user(self):
        g = FriendGraph()
        g.add_user(u("solo"))
        labels = detect_communities(g)
        assert labels == {"solo": 0}
        comps = connected_components(g)
        assert comps == [["solo"]]

    def test_two_components(self, two_components: FriendGraph):
        labels = detect_communities(two_components)
        # p, q, r should share one label; x, y, z another
        assert labels["p"] == labels["q"] == labels["r"]
        assert labels["x"] == labels["y"] == labels["z"]
        assert labels["p"] != labels["x"]

    def test_fully_connected_one_component(self, diamond: FriendGraph):
        labels = detect_communities(diamond)
        assert len(set(labels.values())) == 1

    def test_connected_components_sorted_by_size(self, two_components: FriendGraph):
        comps = connected_components(two_components)
        assert len(comps) == 2
        assert len(comps[0]) >= len(comps[1])

    def test_connected_components_cover_all_users(self, social: FriendGraph):
        comps = connected_components(social)
        all_ids = {uid for comp in comps for uid in comp}
        assert all_ids == social.user_ids()

    def test_isolated_users_each_own_component(self):
        g = FriendGraph()
        g.add_user(u("a"))
        g.add_user(u("b"))
        g.add_user(u("c"))
        labels = detect_communities(g)
        # all different labels (3 singletons)
        assert len(set(labels.values())) == 3

    def test_adding_edge_merges_components(self):
        g = FriendGraph()
        g.add_user(u("a"))
        g.add_user(u("b"))
        labels_before = detect_communities(g)
        assert len(set(labels_before.values())) == 2

        g.add_friend("a", "b")
        labels_after = detect_communities(g)
        assert len(set(labels_after.values())) == 1
