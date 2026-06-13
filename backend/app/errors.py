"""Typed domain exceptions for the Social Network Friend Graph System.

Every error carries a machine-readable ``code`` so API handlers can map it
to the correct HTTP status without inspecting message strings.
"""

from __future__ import annotations


class SocialGraphError(Exception):
    """Base class for all application-domain errors."""

    code: str = "SOCIAL_GRAPH_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


# ── User errors ────────────────────────────────────────────────────────────────

class UserNotFoundError(SocialGraphError):
    """Raised when an operation references a user ID that doesn't exist."""

    code = "USER_NOT_FOUND"

    def __init__(self, user_id: str) -> None:
        super().__init__(f"User '{user_id}' not found.")
        self.user_id = user_id


class DuplicateUserError(SocialGraphError):
    """Raised when attempting to add a user whose ID already exists."""

    code = "DUPLICATE_USER"

    def __init__(self, user_id: str) -> None:
        super().__init__(f"User '{user_id}' already exists.")
        self.user_id = user_id


class InvalidUserDataError(SocialGraphError):
    """Raised when user data fails validation (e.g. empty name, age < 13)."""

    code = "INVALID_USER_DATA"


# ── Friendship errors ──────────────────────────────────────────────────────────

class SelfFriendshipError(SocialGraphError):
    """Raised when a user attempts to befriend themselves."""

    code = "SELF_FRIENDSHIP"

    def __init__(self, user_id: str) -> None:
        super().__init__(f"User '{user_id}' cannot be friends with themselves.")
        self.user_id = user_id


class AlreadyFriendsError(SocialGraphError):
    """Raised when a friendship edge already exists."""

    code = "ALREADY_FRIENDS"

    def __init__(self, a: str, b: str) -> None:
        super().__init__(f"'{a}' and '{b}' are already friends.")
        self.a = a
        self.b = b


class NotFriendsError(SocialGraphError):
    """Raised when trying to remove a friendship that doesn't exist."""

    code = "NOT_FRIENDS"

    def __init__(self, a: str, b: str) -> None:
        super().__init__(f"'{a}' and '{b}' are not friends.")
        self.a = a
        self.b = b


# ── Friend Request errors ──────────────────────────────────────────────────────

class DuplicateRequestError(SocialGraphError):
    """Raised when an identical pending request already exists."""

    code = "DUPLICATE_REQUEST"

    def __init__(self, from_id: str, to_id: str) -> None:
        super().__init__(
            f"A pending request from '{from_id}' to '{to_id}' already exists."
        )
        self.from_id = from_id
        self.to_id = to_id


class ReverseRequestError(SocialGraphError):
    """Raised when the target user has already sent a request to the sender."""

    code = "REVERSE_REQUEST"

    def __init__(self, from_id: str, to_id: str) -> None:
        super().__init__(
            f"'{to_id}' has already sent a friend request to '{from_id}'. "
            "Accept that request instead."
        )
        self.from_id = from_id
        self.to_id = to_id


class RequestNotFoundError(SocialGraphError):
    """Raised when attempting to accept/reject a request that doesn't exist."""

    code = "REQUEST_NOT_FOUND"

    def __init__(self, from_id: str, to_id: str) -> None:
        super().__init__(
            f"No pending request from '{from_id}' to '{to_id}' found."
        )
        self.from_id = from_id
        self.to_id = to_id


# ── Path / Graph errors ────────────────────────────────────────────────────────

class NoPathError(SocialGraphError):
    """Raised (or used as a sentinel) when no path exists between two users."""

    code = "NO_PATH"

    def __init__(self, source: str, target: str) -> None:
        super().__init__(f"No connection path between '{source}' and '{target}'.")
        self.source = source
        self.target = target


# ── Storage errors ─────────────────────────────────────────────────────────────

class StorageError(SocialGraphError):
    """Raised when a persistence operation fails."""

    code = "STORAGE_ERROR"
