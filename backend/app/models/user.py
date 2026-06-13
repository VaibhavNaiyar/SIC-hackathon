"""User domain model.

A ``User`` is a node in the social graph.  All mutable state (the friend list)
lives on the ``FriendGraph`` — ``User`` only carries profile data so the two
concerns stay decoupled.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.errors import InvalidUserDataError


@dataclass
class User:
    """Represents a registered member of the social network.

    Attributes:
        user_id:   Unique identifier (UUID string by default).
        name:      Display name — must be non-empty after stripping whitespace.
        age:       Age in years — must be ≥ 13 (platform minimum).
        city:      City of residence.
        interests: Set of interest tags (e.g. ``{"gaming", "hiking"}``).
    """

    name: str
    age: int
    city: str
    interests: set[str] = field(default_factory=set)
    user_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # friends is intentionally NOT stored here — the graph owns edges.

    def __post_init__(self) -> None:
        self._validate()

    # ── Validation ─────────────────────────────────────────────────────────────

    def _validate(self) -> None:
        """Run all field-level validations; raise ``InvalidUserDataError`` on failure."""
        if not self.name or not self.name.strip():
            raise InvalidUserDataError("User name must not be empty.")
        if self.age < 13:
            raise InvalidUserDataError(
                f"User must be at least 13 years old (got {self.age})."
            )
        if not self.city or not self.city.strip():
            raise InvalidUserDataError("City must not be empty.")
        # Normalise: strip whitespace from name/city, lower-case interests
        self.name = self.name.strip()
        self.city = self.city.strip()
        self.interests = {i.lower().strip() for i in self.interests if i.strip()}

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation of this user."""
        return {
            "user_id": self.user_id,
            "name": self.name,
            "age": self.age,
            "city": self.city,
            "interests": sorted(self.interests),  # deterministic order
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "User":
        """Reconstruct a ``User`` from a dict (e.g. loaded from storage).

        The ``user_id`` field is preserved as-is so rehydration is stable.
        """
        return cls(
            name=data["name"],
            age=data["age"],
            city=data["city"],
            interests=set(data.get("interests", [])),
            user_id=data["user_id"],
        )

    # ── Dunder helpers ─────────────────────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return NotImplemented
        return self.user_id == other.user_id

    def __hash__(self) -> int:
        return hash(self.user_id)

    def __repr__(self) -> str:
        return (
            f"User(id={self.user_id!r}, name={self.name!r}, "
            f"age={self.age}, city={self.city!r})"
        )
