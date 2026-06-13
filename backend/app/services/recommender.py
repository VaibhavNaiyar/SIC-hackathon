"""RecommendationEngine — mutual friends, Jaccard similarity, greedy ranking.

Algorithms implemented
----------------------
1. **Mutual friends** (set intersection):
   ``mutual_friends(a, b) = friends(a) ∩ friends(b)``
   O(min(|A|, |B|)) using Python's built-in set intersection.

2. **Jaccard similarity**:
   ``J(A, B) = |A ∩ B| / |A ∪ B|``
   Measures friendship-neighbourhood overlap on a [0, 1] scale.

3. **Friend recommendation** (BFS to depth 2 + greedy ranking):
   Candidates = (friends of friends) − (existing friends) − {self}.
   Each candidate is scored by a weighted sum:
       score = w1 * #mutual_friends + w2 * #common_interests + w3 * same_city
   Candidates are then sorted descending (greedy: always take the
   locally-best-scored candidate) and the top-K are returned with a
   structured explanation object showing *why* each was recommended.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.errors import UserNotFoundError

if TYPE_CHECKING:
    from app.models.graph import FriendGraph


# ── Weights (tuneable) ─────────────────────────────────────────────────────────

W_MUTUALS: float = 3.0    # weight per mutual friend
W_INTERESTS: float = 2.0  # weight per shared interest
W_CITY: float = 1.0       # weight for same city match


# ── Result types ───────────────────────────────────────────────────────────────


@dataclass
class RecommendationExplanation:
    """Human-readable explanation for a single recommendation.

    Attributes:
        mutuals:         List of mutual friend IDs.
        shared_interests: Set of interest tags shared with the target user.
        same_city:       Whether both users are in the same city.
        score:           Computed recommendation score.
    """

    mutuals: list[str]
    shared_interests: list[str]
    same_city: bool
    score: float

    def to_dict(self) -> dict:
        return {
            "mutuals": self.mutuals,
            "shared_interests": self.shared_interests,
            "same_city": self.same_city,
            "score": round(self.score, 4),
        }


@dataclass
class Recommendation:
    """A single friend recommendation for a user.

    Attributes:
        candidate_id: The recommended user's ID.
        why:          Explanation object with scoring details.
    """

    candidate_id: str
    why: RecommendationExplanation

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "why": self.why.to_dict(),
        }


# ── Pure functions ─────────────────────────────────────────────────────────────


def mutual_friends(graph: "FriendGraph", a: str, b: str) -> set[str]:
    """Return the set of user IDs that are friends with *both* a and b.

    Uses set intersection for O(min(|friends(a)|, |friends(b)|)) performance.

    Args:
        graph: The friendship graph.
        a:     First user ID.
        b:     Second user ID.

    Returns:
        Set of mutual friend IDs (may be empty).

    Raises:
        UserNotFoundError: If either user does not exist.
    """
    if not graph.has_user(a):
        raise UserNotFoundError(a)
    if not graph.has_user(b):
        raise UserNotFoundError(b)
    return graph.get_friends(a) & graph.get_friends(b)


def jaccard_similarity(graph: "FriendGraph", a: str, b: str) -> float:
    """Compute Jaccard similarity of the friendship neighbourhoods of a and b.

    J(A, B) = |friends(A) ∩ friends(B)| / |friends(A) ∪ friends(B)|

    Returns 0.0 if both users have no friends, and 1.0 if their friend
    sets are identical (and non-empty).

    Args:
        graph: The friendship graph.
        a:     First user ID.
        b:     Second user ID.

    Returns:
        Float in [0.0, 1.0].

    Raises:
        UserNotFoundError: If either user does not exist.
    """
    if not graph.has_user(a):
        raise UserNotFoundError(a)
    if not graph.has_user(b):
        raise UserNotFoundError(b)
    friends_a = graph.get_friends(a)
    friends_b = graph.get_friends(b)
    union = friends_a | friends_b
    if not union:
        return 0.0
    return len(friends_a & friends_b) / len(union)


# ── RecommendationEngine ───────────────────────────────────────────────────────


class RecommendationEngine:
    """Generates friend recommendations using BFS candidate discovery and
    greedy score-based ranking.

    Args:
        graph: The ``FriendGraph`` instance to operate on.
    """

    def __init__(self, graph: "FriendGraph") -> None:
        self._graph = graph

    # ── Public API ─────────────────────────────────────────────────────────────

    def recommend(
        self,
        user_id: str,
        top_k: int = 5,
        w_mutuals: float = W_MUTUALS,
        w_interests: float = W_INTERESTS,
        w_city: float = W_CITY,
    ) -> list[Recommendation]:
        """Return the top-K friend recommendations for *user_id*.

        Candidate discovery:
            BFS from *user_id* to depth 2 collects all "friends of friends"
            that are not already connected to the target user.

        Scoring (greedy ranking):
            For each candidate ``c``:
                score = w_mutuals  * len(mutual_friends(user_id, c))
                      + w_interests * len(common_interests(user_id, c))
                      + w_city     * (1 if same_city else 0)

            Candidates are sorted by score descending (greedy: take the
            highest-scoring candidate at each selection step).

        Args:
            user_id:    The user to generate recommendations for.
            top_k:      Maximum number of recommendations to return.
            w_mutuals:  Weight for mutual friend count.
            w_interests: Weight for shared interest count.
            w_city:     Weight for same-city bonus.

        Returns:
            List of ``Recommendation`` objects, best first, length ≤ top_k.

        Raises:
            UserNotFoundError: If *user_id* does not exist.
        """
        if not self._graph.has_user(user_id):
            raise UserNotFoundError(user_id)

        user = self._graph.get_user(user_id)
        existing_friends = self._graph.get_friends(user_id)
        excluded = existing_friends | {user_id}

        # BFS to depth 2 — collect candidate IDs
        candidates = self._bfs_candidates(user_id, depth=2, excluded=excluded)

        # Score every candidate
        scored: list[Recommendation] = []
        for cid in candidates:
            candidate = self._graph.get_user(cid)

            mutuals = sorted(mutual_friends(self._graph, user_id, cid))
            shared = sorted(user.interests & candidate.interests)
            same_city = user.city.lower() == candidate.city.lower()

            score = (
                w_mutuals  * len(mutuals)
                + w_interests * len(shared)
                + w_city     * (1.0 if same_city else 0.0)
            )

            scored.append(
                Recommendation(
                    candidate_id=cid,
                    why=RecommendationExplanation(
                        mutuals=mutuals,
                        shared_interests=shared,
                        same_city=same_city,
                        score=score,
                    ),
                )
            )

        # Greedy selection: sort by score descending, take top-K
        scored.sort(key=lambda r: r.why.score, reverse=True)
        return scored[:top_k]

    def mutual_friends(self, a: str, b: str) -> set[str]:
        """Delegate to the module-level ``mutual_friends`` function."""
        return mutual_friends(self._graph, a, b)

    def jaccard_similarity(self, a: str, b: str) -> float:
        """Delegate to the module-level ``jaccard_similarity`` function."""
        return jaccard_similarity(self._graph, a, b)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _bfs_candidates(
        self,
        source: str,
        depth: int,
        excluded: set[str],
    ) -> set[str]:
        """BFS from *source* up to *depth* hops, collecting non-excluded nodes.

        The BFS visits nodes layer by layer.  Nodes in *excluded* are never
        enqueued, so friends and the source itself are never recommended.

        Returns:
            Set of candidate user IDs reachable within *depth* hops.
        """
        visited: set[str] = {source}
        current_layer: set[str] = {source}
        candidates: set[str] = set()

        for _ in range(depth):
            next_layer: set[str] = set()
            for node in current_layer:
                for neighbour in self._graph.neighbors(node):
                    if neighbour in visited:
                        continue
                    visited.add(neighbour)
                    next_layer.add(neighbour)
                    if neighbour not in excluded:
                        candidates.add(neighbour)
            current_layer = next_layer
            if not current_layer:
                break  # no new nodes reachable — stop early

        return candidates
