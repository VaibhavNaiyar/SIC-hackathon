"""FriendRequestManager — FIFO request queue per user.

Design decisions
----------------
* Pending requests for each recipient are stored in a ``collections.deque``
  (double-ended queue used in FIFO mode).  This is the explicit Queue DSA
  requirement: ``send_request`` appends to the right (tail); ``accept_request``
  and ``reject_request`` remove by value — preserving arrival order for all
  *other* requests in the queue.
* A separate ``dict[str, set[str]]`` tracks ``_sent_by[from_id]`` (the IDs the
  sender currently has a pending outgoing request to) for O(1) duplicate
  detection without scanning every recipient queue.
* All guard checks are performed *before* mutating any state, so the object
  stays consistent if an error is raised mid-operation.

Relationships
-------------
``FriendRequestManager`` holds a reference to a ``FriendGraph`` so that
``accept_request`` can create the friendship edge atomically in the same call.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import TYPE_CHECKING

from app.errors import (
    AlreadyFriendsError,
    DuplicateRequestError,
    RequestNotFoundError,
    ReverseRequestError,
    SelfFriendshipError,
    UserNotFoundError,
)

if TYPE_CHECKING:
    from app.models.graph import FriendGraph


class RequestStatus(str, Enum):
    """Lifecycle states for a friend request."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class FriendRequest:
    """Value object representing a single friend request.

    Attributes:
        from_id: User ID of the sender.
        to_id:   User ID of the recipient.
        status:  Current ``RequestStatus``.
    """

    __slots__ = ("from_id", "to_id", "status")

    def __init__(self, from_id: str, to_id: str) -> None:
        self.from_id = from_id
        self.to_id = to_id
        self.status = RequestStatus.PENDING

    def to_dict(self) -> dict[str, str]:
        return {
            "from_id": self.from_id,
            "to_id": self.to_id,
            "status": self.status.value,
        }

    def __repr__(self) -> str:
        return (
            f"FriendRequest(from={self.from_id!r}, to={self.to_id!r}, "
            f"status={self.status.value})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FriendRequest):
            return NotImplemented
        return self.from_id == other.from_id and self.to_id == other.to_id


class FriendRequestManager:
    """Manages the lifecycle of friend requests across the social network.

    Internal data structures
    ------------------------
    ``_incoming[to_id]`` → ``deque[FriendRequest]``
        FIFO queue of pending requests received by *to_id*, in arrival order.

    ``_sent_by[from_id]`` → ``set[str]``
        Set of *to_id* values that *from_id* currently has a pending outgoing
        request to — used for O(1) duplicate detection.

    Args:
        graph: The ``FriendGraph`` instance that will receive new edges when
               requests are accepted.
    """

    def __init__(self, graph: "FriendGraph") -> None:
        self._graph = graph
        # recipient → FIFO queue of pending requests
        self._incoming: dict[str, deque[FriendRequest]] = {}
        # sender → set of recipients with a live pending request
        self._sent_by: dict[str, set[str]] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def send_request(self, from_id: str, to_id: str) -> FriendRequest:
        """Send a friend request from *from_id* to *to_id*.

        Guards (checked in order):
            1. Both users must exist in the graph.
            2. ``from_id != to_id`` (no self-requests).
            3. The pair must not already be friends.
            4. No duplicate pending request in the same direction.
            5. No reverse-pending request (*to_id* → *from_id* already waiting).

        Returns:
            The newly created ``FriendRequest`` in ``PENDING`` status.

        Raises:
            UserNotFoundError:    If either user doesn't exist.
            SelfFriendshipError:  If ``from_id == to_id``.
            AlreadyFriendsError:  If the pair are already friends.
            DuplicateRequestError: If a pending request from→to already exists.
            ReverseRequestError:  If a pending request to→from already exists.
        """
        # 1. Existence checks
        if not self._graph.has_user(from_id):
            raise UserNotFoundError(from_id)
        if not self._graph.has_user(to_id):
            raise UserNotFoundError(to_id)

        # 2. Self-request
        if from_id == to_id:
            raise SelfFriendshipError(from_id)

        # 3. Already friends
        if self._graph.are_friends(from_id, to_id):
            raise AlreadyFriendsError(from_id, to_id)

        # 4. Duplicate pending (same direction)
        if to_id in self._sent_by.get(from_id, set()):
            raise DuplicateRequestError(from_id, to_id)

        # 5. Reverse pending (other direction already waiting)
        if from_id in self._sent_by.get(to_id, set()):
            raise ReverseRequestError(from_id, to_id)

        # All guards passed — create and enqueue
        req = FriendRequest(from_id=from_id, to_id=to_id)

        self._incoming.setdefault(to_id, deque()).append(req)
        self._sent_by.setdefault(from_id, set()).add(to_id)

        return req

    def accept_request(self, to_id: str, from_id: str) -> FriendRequest:
        """Accept a pending request that *from_id* sent to *to_id*.

        Side effects:
            * Removes the request from the pending queue.
            * Creates a bidirectional friendship edge in the graph.
            * Updates the request's status to ``ACCEPTED``.

        Returns:
            The now-``ACCEPTED`` ``FriendRequest``.

        Raises:
            RequestNotFoundError: If no matching pending request exists.
        """
        req = self._pop_request(to_id, from_id)
        req.status = RequestStatus.ACCEPTED
        # Create the friendship edge in the graph
        self._graph.add_friend(from_id, to_id)
        return req

    def reject_request(self, to_id: str, from_id: str) -> FriendRequest:
        """Reject a pending request that *from_id* sent to *to_id*.

        Side effects:
            * Removes the request from the pending queue.
            * No friendship edge is created.
            * Updates the request's status to ``REJECTED``.

        Returns:
            The now-``REJECTED`` ``FriendRequest``.

        Raises:
            RequestNotFoundError: If no matching pending request exists.
        """
        req = self._pop_request(to_id, from_id)
        req.status = RequestStatus.REJECTED
        return req

    def pending_for(self, user_id: str) -> list[FriendRequest]:
        """Return all incoming pending requests for *user_id* in arrival order.

        Args:
            user_id: The recipient's user ID.

        Returns:
            A list of ``FriendRequest`` objects (possibly empty), oldest first.

        Raises:
            UserNotFoundError: If *user_id* doesn't exist in the graph.
        """
        if not self._graph.has_user(user_id):
            raise UserNotFoundError(user_id)
        return list(self._incoming.get(user_id, deque()))

    def pending_sent_by(self, user_id: str) -> list[str]:
        """Return the list of user IDs that *user_id* has a pending request to.

        Raises:
            UserNotFoundError: If *user_id* doesn't exist in the graph.
        """
        if not self._graph.has_user(user_id):
            raise UserNotFoundError(user_id)
        return sorted(self._sent_by.get(user_id, set()))

    def has_pending_request(self, from_id: str, to_id: str) -> bool:
        """Return ``True`` if a pending request from *from_id* to *to_id* exists."""
        return to_id in self._sent_by.get(from_id, set())

    def total_pending(self) -> int:
        """Return the total number of pending requests across all users."""
        return sum(len(q) for q in self._incoming.values())

    # ── Private helpers ────────────────────────────────────────────────────────

    def _pop_request(self, to_id: str, from_id: str) -> FriendRequest:
        """Find and remove the matching request from the recipient's queue.

        Preserves FIFO order for all other requests in the queue by rebuilding
        the deque without the matched entry.

        Raises:
            RequestNotFoundError: If no matching pending request is found.
        """
        queue = self._incoming.get(to_id)
        if queue is None:
            raise RequestNotFoundError(from_id, to_id)

        # Find the request — deque doesn't support random removal, so we
        # rebuild it without the matched entry (queue is typically small).
        found: FriendRequest | None = None
        new_queue: deque[FriendRequest] = deque()
        for req in queue:
            if req.from_id == from_id and found is None:
                found = req
            else:
                new_queue.append(req)

        if found is None:
            raise RequestNotFoundError(from_id, to_id)

        # Commit the rebuilt queue
        self._incoming[to_id] = new_queue
        # Clean up the sender's outgoing set
        sent = self._sent_by.get(from_id, set())
        sent.discard(to_id)

        return found

    def __repr__(self) -> str:
        return f"FriendRequestManager(pending={self.total_pending()})"
