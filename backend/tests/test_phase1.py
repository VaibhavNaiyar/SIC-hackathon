"""Phase 1 test suite — User model + FriendGraph.

Covers the Phase 1 acceptance criteria:
  ✓ add/remove user
  ✓ add/remove friend (both directions update)
  ✓ self-edge rejection
  ✓ missing-node rejection
  ✓ duplicate friendship is idempotent (raises AlreadyFriendsError, not silent)
  ✓ serialisation round-trip (to_dict / from_dict)
  ✓ validation guards
"""

from __future__ import annotations

import pytest

from app.errors import (
    AlreadyFriendsError,
    DuplicateUserError,
    InvalidUserDataError,
    NotFriendsError,
    SelfFriendshipError,
    UserNotFoundError,
)
from app.models.graph import FriendGraph
from app.models.user import User


# ── Fixtures ───────────────────────────────────────────────────────────────────


def make_user(uid: str, name: str = "Test", age: int = 20, city: str = "NYC") -> User:
    """Helper that builds a User with a deterministic ID."""
    return User(name=name, age=age, city=city, user_id=uid)


@pytest.fixture()
def graph() -> FriendGraph:
    """Fresh empty graph for each test."""
    return FriendGraph()


@pytest.fixture()
def populated_graph() -> FriendGraph:
    """Graph pre-loaded with 4 users and 3 friendship edges:
       alice — bob — carol — dave
    """
    g = FriendGraph()
    for uid, name in [("alice", "Alice"), ("bob", "Bob"),
                      ("carol", "Carol"), ("dave", "Dave")]:
        g.add_user(make_user(uid, name))
    g.add_friend("alice", "bob")
    g.add_friend("bob", "carol")
    g.add_friend("carol", "dave")
    return g


# ─────────────────────────────────────────────────────────────────────────────
# 1. User model
# ─────────────────────────────────────────────────────────────────────────────


class TestUserModel:
    def test_basic_construction(self):
        u = User(name="Alice", age=25, city="London", user_id="u1")
        assert u.name == "Alice"
        assert u.age == 25
        assert u.city == "London"
        assert u.user_id == "u1"

    def test_auto_generated_id(self):
        u1 = User(name="Alice", age=25, city="London")
        u2 = User(name="Bob", age=30, city="Paris")
        assert u1.user_id != u2.user_id  # UUIDs must be unique

    def test_interests_normalised_to_lowercase(self):
        u = User(name="Alice", age=25, city="NYC", interests={"Gaming", "HIKING"})
        assert u.interests == {"gaming", "hiking"}

    def test_name_stripped(self):
        u = User(name="  Alice  ", age=25, city="NYC")
        assert u.name == "Alice"

    def test_city_stripped(self):
        u = User(name="Alice", age=25, city="  NYC  ")
        assert u.city == "NYC"

    def test_empty_name_raises(self):
        with pytest.raises(InvalidUserDataError):
            User(name="", age=25, city="NYC")

    def test_whitespace_only_name_raises(self):
        with pytest.raises(InvalidUserDataError):
            User(name="   ", age=25, city="NYC")

    def test_age_below_13_raises(self):
        with pytest.raises(InvalidUserDataError):
            User(name="Kid", age=12, city="NYC")

    def test_age_exactly_13_is_valid(self):
        u = User(name="Teen", age=13, city="NYC")
        assert u.age == 13

    def test_empty_city_raises(self):
        with pytest.raises(InvalidUserDataError):
            User(name="Alice", age=25, city="")

    def test_to_dict_round_trip(self):
        u = User(
            name="Alice",
            age=25,
            city="London",
            interests={"reading", "coding"},
            user_id="abc-123",
        )
        d = u.to_dict()
        assert d["user_id"] == "abc-123"
        assert d["name"] == "Alice"
        assert d["age"] == 25
        assert d["city"] == "London"
        assert set(d["interests"]) == {"reading", "coding"}

        restored = User.from_dict(d)
        assert restored.user_id == u.user_id
        assert restored.name == u.name
        assert restored.interests == u.interests

    def test_equality_by_id(self):
        u1 = User(name="Alice", age=25, city="NYC", user_id="same")
        u2 = User(name="Bob",   age=30, city="LA",  user_id="same")
        assert u1 == u2  # same ID → equal

    def test_inequality_different_ids(self):
        u1 = User(name="Alice", age=25, city="NYC", user_id="x")
        u2 = User(name="Alice", age=25, city="NYC", user_id="y")
        assert u1 != u2

    def test_hashable_for_set_membership(self):
        u1 = User(name="Alice", age=25, city="NYC", user_id="x")
        u2 = User(name="Alice", age=25, city="NYC", user_id="x")
        assert len({u1, u2}) == 1  # de-duplicated by hash


# ─────────────────────────────────────────────────────────────────────────────
# 2. FriendGraph — user management
# ─────────────────────────────────────────────────────────────────────────────


class TestFriendGraphUsers:
    def test_add_user_increases_len(self, graph: FriendGraph):
        assert len(graph) == 0
        graph.add_user(make_user("u1"))
        assert len(graph) == 1

    def test_add_multiple_users(self, graph: FriendGraph):
        graph.add_user(make_user("u1"))
        graph.add_user(make_user("u2"))
        graph.add_user(make_user("u3"))
        assert len(graph) == 3

    def test_duplicate_user_raises(self, graph: FriendGraph):
        graph.add_user(make_user("u1"))
        with pytest.raises(DuplicateUserError) as exc_info:
            graph.add_user(make_user("u1"))
        assert exc_info.value.user_id == "u1"

    def test_has_user(self, graph: FriendGraph):
        graph.add_user(make_user("u1"))
        assert graph.has_user("u1")
        assert not graph.has_user("u2")

    def test_contains_operator(self, graph: FriendGraph):
        graph.add_user(make_user("u1"))
        assert "u1" in graph
        assert "u2" not in graph

    def test_get_user_returns_correct_object(self, graph: FriendGraph):
        u = make_user("u1", name="Alice")
        graph.add_user(u)
        assert graph.get_user("u1") is u

    def test_get_user_missing_raises(self, graph: FriendGraph):
        with pytest.raises(UserNotFoundError) as exc_info:
            graph.get_user("ghost")
        assert exc_info.value.user_id == "ghost"

    def test_remove_user_decreases_len(self, graph: FriendGraph):
        graph.add_user(make_user("u1"))
        graph.remove_user("u1")
        assert len(graph) == 0

    def test_remove_user_missing_raises(self, graph: FriendGraph):
        with pytest.raises(UserNotFoundError):
            graph.remove_user("ghost")

    def test_remove_user_also_removes_edges(self, populated_graph: FriendGraph):
        # bob is friends with alice and carol
        assert populated_graph.are_friends("alice", "bob")
        populated_graph.remove_user("bob")
        # alice should no longer list bob as a friend
        assert "bob" not in populated_graph.get_friends("alice")
        assert "bob" not in populated_graph.get_friends("carol")

    def test_users_iterator_yields_all(self, populated_graph: FriendGraph):
        ids = {u.user_id for u in populated_graph.users()}
        assert ids == {"alice", "bob", "carol", "dave"}

    def test_user_ids(self, populated_graph: FriendGraph):
        assert populated_graph.user_ids() == {"alice", "bob", "carol", "dave"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. FriendGraph — friendship / edge management
# ─────────────────────────────────────────────────────────────────────────────


class TestFriendGraphEdges:
    def test_add_friend_creates_bidirectional_edge(self, graph: FriendGraph):
        graph.add_user(make_user("a"))
        graph.add_user(make_user("b"))
        graph.add_friend("a", "b")
        # Both directions must exist
        assert "b" in graph.get_friends("a")
        assert "a" in graph.get_friends("b")

    def test_are_friends_true_after_add(self, graph: FriendGraph):
        graph.add_user(make_user("a"))
        graph.add_user(make_user("b"))
        graph.add_friend("a", "b")
        assert graph.are_friends("a", "b")
        assert graph.are_friends("b", "a")  # symmetric

    def test_are_friends_false_before_add(self, graph: FriendGraph):
        graph.add_user(make_user("a"))
        graph.add_user(make_user("b"))
        assert not graph.are_friends("a", "b")

    def test_self_friendship_raises(self, graph: FriendGraph):
        graph.add_user(make_user("a"))
        with pytest.raises(SelfFriendshipError) as exc_info:
            graph.add_friend("a", "a")
        assert exc_info.value.user_id == "a"

    def test_add_friend_missing_user_a_raises(self, graph: FriendGraph):
        graph.add_user(make_user("b"))
        with pytest.raises(UserNotFoundError):
            graph.add_friend("ghost", "b")

    def test_add_friend_missing_user_b_raises(self, graph: FriendGraph):
        graph.add_user(make_user("a"))
        with pytest.raises(UserNotFoundError):
            graph.add_friend("a", "ghost")

    def test_duplicate_friendship_raises_already_friends(self, graph: FriendGraph):
        """Adding the same friendship twice must raise AlreadyFriendsError — idempotent check."""
        graph.add_user(make_user("a"))
        graph.add_user(make_user("b"))
        graph.add_friend("a", "b")
        with pytest.raises(AlreadyFriendsError) as exc_info:
            graph.add_friend("a", "b")  # second call
        # Graph state is unchanged
        assert exc_info.value.a == "a"
        assert exc_info.value.b == "b"

    def test_duplicate_friendship_reversed_also_raises(self, graph: FriendGraph):
        """Adding (b, a) when (a, b) exists must also raise AlreadyFriendsError."""
        graph.add_user(make_user("a"))
        graph.add_user(make_user("b"))
        graph.add_friend("a", "b")
        with pytest.raises(AlreadyFriendsError):
            graph.add_friend("b", "a")

    def test_remove_friend_removes_both_directions(self, graph: FriendGraph):
        graph.add_user(make_user("a"))
        graph.add_user(make_user("b"))
        graph.add_friend("a", "b")
        graph.remove_friend("a", "b")
        assert not graph.are_friends("a", "b")
        assert not graph.are_friends("b", "a")

    def test_remove_friend_missing_edge_raises(self, graph: FriendGraph):
        graph.add_user(make_user("a"))
        graph.add_user(make_user("b"))
        with pytest.raises(NotFriendsError):
            graph.remove_friend("a", "b")

    def test_remove_friend_self_raises(self, graph: FriendGraph):
        graph.add_user(make_user("a"))
        with pytest.raises(SelfFriendshipError):
            graph.remove_friend("a", "a")

    def test_get_friends_returns_copy(self, graph: FriendGraph):
        """Mutating the returned set must not affect the graph's internal state."""
        graph.add_user(make_user("a"))
        graph.add_user(make_user("b"))
        graph.add_friend("a", "b")
        friends = graph.get_friends("a")
        friends.add("hacked")
        assert "hacked" not in graph.get_friends("a")

    def test_neighbors_alias(self, graph: FriendGraph):
        graph.add_user(make_user("a"))
        graph.add_user(make_user("b"))
        graph.add_friend("a", "b")
        assert graph.neighbors("a") == graph.get_friends("a")

    def test_edge_count(self, populated_graph: FriendGraph):
        # alice-bob, bob-carol, carol-dave = 3 edges
        assert populated_graph.edge_count() == 3

    def test_edge_count_empty(self, graph: FriendGraph):
        assert graph.edge_count() == 0

    def test_degree(self, populated_graph: FriendGraph):
        # bob is connected to alice and carol → degree 2
        assert populated_graph.degree("bob") == 2
        # alice is only connected to bob → degree 1
        assert populated_graph.degree("alice") == 1

    def test_degree_missing_user_raises(self, graph: FriendGraph):
        with pytest.raises(UserNotFoundError):
            graph.degree("ghost")


# ─────────────────────────────────────────────────────────────────────────────
# 4. FriendGraph — adjacency list integrity
# ─────────────────────────────────────────────────────────────────────────────


class TestAdjacencyListIntegrity:
    def test_adjacency_list_copy_is_independent(self, populated_graph: FriendGraph):
        adj = populated_graph.adjacency_list()
        adj["alice"].add("hacked")
        # Original graph not mutated
        assert "hacked" not in populated_graph.get_friends("alice")

    def test_adjacency_list_all_symmetric(self, populated_graph: FriendGraph):
        adj = populated_graph.adjacency_list()
        for uid, neighbours in adj.items():
            for nid in neighbours:
                assert uid in adj[nid], (
                    f"Edge {uid}→{nid} exists but {nid}→{uid} does not (asymmetry!)"
                )

    def test_repr_shows_counts(self, populated_graph: FriendGraph):
        r = repr(populated_graph)
        assert "users=4" in r
        assert "edges=3" in r


# ─────────────────────────────────────────────────────────────────────────────
# 5. Error model integrity
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorModel:
    def test_all_errors_subclass_base(self):
        from app.errors import (
            AlreadyFriendsError,
            DuplicateRequestError,
            DuplicateUserError,
            InvalidUserDataError,
            NoPathError,
            NotFriendsError,
            RequestNotFoundError,
            ReverseRequestError,
            SelfFriendshipError,
            SocialGraphError,
            StorageError,
            UserNotFoundError,
        )
        for cls in [
            UserNotFoundError, DuplicateUserError, InvalidUserDataError,
            SelfFriendshipError, AlreadyFriendsError, NotFriendsError,
            DuplicateRequestError, ReverseRequestError, RequestNotFoundError,
            NoPathError, StorageError,
        ]:
            assert issubclass(cls, SocialGraphError), f"{cls} not a SocialGraphError"

    def test_errors_have_code_attribute(self):
        from app.errors import UserNotFoundError
        e = UserNotFoundError("x")
        assert e.code == "USER_NOT_FOUND"
        assert "x" in str(e)
