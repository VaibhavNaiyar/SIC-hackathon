"""Pathfinder — BFS shortest path + DFS backtracking for all simple paths.

Algorithms implemented
----------------------
1. **BFS shortest path** (``shortest_path``):
   Uses a ``collections.deque`` as a FIFO queue.  A ``parent`` dict records
   the predecessor of each discovered node, enabling O(V+E) path
   reconstruction by back-tracking from target to source.
   Guarantees the *shortest* path in an unweighted graph.

2. **DFS with backtracking — all simple paths** (``all_simple_paths``):
   Explores depth-first, maintaining a ``visited`` set to prevent revisiting
   nodes within the current path (simple-path guarantee).  On reaching the
   target, the current path is recorded.  Backtracking is achieved by
   removing the current node from ``visited`` before returning, restoring the
   set to its pre-call state.  A ``max_depth`` guard prevents combinatorial
   explosion in dense graphs.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from app.errors import UserNotFoundError

if TYPE_CHECKING:
    from app.models.graph import FriendGraph


# ── Result types ───────────────────────────────────────────────────────────────


class PathResult:
    """Holds the result of a shortest-path search.

    Attributes:
        path:    Ordered list of user IDs from source to target (inclusive).
                 ``None`` if no path exists.
        hops:    Number of edges traversed (``len(path) - 1``).
                 ``-1`` if no path exists.
        degrees: Human-readable "degrees of separation" label.
    """

    def __init__(self, path: list[str] | None) -> None:
        self.path = path
        self.hops: int = (len(path) - 1) if path else -1
        self.connected: bool = path is not None
        if path is None:
            self.degrees = "Not connected"
        elif self.hops == 0:
            self.degrees = "Same person"
        elif self.hops == 1:
            self.degrees = "1 degree of separation"
        else:
            self.degrees = f"{self.hops} degrees of separation"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "hops": self.hops,
            "degrees": self.degrees,
            "connected": self.path is not None,
        }

    def __repr__(self) -> str:
        return f"PathResult(hops={self.hops}, path={self.path})"


# ── BFS shortest path ──────────────────────────────────────────────────────────


def shortest_path(graph: "FriendGraph", source: str, target: str) -> PathResult:
    """Find the shortest path between *source* and *target* using BFS.

    The algorithm maintains a ``parent`` map so the path can be reconstructed
    in O(V) after the BFS terminates, without storing full paths in the queue
    (which would use O(V·E) memory).

    Args:
        graph:  The ``FriendGraph`` to search.
        source: Start user ID.
        target: Goal user ID.

    Returns:
        A ``PathResult`` with the ordered path and hop count.
        ``PathResult(path=None)`` if the nodes are disconnected.

    Raises:
        UserNotFoundError: If either user does not exist in the graph.
    """
    if not graph.has_user(source):
        raise UserNotFoundError(source)
    if not graph.has_user(target):
        raise UserNotFoundError(target)

    # Trivial case: path to self
    if source == target:
        return PathResult([source])

    # BFS — deque used as FIFO queue
    queue: deque[str] = deque([source])
    parent: dict[str, str | None] = {source: None}

    while queue:
        current = queue.popleft()
        for neighbour in graph.neighbors(current):
            if neighbour in parent:
                continue  # already visited
            parent[neighbour] = current
            if neighbour == target:
                return PathResult(_reconstruct(parent, source, target))
            queue.append(neighbour)

    # Target never reached — disconnected
    return PathResult(None)


def _reconstruct(parent: dict[str, str | None], source: str, target: str) -> list[str]:
    """Walk the parent map from *target* back to *source* and reverse."""
    path: list[str] = []
    node: str | None = target
    while node is not None:
        path.append(node)
        node = parent[node]
    path.reverse()
    return path


# ── DFS + backtracking — all simple paths ─────────────────────────────────────


def all_simple_paths(
    graph: "FriendGraph",
    source: str,
    target: str,
    max_depth: int = 4,
) -> list[list[str]]:
    """Enumerate all simple paths from *source* to *target* up to *max_depth* hops.

    Uses **DFS with backtracking**:
    * A ``visited`` set prevents revisiting nodes *within* the current path
      (ensuring "simple" — no repeated nodes).
    * After recursing into a neighbour, the neighbour is removed from
      ``visited`` (backtrack) so sibling branches can explore it independently.
    * ``max_depth`` bounds the recursion depth to avoid combinatorial blow-up
      on dense graphs.

    Args:
        graph:     The ``FriendGraph`` to search.
        source:    Start user ID.
        target:    Goal user ID.
        max_depth: Maximum number of hops allowed (default 4).

    Returns:
        List of paths; each path is a list of user IDs (source…target).
        Returns ``[[source]]`` if source == target.
        Returns ``[]`` if no path exists within *max_depth*.

    Raises:
        UserNotFoundError: If either user does not exist.
    """
    if not graph.has_user(source):
        raise UserNotFoundError(source)
    if not graph.has_user(target):
        raise UserNotFoundError(target)

    if source == target:
        return [[source]]

    results: list[list[str]] = []
    visited: set[str] = {source}
    _dfs(graph, source, target, visited, [source], results, max_depth)
    return results


def _dfs(
    graph: "FriendGraph",
    current: str,
    target: str,
    visited: set[str],
    path: list[str],
    results: list[list[str]],
    remaining_depth: int,
) -> None:
    """Recursive DFS helper with backtracking.

    Args:
        current:         The node being expanded in this call.
        target:          The goal node.
        visited:         Set of nodes on the *current* path (mutated in-place;
                         restored on backtrack).
        path:            The current partial path (mutated in-place).
        results:         Accumulator for complete paths found.
        remaining_depth: How many more hops may be taken from *current*.
    """
    if remaining_depth == 0:
        return  # depth limit reached — prune this branch

    for neighbour in graph.neighbors(current):
        if neighbour in visited:
            continue  # already on this path — skip to preserve simplicity

        path.append(neighbour)
        visited.add(neighbour)

        if neighbour == target:
            results.append(list(path))  # snapshot the complete path
        else:
            _dfs(graph, neighbour, target, visited, path, results, remaining_depth - 1)

        # ← backtrack: undo the choice before trying next neighbour
        path.pop()
        visited.discard(neighbour)
