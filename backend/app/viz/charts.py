"""Matplotlib chart generation — headless PNG charts returned as base64.

Every public function accepts data (pre-computed by ``NetworkAnalytics``) and
returns a ``base64``-encoded PNG string ready to embed directly in a JSON API
response or an ``<img src="data:image/png;base64,...">`` tag.

``matplotlib.use("Agg")`` is called at import time so no display is needed.
"""

from __future__ import annotations

import base64
import io
from typing import Any

import matplotlib
matplotlib.use("Agg")  # headless — must come before pyplot import

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd


# ── Internal helper ────────────────────────────────────────────────────────────


def _fig_to_b64(fig: plt.Figure) -> str:
    """Render *fig* to a PNG in memory and return as a base64 string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


# ── Chart 1 — Top-N most connected users (bar chart) ──────────────────────────


def chart_top_connected(most_connected_df: pd.DataFrame, top_n: int = 10) -> str:
    """Bar chart: top-N users by degree (friend count).

    Args:
        most_connected_df: DataFrame with columns ``name``, ``degree``.
        top_n:             Maximum bars to show.

    Returns:
        Base64-encoded PNG string.
    """
    df = most_connected_df.head(top_n)
    if df.empty:
        return _empty_chart("No users in network")

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = plt.cm.Blues(np.linspace(0.4, 0.9, len(df)))[::-1]
    bars = ax.barh(df["name"][::-1], df["degree"][::-1], color=colors, edgecolor="white")

    # Value labels
    for bar, val in zip(bars, df["degree"][::-1]):
        ax.text(
            bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2,
            str(int(val)), va="center", ha="left", fontsize=9
        )

    ax.set_xlabel("Number of Friends", fontsize=11)
    ax.set_title("Most Connected Users", fontsize=13, fontweight="bold", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlim(0, df["degree"].max() * 1.15 + 1)
    fig.tight_layout()
    return _fig_to_b64(fig)


# ── Chart 2 — City distribution (horizontal bar / pie) ────────────────────────


def chart_city_distribution(city_df: pd.DataFrame) -> str:
    """Horizontal bar chart of user count by city with percentage labels.

    Args:
        city_df: DataFrame with columns ``city``, ``count``, ``percentage``.

    Returns:
        Base64-encoded PNG string.
    """
    if city_df.empty:
        return _empty_chart("No city data")

    fig, ax = plt.subplots(figsize=(9, max(4, len(city_df) * 0.55)))
    palette = plt.cm.Set3(np.linspace(0, 1, len(city_df)))
    bars = ax.barh(
        city_df["city"][::-1],
        city_df["count"][::-1],
        color=palette[::-1],
        edgecolor="white",
    )

    for bar, pct in zip(bars, city_df["percentage"][::-1]):
        ax.text(
            bar.get_width() + 0.05,
            bar.get_y() + bar.get_height() / 2,
            f"{int(bar.get_width())}  ({pct:.1f}%)",
            va="center", ha="left", fontsize=9,
        )

    ax.set_xlabel("Users", fontsize=11)
    ax.set_title("Users by City", fontsize=13, fontweight="bold", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlim(0, city_df["count"].max() * 1.25 + 1)
    fig.tight_layout()
    return _fig_to_b64(fig)


# ── Chart 3 — Friendship growth over time (line chart) ────────────────────────


def chart_friendship_growth(growth_df: pd.DataFrame) -> str:
    """Line chart of cumulative friendship count over time.

    Args:
        growth_df: DataFrame with columns ``created_at``, ``cumulative_edges``.

    Returns:
        Base64-encoded PNG string.
    """
    if growth_df.empty:
        return _empty_chart("No timestamp data available")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        growth_df["created_at"],
        growth_df["cumulative_edges"],
        color="#4C72B0",
        linewidth=2.5,
        marker="o",
        markersize=4,
        markerfacecolor="white",
        markeredgewidth=1.5,
    )
    ax.fill_between(
        growth_df["created_at"],
        growth_df["cumulative_edges"],
        alpha=0.15,
        color="#4C72B0",
    )

    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Total Friendships", fontsize=11)
    ax.set_title("Friendship Growth Over Time", fontsize=13, fontweight="bold", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_to_b64(fig)


# ── Chart 4 — Network spring-layout graph (small graphs, ≤ 60 nodes) ──────────


def chart_network_graph(
    nodes: list[dict[str, Any]],
    edges: list[tuple[str, str]],
    community_labels: dict[str, int] | None = None,
) -> str:
    """Spring-layout visualisation of the friendship network.

    Uses a hand-rolled Fruchterman-Reingold-style force layout (no networkx)
    so the DSA constraint is respected.

    Args:
        nodes:            List of ``{id, name}`` dicts.
        edges:            List of ``(id_a, id_b)`` tuples.
        community_labels: Optional ``{user_id: community_int}`` for colouring.

    Returns:
        Base64-encoded PNG string.
    """
    if not nodes:
        return _empty_chart("No users in network")

    n = len(nodes)
    ids = [nd["id"] for nd in nodes]
    names = {nd["id"]: nd["name"] for nd in nodes}
    idx = {uid: i for i, uid in enumerate(ids)}

    # ── Spring layout (force-directed, hand-rolled) ────────────────────────────
    rng = np.random.default_rng(42)
    pos = rng.uniform(-1, 1, (n, 2))

    k = 1.0 / max(np.sqrt(n), 1)  # optimal distance
    iterations = min(50, 10 + n)

    for _ in range(iterations):
        delta = np.zeros_like(pos)

        # Repulsive forces between all pairs
        for i in range(n):
            diff = pos[i] - pos          # (n, 2)
            dist = np.linalg.norm(diff, axis=1, keepdims=True)
            dist = np.where(dist < 1e-6, 1e-6, dist)
            repulse = diff / (dist ** 2) * (k ** 2)
            repulse[i] = 0
            delta[i] += repulse.sum(axis=0)

        # Attractive forces along edges
        for a, b in edges:
            if a not in idx or b not in idx:
                continue
            i, j = idx[a], idx[b]
            diff = pos[i] - pos[j]
            dist = max(np.linalg.norm(diff), 1e-6)
            force = diff / dist * (dist ** 2 / k)
            delta[i] -= force
            delta[j] += force

        # Limit displacement and update
        disp_norm = np.linalg.norm(delta, axis=1, keepdims=True)
        disp_norm = np.where(disp_norm < 1e-6, 1e-6, disp_norm)
        step = min(0.1, 1.0 / (_ + 1))
        pos += delta / disp_norm * np.minimum(disp_norm, step)

    # ── Colour by community ────────────────────────────────────────────────────
    cmap = plt.cm.tab20
    if community_labels:
        num_communities = max(community_labels.values()) + 1
        node_colors = [
            cmap(community_labels.get(uid, 0) / max(num_communities, 1))
            for uid in ids
        ]
    else:
        node_colors = [cmap(0.1)] * n

    # ── Draw ───────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#1a1a2e")

    # Edges
    for a, b in edges:
        if a not in idx or b not in idx:
            continue
        i, j = idx[a], idx[b]
        ax.plot(
            [pos[i, 0], pos[j, 0]],
            [pos[i, 1], pos[j, 1]],
            color="#aaaaaa", linewidth=0.8, alpha=0.5, zorder=1,
        )

    # Nodes
    sc = ax.scatter(
        pos[:, 0], pos[:, 1],
        s=200, c=node_colors, zorder=2,
        edgecolors="white", linewidths=0.8,
    )

    # Labels (only if not too crowded)
    if n <= 30:
        for i, uid in enumerate(ids):
            ax.text(
                pos[i, 0], pos[i, 1] + 0.07,
                names[uid], ha="center", va="bottom",
                fontsize=7, color="white", zorder=3,
            )

    ax.set_title(
        f"Social Network Graph  ({n} users, {len(edges)} edges)",
        fontsize=12, fontweight="bold", color="white", pad=10,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Community legend (up to 8 entries)
    if community_labels:
        unique = sorted(set(community_labels.values()))[:8]
        handles = [
            mpatches.Patch(
                color=cmap(c / max(len(unique), 1)),
                label=f"Community {c}",
            )
            for c in unique
        ]
        ax.legend(
            handles=handles, loc="lower right", fontsize=8,
            facecolor="#2a2a4e", edgecolor="none", labelcolor="white",
        )

    fig.tight_layout()
    return _fig_to_b64(fig)


# ── Chart 5 — Degree distribution histogram ───────────────────────────────────


def chart_degree_distribution(users_df: pd.DataFrame) -> str:
    """Histogram of the degree (friend count) distribution across all users.

    Args:
        users_df: DataFrame with a ``degree`` column.

    Returns:
        Base64-encoded PNG string.
    """
    if users_df.empty:
        return _empty_chart("No users in network")

    fig, ax = plt.subplots(figsize=(8, 5))
    degrees = users_df["degree"].values
    max_deg = int(degrees.max()) if len(degrees) > 0 else 1
    bins = range(0, max_deg + 2)

    ax.hist(degrees, bins=bins, color="#55a868", edgecolor="white", align="left")
    ax.set_xlabel("Degree (Number of Friends)", fontsize=11)
    ax.set_ylabel("Number of Users", fontsize=11)
    ax.set_title("Degree Distribution", fontsize=13, fontweight="bold", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    fig.tight_layout()
    return _fig_to_b64(fig)


# ── Fallback ───────────────────────────────────────────────────────────────────


def _empty_chart(message: str = "No data") -> str:
    """Return a base64 PNG with a centred 'no data' message."""
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=13, color="#888888", transform=ax.transAxes)
    ax.set_axis_off()
    fig.tight_layout()
    return _fig_to_b64(fig)


# ── Dispatcher ─────────────────────────────────────────────────────────────────

CHART_KINDS = frozenset([
    "top_connected",
    "city_distribution",
    "friendship_growth",
    "network_graph",
    "degree_distribution",
])
