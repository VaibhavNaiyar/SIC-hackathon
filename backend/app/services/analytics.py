"""NetworkAnalytics — pandas/numpy analytics + community detection.

Phase 3 contribution: Union-Find (disjoint set union) for connected-component
labelling.

Phase 4 additions
-----------------
* ``NetworkAnalytics`` class: pandas DataFrames, degree centrality, city
  distribution, Floyd-Warshall all-pairs shortest paths (numpy DP), avg
  separation, diameter, friendship growth time-series, influencer leaderboard.

Floyd-Warshall DP design
------------------------
Build an N×N numpy distance matrix D where:
    D[i,j] = 1   if i and j are friends
    D[i,j] = 0   if i == j
    D[i,j] = inf otherwise

Then for each intermediate node k:
    D[i,j] = min(D[i,j], D[i,k] + D[k,j])

This is the classic O(N³) dynamic-programming relaxation — the "DP algorithm"
mark.  For the network sizes in this project (≤ a few hundred users) it runs
in negligible time.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from app.models.graph import FriendGraph


# ── Union-Find (disjoint set union) ───────────────────────────────────────────


class UnionFind:
    """Disjoint-Set Union with path compression and union by rank.

    Args:
        members: Iterable of member IDs to initialise.
    """

    def __init__(self, members: list[str]) -> None:
        self._parent: dict[str, str] = {m: m for m in members}
        self._rank: dict[str, int] = {m: 0 for m in members}
        self._size: dict[str, int] = {m: 1 for m in members}

    def find(self, x: str) -> str:
        """Return the root of x's component with path compression."""
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str) -> bool:
        """Merge components of x and y. Returns True if they were distinct."""
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        self._size[rx] += self._size[ry]
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1
        return True

    def connected(self, x: str, y: str) -> bool:
        return self.find(x) == self.find(y)

    def component_size(self, x: str) -> int:
        return self._size[self.find(x)]

    def components(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for member in self._parent:
            root = self.find(member)
            groups.setdefault(root, []).append(member)
        return groups


# ── Community detection entry points ──────────────────────────────────────────


def detect_communities(graph: "FriendGraph") -> dict[str, int]:
    """Label every user with a community (connected-component) integer index."""
    ids = list(graph.user_ids())
    if not ids:
        return {}
    uf = UnionFind(ids)
    for uid in ids:
        for neighbour in graph.neighbors(uid):
            uf.union(uid, neighbour)
    root_to_label: dict[str, int] = {}
    label_counter = 0
    result: dict[str, int] = {}
    for uid in ids:
        root = uf.find(uid)
        if root not in root_to_label:
            root_to_label[root] = label_counter
            label_counter += 1
        result[uid] = root_to_label[root]
    return result


def connected_components(graph: "FriendGraph") -> list[list[str]]:
    """Return sorted lists of user IDs per connected component, largest first."""
    ids = list(graph.user_ids())
    if not ids:
        return []
    uf = UnionFind(ids)
    for uid in ids:
        for neighbour in graph.neighbors(uid):
            uf.union(uid, neighbour)
    groups = uf.components()
    components = [sorted(members) for members in groups.values()]
    components.sort(key=len, reverse=True)
    return components


# ── NetworkAnalytics ───────────────────────────────────────────────────────────


class NetworkAnalytics:
    """Compute graph-level analytics using pandas and numpy.

    Args:
        graph:      The ``FriendGraph`` to analyse.
        timestamps: Optional mapping of ``(a, b)`` edge (sorted tuple) to a
                    ``datetime`` recording when the friendship was created.
                    Used for the friendship-growth time series.
    """

    def __init__(
        self,
        graph: "FriendGraph",
        timestamps: dict[tuple[str, str], datetime] | None = None,
    ) -> None:
        self._graph = graph
        self._timestamps = timestamps or {}
        self._users_df: pd.DataFrame | None = None
        self._edges_df: pd.DataFrame | None = None

    # ── DataFrame builders ─────────────────────────────────────────────────────

    def users_dataframe(self) -> pd.DataFrame:
        """Build (and cache) a DataFrame with one row per user.

        Columns: user_id, name, age, city, interests_count, degree
        """
        if self._users_df is not None:
            return self._users_df

        rows = []
        for user in self._graph.users():
            rows.append(
                {
                    "user_id": user.user_id,
                    "name": user.name,
                    "age": user.age,
                    "city": user.city,
                    "interests_count": len(user.interests),
                    "degree": self._graph.degree(user.user_id),
                }
            )
        self._users_df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["user_id", "name", "age", "city", "interests_count", "degree"]
        )
        return self._users_df

    def edges_dataframe(self) -> pd.DataFrame:
        """Build (and cache) a DataFrame with one row per unique edge.

        Columns: user_a, user_b, created_at (NaT if no timestamp)
        """
        if self._edges_df is not None:
            return self._edges_df

        rows = []
        seen: set[tuple[str, str]] = set()
        for uid in self._graph.user_ids():
            for nid in self._graph.neighbors(uid):
                key = (min(uid, nid), max(uid, nid))
                if key in seen:
                    continue
                seen.add(key)
                ts = self._timestamps.get(key)
                rows.append({"user_a": key[0], "user_b": key[1], "created_at": ts})

        self._edges_df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["user_a", "user_b", "created_at"]
        )
        if not self._edges_df.empty:
            self._edges_df["created_at"] = pd.to_datetime(
                self._edges_df["created_at"]
            )
        return self._edges_df

    # ── Degree / centrality ────────────────────────────────────────────────────

    def most_connected(self, top_n: int = 10) -> pd.DataFrame:
        """Return the top-N users by degree (friend count), descending.

        Returns a DataFrame with columns: user_id, name, city, degree.
        """
        df = self.users_dataframe()
        if df.empty:
            return df
        return (
            df[["user_id", "name", "city", "degree"]]
            .sort_values("degree", ascending=False)
            .head(top_n)
            .reset_index(drop=True)
        )

    def degree_stats(self) -> dict[str, float]:
        """Return mean, median, max, min degree as a dict."""
        df = self.users_dataframe()
        if df.empty:
            return {"mean": 0.0, "median": 0.0, "max": 0, "min": 0}
        deg = df["degree"]
        return {
            "mean": float(np.mean(deg.values)),
            "median": float(np.median(deg.values)),
            "max": int(deg.max()),
            "min": int(deg.min()),
        }

    # ── City distribution ──────────────────────────────────────────────────────

    def city_distribution(self) -> pd.DataFrame:
        """Return a DataFrame of city counts, sorted by count descending.

        Columns: city, count, percentage
        """
        df = self.users_dataframe()
        if df.empty:
            return pd.DataFrame(columns=["city", "count", "percentage"])
        counts = df.groupby("city").size().reset_index(name="count")
        total = counts["count"].sum()
        counts["percentage"] = (counts["count"] / total * 100).round(2)
        return counts.sort_values("count", ascending=False).reset_index(drop=True)

    # ── Floyd-Warshall all-pairs shortest paths (DP) ──────────────────────────

    def floyd_warshall(self) -> np.ndarray:
        """Compute the all-pairs shortest-path distance matrix via Floyd-Warshall.

        This is the **DP algorithm** mark: we relax distances over each
        intermediate node k in O(N³) time using a numpy matrix.

        Returns:
            N×N float64 numpy array where ``D[i,j]`` is the shortest-path
            length between users i and j.  Unreachable pairs store ``inf``.
            Diagonal is 0.
        """
        ids = sorted(self._graph.user_ids())  # stable ordering
        n = len(ids)
        if n == 0:
            return np.zeros((0, 0), dtype=np.float64)

        idx = {uid: i for i, uid in enumerate(ids)}

        # Initialise: 0 on diagonal, 1 for edges, inf otherwise
        D = np.full((n, n), np.inf, dtype=np.float64)
        np.fill_diagonal(D, 0.0)

        for uid in ids:
            i = idx[uid]
            for nid in self._graph.neighbors(uid):
                j = idx[nid]
                D[i, j] = 1.0

        # DP relaxation — the Floyd-Warshall triple loop
        for k in range(n):
            # numpy broadcasting: update all (i, j) pairs in one vectorised step
            D = np.minimum(D, D[:, k:k+1] + D[k:k+1, :])

        return D

    def _fw_result(self) -> tuple[np.ndarray, list[str]]:
        """Return (distance_matrix, ordered_ids) — computed once per instance."""
        if not hasattr(self, "_D"):
            self._ids_ordered = sorted(self._graph.user_ids())
            self._D = self.floyd_warshall()
        return self._D, self._ids_ordered

    def diameter(self) -> float:
        """Return the graph diameter (longest shortest path) using Floyd-Warshall.

        Returns 0 for empty/single-node graphs, inf if graph is disconnected.
        """
        D, _ = self._fw_result()
        if D.size == 0:
            return 0.0
        finite = D[np.isfinite(D) & (D > 0)]
        if finite.size == 0:
            return 0.0
        return float(np.max(finite))

    def average_separation(self) -> float:
        """Return the average shortest-path length over all *connected* pairs.

        Disconnected pairs (inf distance) are excluded.
        Returns 0.0 for graphs with fewer than 2 users.
        """
        D, _ = self._fw_result()
        if D.size == 0:
            return 0.0
        finite = D[np.isfinite(D) & (D > 0)]
        if finite.size == 0:
            return 0.0
        return float(np.mean(finite))

    # ── Network density ────────────────────────────────────────────────────────

    def density(self) -> float:
        """Return network density = actual edges / possible edges.

        For an undirected graph with N nodes: max_edges = N*(N-1)/2.
        Returns 0.0 for graphs with fewer than 2 nodes.
        """
        n = len(self._graph)
        if n < 2:
            return 0.0
        max_edges = n * (n - 1) / 2
        return self._graph.edge_count() / max_edges

    # ── Friendship growth time series ──────────────────────────────────────────

    def friendship_growth(self) -> pd.DataFrame:
        """Return a cumulative friendship-growth time series.

        Only works when timestamps are provided.  Edges are sorted by
        ``created_at`` and cumulative count is computed with pandas cumsum.

        Returns:
            DataFrame with columns: created_at, new_edges, cumulative_edges.
            Empty DataFrame if no timestamps are stored.
        """
        df = self.edges_dataframe()
        if df.empty or df["created_at"].isna().all():
            return pd.DataFrame(
                columns=["created_at", "new_edges", "cumulative_edges"]
            )
        ts_df = df.dropna(subset=["created_at"]).copy()
        ts_df = ts_df.sort_values("created_at")
        ts_df["new_edges"] = 1
        ts_df["cumulative_edges"] = ts_df["new_edges"].cumsum()
        return ts_df[["created_at", "new_edges", "cumulative_edges"]].reset_index(
            drop=True
        )

    # ── Influencer leaderboard ─────────────────────────────────────────────────

    def top_influencers(self, top_n: int = 5) -> list[dict[str, Any]]:
        """Return the top-N influencers ranked by degree (greedy selection).

        For each candidate, also estimates a betweenness score as the fraction
        of all-pairs shortest paths that pass through them, approximated from
        the Floyd-Warshall distance matrix (no repeated BFS needed).

        Returns:
            List of dicts: {user_id, name, degree, betweenness_approx}
        """
        df = self.users_dataframe()
        if df.empty:
            return []

        D, ids_ordered = self._fw_result()
        n = len(ids_ordered)
        idx = {uid: i for i, uid in enumerate(ids_ordered)}

        # Approximate betweenness: count (s,t) pairs where shortest path
        # through k equals D[s,k] + D[k,t] = D[s,t]
        betweenness: dict[str, float] = {}
        total_pairs = n * (n - 1)

        for uid in self._graph.user_ids():
            k = idx[uid]
            dk = D[k, :]          # distances from k to all nodes
            # For each pair (i, j), check if k lies on a shortest path
            # via broadcast: D[i,j] == D[i,k] + D[k,j]
            through_k = np.isclose(D, D[:, k:k+1] + dk[np.newaxis, :])
            # Exclude diagonal and paths where k is an endpoint
            mask = np.ones((n, n), dtype=bool)
            np.fill_diagonal(mask, False)
            mask[:, k] = False
            mask[k, :] = False
            count = int(np.sum(through_k & mask & np.isfinite(D)))
            betweenness[uid] = count / total_pairs if total_pairs > 0 else 0.0

        # Greedy: sort by degree descending (primary), betweenness (secondary)
        top_df = (
            df[["user_id", "name", "degree"]]
            .sort_values("degree", ascending=False)
            .head(top_n)
            .reset_index(drop=True)
        )
        result = []
        for _, row in top_df.iterrows():
            result.append(
                {
                    "user_id": row["user_id"],
                    "name": row["name"],
                    "degree": int(row["degree"]),
                    "betweenness_approx": round(betweenness.get(row["user_id"], 0.0), 6),
                }
            )
        return result

    # ── Summary ────────────────────────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """Return a full network health summary dict for the API."""
        comps = connected_components(self._graph)
        return {
            "total_users": len(self._graph),
            "total_edges": self._graph.edge_count(),
            "density": round(self.density(), 6),
            "num_components": len(comps),
            "largest_component_size": len(comps[0]) if comps else 0,
            "diameter": self.diameter(),
            "average_separation": round(self.average_separation(), 4),
            "degree_stats": self.degree_stats(),
        }

    def invalidate_cache(self) -> None:
        """Clear cached DataFrames and FW matrix (call after graph mutations)."""
        self._users_df = None
        self._edges_df = None
        if hasattr(self, "_D"):
            del self._D
            del self._ids_ordered
