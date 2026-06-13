"""Phase 2 test suite — FriendRequestManager.

Covers the Phase 2 acceptance criteria:
  ✓ accept_request creates a bidirectional friendship and removes the pending entry
  ✓ reject_request removes the pending entry and creates no edge
  ✓ Duplicate requests blocked
  ✓ Self-requests blocked
  ✓ Requesting someone you're already friends with blocked
  ✓ Reverse-duplicate request detected and blocked
  ✓ pending_for returns requests in arrival (FIFO) order
  ✓ RequestStatus enum values
"""

from __future__ import annotations

import pytest

from app.errors import (
    AlreadyFriendsError,
    DuplicateRequestError,
    RequestNotFoundError,
    ReverseRequestError,
    SelfFriendshipError,
    UserNotFoundError,
)
from app.models.graph import FriendGraph
from app.models.requests import FriendRequest, FriendRequestManager, RequestStatus
from app.models.user import User


# ── Fixtures ───────────────────────────────────────────────────────────────────


def make_user(uid: str, name: str = "Test") -> User:
    return User(name=name, age=20, city="NYC", user_id=uid)


@pytest.fixture()
def graph() -> FriendGraph:
    g = FriendGraph()
    for uid, name in [
        ("alice", "Alice"),
        ("bob", "Bob"),
        ("carol", "Carol"),
        ("dave", "Dave"),
    ]:
        g.add_user(make_user(uid, name))
    return g


@pytest.fixture()
def mgr(graph: FriendGraph) -> FriendRequestManager:
    return FriendRequestManager(graph)


# ─────────────────────────────────────────────────────────────────────────────
# 1. RequestStatus enum
# ─────────────────────────────────────────────────────────────────────────────


class TestRequestStatus:
    def test_enum_values_exist(self):
        assert RequestStatus.PENDING.value == "PENDING"
        assert RequestStatus.ACCEPTED.value == "ACCEPTED"
        assert RequestStatus.REJECTED.value == "REJECTED"

    def test_is_string_enum(self):
        # str Enum allows direct comparison with string literals
        assert RequestStatus.PENDING == "PENDING"


# ─────────────────────────────────────────────────────────────────────────────
# 2. FriendRequest value object
# ─────────────────────────────────────────────────────────────────────────────


class TestFriendRequestObject:
    def test_initial_status_is_pending(self):
        req = FriendRequest("alice", "bob")
        assert req.status == RequestStatus.PENDING

    def test_to_dict(self):
        req = FriendRequest("alice", "bob")
        d = req.to_dict()
        assert d == {"from_id": "alice", "to_id": "bob", "status": "PENDING"}

    def test_equality(self):
        r1 = FriendRequest("alice", "bob")
        r2 = FriendRequest("alice", "bob")
        assert r1 == r2

    def test_inequality_different_parties(self):
        assert FriendRequest("alice", "bob") != FriendRequest("bob", "alice")


# ─────────────────────────────────────────────────────────────────────────────
# 3. send_request — happy path
# ─────────────────────────────────────────────────────────────────────────────


class TestSendRequest:
    def test_returns_pending_request(self, mgr: FriendRequestManager):
        req = mgr.send_request("alice", "bob")
        assert req.from_id == "alice"
        assert req.to_id == "bob"
        assert req.status == RequestStatus.PENDING

    def test_appears_in_recipients_pending_queue(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        pending = mgr.pending_for("bob")
        assert len(pending) == 1
        assert pending[0].from_id == "alice"

    def test_total_pending_increments(self, mgr: FriendRequestManager):
        assert mgr.total_pending() == 0
        mgr.send_request("alice", "bob")
        assert mgr.total_pending() == 1
        mgr.send_request("carol", "bob")
        assert mgr.total_pending() == 2

    def test_has_pending_request_true(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        assert mgr.has_pending_request("alice", "bob")

    def test_has_pending_request_false_reverse(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        assert not mgr.has_pending_request("bob", "alice")

    def test_pending_sent_by(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        mgr.send_request("alice", "carol")
        sent = mgr.pending_sent_by("alice")
        assert set(sent) == {"bob", "carol"}


# ─────────────────────────────────────────────────────────────────────────────
# 4. send_request — guard clauses
# ─────────────────────────────────────────────────────────────────────────────


class TestSendRequestGuards:
    def test_unknown_sender_raises(self, mgr: FriendRequestManager):
        with pytest.raises(UserNotFoundError) as exc:
            mgr.send_request("ghost", "bob")
        assert exc.value.user_id == "ghost"

    def test_unknown_recipient_raises(self, mgr: FriendRequestManager):
        with pytest.raises(UserNotFoundError) as exc:
            mgr.send_request("alice", "ghost")
        assert exc.value.user_id == "ghost"

    def test_self_request_raises(self, mgr: FriendRequestManager):
        with pytest.raises(SelfFriendshipError) as exc:
            mgr.send_request("alice", "alice")
        assert exc.value.user_id == "alice"

    def test_already_friends_raises(
        self, graph: FriendGraph, mgr: FriendRequestManager
    ):
        graph.add_friend("alice", "bob")
        with pytest.raises(AlreadyFriendsError):
            mgr.send_request("alice", "bob")

    def test_duplicate_request_same_direction_raises(
        self, mgr: FriendRequestManager
    ):
        mgr.send_request("alice", "bob")
        with pytest.raises(DuplicateRequestError) as exc:
            mgr.send_request("alice", "bob")
        assert exc.value.from_id == "alice"
        assert exc.value.to_id == "bob"

    def test_reverse_request_raises(self, mgr: FriendRequestManager):
        """If bob already sent a request to alice, alice→bob should raise ReverseRequestError."""
        mgr.send_request("bob", "alice")
        with pytest.raises(ReverseRequestError) as exc:
            mgr.send_request("alice", "bob")
        assert exc.value.from_id == "alice"
        assert exc.value.to_id == "bob"

    def test_guard_does_not_mutate_state_on_failure(
        self, mgr: FriendRequestManager
    ):
        """State must remain clean after a rejected guard."""
        mgr.send_request("alice", "bob")
        with pytest.raises(DuplicateRequestError):
            mgr.send_request("alice", "bob")
        # The queue must still contain exactly one request
        assert len(mgr.pending_for("bob")) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. accept_request
# ─────────────────────────────────────────────────────────────────────────────


class TestAcceptRequest:
    def test_accept_creates_friendship(
        self, graph: FriendGraph, mgr: FriendRequestManager
    ):
        mgr.send_request("alice", "bob")
        mgr.accept_request("bob", "alice")
        assert graph.are_friends("alice", "bob")
        assert graph.are_friends("bob", "alice")  # both directions

    def test_accept_removes_from_pending_queue(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        mgr.accept_request("bob", "alice")
        assert len(mgr.pending_for("bob")) == 0
        assert mgr.total_pending() == 0

    def test_accept_updates_status(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        req = mgr.accept_request("bob", "alice")
        assert req.status == RequestStatus.ACCEPTED

    def test_accept_clears_senders_outgoing_set(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        mgr.accept_request("bob", "alice")
        assert not mgr.has_pending_request("alice", "bob")

    def test_accept_nonexistent_request_raises(self, mgr: FriendRequestManager):
        with pytest.raises(RequestNotFoundError):
            mgr.accept_request("bob", "alice")

    def test_accept_preserves_other_pending_requests(
        self, mgr: FriendRequestManager
    ):
        """Accepting one request in a queue must not affect other entries."""
        mgr.send_request("alice", "bob")
        mgr.send_request("carol", "bob")
        mgr.accept_request("bob", "alice")
        remaining = mgr.pending_for("bob")
        assert len(remaining) == 1
        assert remaining[0].from_id == "carol"


# ─────────────────────────────────────────────────────────────────────────────
# 6. reject_request
# ─────────────────────────────────────────────────────────────────────────────


class TestRejectRequest:
    def test_reject_creates_no_friendship(
        self, graph: FriendGraph, mgr: FriendRequestManager
    ):
        mgr.send_request("alice", "bob")
        mgr.reject_request("bob", "alice")
        assert not graph.are_friends("alice", "bob")

    def test_reject_removes_from_pending_queue(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        mgr.reject_request("bob", "alice")
        assert len(mgr.pending_for("bob")) == 0
        assert mgr.total_pending() == 0

    def test_reject_updates_status(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        req = mgr.reject_request("bob", "alice")
        assert req.status == RequestStatus.REJECTED

    def test_reject_clears_senders_outgoing_set(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        mgr.reject_request("bob", "alice")
        assert not mgr.has_pending_request("alice", "bob")

    def test_reject_nonexistent_request_raises(self, mgr: FriendRequestManager):
        with pytest.raises(RequestNotFoundError):
            mgr.reject_request("bob", "alice")

    def test_reject_preserves_other_pending_requests(
        self, mgr: FriendRequestManager
    ):
        mgr.send_request("alice", "bob")
        mgr.send_request("carol", "bob")
        mgr.reject_request("bob", "carol")
        remaining = mgr.pending_for("bob")
        assert len(remaining) == 1
        assert remaining[0].from_id == "alice"

    def test_after_reject_sender_can_resend(
        self, mgr: FriendRequestManager
    ):
        """After rejection, the sender is free to send a new request."""
        mgr.send_request("alice", "bob")
        mgr.reject_request("bob", "alice")
        # Should not raise
        req = mgr.send_request("alice", "bob")
        assert req.status == RequestStatus.PENDING


# ─────────────────────────────────────────────────────────────────────────────
# 7. FIFO (queue) ordering
# ─────────────────────────────────────────────────────────────────────────────


class TestFIFOOrdering:
    def test_pending_for_preserves_arrival_order(self, mgr: FriendRequestManager):
        """Requests must be returned oldest-first (FIFO)."""
        mgr.send_request("alice", "dave")
        mgr.send_request("bob", "dave")
        mgr.send_request("carol", "dave")

        pending = mgr.pending_for("dave")
        assert [r.from_id for r in pending] == ["alice", "bob", "carol"]

    def test_accepting_middle_request_preserves_order(
        self, mgr: FriendRequestManager
    ):
        """Removing the middle entry must keep the others in order."""
        mgr.send_request("alice", "dave")
        mgr.send_request("bob", "dave")
        mgr.send_request("carol", "dave")

        mgr.accept_request("dave", "bob")
        pending = mgr.pending_for("dave")
        assert [r.from_id for r in pending] == ["alice", "carol"]

    def test_pending_for_empty_if_no_requests(self, mgr: FriendRequestManager):
        assert mgr.pending_for("alice") == []

    def test_pending_for_unknown_user_raises(self, mgr: FriendRequestManager):
        with pytest.raises(UserNotFoundError):
            mgr.pending_for("ghost")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Integration — full lifecycle
# ─────────────────────────────────────────────────────────────────────────────


class TestFullLifecycle:
    def test_send_accept_then_no_reverse_request_possible(
        self, graph: FriendGraph, mgr: FriendRequestManager
    ):
        """After accepting, both users are friends — further requests are blocked."""
        mgr.send_request("alice", "bob")
        mgr.accept_request("bob", "alice")
        with pytest.raises(AlreadyFriendsError):
            mgr.send_request("alice", "bob")
        with pytest.raises(AlreadyFriendsError):
            mgr.send_request("bob", "alice")

    def test_multiple_independent_pairs(
        self, graph: FriendGraph, mgr: FriendRequestManager
    ):
        mgr.send_request("alice", "carol")
        mgr.send_request("bob", "dave")
        mgr.accept_request("carol", "alice")
        mgr.reject_request("dave", "bob")

        assert graph.are_friends("alice", "carol")
        assert not graph.are_friends("bob", "dave")
        assert mgr.total_pending() == 0

    def test_repr(self, mgr: FriendRequestManager):
        mgr.send_request("alice", "bob")
        assert "pending=1" in repr(mgr)
