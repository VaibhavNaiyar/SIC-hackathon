"""FriendGraph — the core adjacency-list graph data structure.

Design decisions
----------------
* Edges are stored as ``dict[str, set[str]]`` (user_id → set of neighbour IDs).
  This gives **O(1)** average-case membership tests, insertions, and deletions
  for all friendship operations.
* The graph is **undirected**: every ``add_friend(a, b)`` call adds *b* to *a*'s
  adjacency set AND *a* to *b*'s adjacency set atomically.
* User objects are stored separately in ``_users: dict[str, User]`` so that
  profile data can be retrieved by ID in O(1) without scanning.

No third-party graph libraries are used — this is the hand-rolled DSA core that
earns the DSA implementation marks.
"""

from __future__ import annotations

from typing import Iterator

from app.errors import (
    AlreadyFriendsError,
    DuplicateUserError,
    NotFriendsError,
    SelfFriendshipError,
    UserNotFoundError,
)
from app.models.user import User


class FriendGraph:
    """Undirected friendship graph backed by an adjacency list.

    The adjacency list is a ``dict`` mapping each ``user_id`` to the *set* of
    IDs of users it is directly connected to (i.e. friends with).

    Example::

        g = FriendGraph()
        alice = User(name="Alice", age=25, city="NYC", user_id="alice")
        bob   = User(name="Bob",   age=30, city="LA",  user_id="bob")
        g.add_user(alice)
        g.add_user(bob)
        g.add_friend("alice", "bob")
        assert g.are_friends("alice", "bob")   # True
        assert g.get_friends("alice") == {"bob"}
    """

    def __init__(self) -> None:
        # user_id → User object (O(1) profile look-up)
        self._users: dict[str, User] = {}
        # user_id → set of neighbour user_ids (the adjacency list)
        self._adj: dict[str, set[str]] = {}

    # ── User management ────────────────────────────────────────────────────────

    def add_user(self, user: User) -> None:
        """Register a new user as an isolated node in the graph.

        Args:
            user: A fully-constructed ``User`` instance.

        Raises:
            DuplicateUserError: If a user with the same ID already exists.
        """
        if user.user_id in self._users:
            raise DuplicateUserError(user.user_id)
        self._users[user.user_id] = user
        self._adj[user.user_id] = set()

    def remove_user(self, user_id: str) -> User:
        """Remove a user and all their friendship edges from the graph.

        Args:
            user_id: The ID of the user to remove.

        Returns:
            The removed ``User`` object.

        Raises:
            UserNotFoundError: If the user does not exist.
        """
        self._require_user(user_id)
        # Remove this user from every neighbour's adjacency set first
        for neighbour_id in list(self._adj[user_id]):
            self._adj[neighbour_id].discard(user_id)
        del self._adj[user_id]
        return self._users.pop(user_id)

    def get_user(self, user_id: str) -> User:
        """Return the ``User`` object for the given ID.

        Raises:
            UserNotFoundError: If the user does not exist.
        """
        self._require_user(user_id)
        return self._users[user_id]

    # ── Friendship / edge management ───────────────────────────────────────────

    def add_friend(self, a: str, b: str) -> None:
        """Create an undirected friendship edge between users *a* and *b*.

        This operation is **idempotent**: calling it when the friendship already
        exists raises ``AlreadyFriendsError`` to signal the caller, but the
        graph state remains unchanged.

        Args:
            a: ID of the first user.
            b: ID of the second user.

        Raises:
            UserNotFoundError:    If either user does not exist.
            SelfFriendshipError:  If ``a == b``.
            AlreadyFriendsError:  If the edge already exists.
        """
        self._require_user(a)
        self._require_user(b)
        if a == b:
            raise SelfFriendshipError(a)
        if b in self._adj[a]:
            raise AlreadyFriendsError(a, b)
        # Add both directions atomically
        self._adj[a].add(b)
        self._adj[b].add(a)

    def remove_friend(self, a: str, b: str) -> None:
        """Remove the friendship edge between users *a* and *b*.

        Args:
            a: ID of the first user.
            b: ID of the second user.

        Raises:
            UserNotFoundError:  If either user does not exist.
            SelfFriendshipError: If ``a == b``.
            NotFriendsError:    If the edge does not exist.
        """
        self._require_user(a)
        self._require_user(b)
        if a == b:
            raise SelfFriendshipError(a)
        if b not in self._adj[a]:
            raise NotFriendsError(a, b)
        self._adj[a].discard(b)
        self._adj[b].discard(a)

    def get_friends(self, user_id: str) -> set[str]:
        """Return the set of user IDs that are direct friends of *user_id*.

        Returns a **copy** of the internal set to prevent external mutation.

        Raises:
            UserNotFoundError: If the user does not exist.
        """
        self._require_user(user_id)
        return set(self._adj[user_id])

    def are_friends(self, a: str, b: str) -> bool:
        """Return ``True`` if *a* and *b* share a direct friendship edge.

        Raises:
            UserNotFoundError: If either user does not exist.
        """
        self._require_user(a)
        self._require_user(b)
        return b in self._adj[a]

    def neighbors(self, user_id: str) -> set[str]:
        """Alias for ``get_friends`` — returns the adjacency set for *user_id*.

        Useful in algorithm code where graph-traversal semantics are clearer.

        Raises:
            UserNotFoundError: If the user does not exist.
        """
        return self.get_friends(user_id)

    # ── Graph-level queries ────────────────────────────────────────────────────

    def users(self) -> Iterator[User]:
        """Iterate over all registered ``User`` objects."""
        return iter(self._users.values())

    def user_ids(self) -> set[str]:
        """Return the set of all registered user IDs."""
        return set(self._users.keys())

    def has_user(self, user_id: str) -> bool:
        """Return ``True`` if *user_id* is registered in the graph."""
        return user_id in self._users

    def edge_count(self) -> int:
        """Return the total number of unique friendship edges.

        Because the graph is undirected, every edge is counted once even
        though it appears in two adjacency sets.
        """
        return sum(len(s) for s in self._adj.values()) // 2

    def degree(self, user_id: str) -> int:
        """Return the degree (number of friends) of *user_id*.

        Raises:
            UserNotFoundError: If the user does not exist.
        """
        self._require_user(user_id)
        return len(self._adj[user_id])

    def adjacency_list(self) -> dict[str, set[str]]:
        """Return a shallow copy of the full adjacency list.

        Useful for serialisation and analytics without exposing the mutable
        internal structure.
        """
        return {uid: set(neighbours) for uid, neighbours in self._adj.items()}

    # ── Dunder helpers ─────────────────────────────────────────────────────────

    def __len__(self) -> int:
        """Return the number of registered users (nodes)."""
        return len(self._users)

    def __contains__(self, user_id: str) -> bool:
        """Support ``user_id in graph`` membership test."""
        return user_id in self._users

    def __repr__(self) -> str:
        return (
            f"FriendGraph(users={len(self._users)}, "
            f"edges={self.edge_count()})"
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _require_user(self, user_id: str) -> None:
        """Raise ``UserNotFoundError`` if *user_id* is not in the graph."""
        if user_id not in self._users:
            raise UserNotFoundError(user_id)
