"""Demo seeder — builds a realistic ~30-user social network.

Run from the backend/ directory:
    python seed.py

Idempotent: clears existing data before seeding, so re-running is safe.
Exercises every feature: mutual friends, BFS paths, recommendations,
community detection, analytics, influencer leaderboard, growth chart.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Windows: force UTF-8 output so unicode symbols don't crash cp1252
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.models.graph import FriendGraph
from app.models.requests import FriendRequestManager
from app.models.user import User
from app.storage.store import Store
from datetime import datetime, timezone, timedelta

# ── User data ──────────────────────────────────────────────────────────────────

USERS = [
    # id,        name,              age, city,          interests
    ("u01", "Alice Chen",       28,  "New York",    {"music", "hiking", "photography"}),
    ("u02", "Bob Martinez",     32,  "New York",    {"gaming", "music", "cooking"}),
    ("u03", "Carol Williams",   25,  "Los Angeles", {"yoga", "cooking", "travel"}),
    ("u04", "David Kim",        30,  "New York",    {"hiking", "coding", "music"}),
    ("u05", "Eve Johnson",      27,  "Los Angeles", {"music", "gaming", "art"}),
    ("u06", "Frank Lee",        35,  "Chicago",     {"hiking", "photography", "cooking"}),
    ("u07", "Grace Patel",      24,  "New York",    {"yoga", "art", "music"}),
    ("u08", "Henry Brown",      31,  "Chicago",     {"coding", "gaming", "music"}),
    ("u09", "Ivy Zhang",        26,  "Los Angeles", {"photography", "travel", "art"}),
    ("u10", "Jack Wilson",      29,  "New York",    {"coding", "hiking", "gaming"}),
    ("u11", "Kate Thompson",    33,  "Chicago",     {"cooking", "yoga", "travel"}),
    ("u12", "Liam Davis",       22,  "Houston",     {"gaming", "music", "coding"}),
    ("u13", "Maya Robinson",    28,  "Houston",     {"art", "photography", "travel"}),
    ("u14", "Noah Anderson",    36,  "New York",    {"hiking", "coding", "photography"}),
    ("u15", "Olivia White",     23,  "Los Angeles", {"music", "yoga", "art"}),
    ("u16", "Peter Harris",     34,  "Chicago",     {"cooking", "gaming", "coding"}),
    ("u17", "Quinn Lewis",      27,  "Houston",     {"travel", "music", "photography"}),
    ("u18", "Rachel Clark",     30,  "New York",    {"yoga", "hiking", "music"}),
    ("u19", "Sam Walker",       25,  "Los Angeles", {"coding", "gaming", "art"}),
    ("u20", "Tara Hall",        29,  "Chicago",     {"cooking", "travel", "photography"}),
    ("u21", "Uma Young",        31,  "Houston",     {"music", "hiking", "yoga"}),
    ("u22", "Victor Allen",     28,  "New York",    {"gaming", "coding", "music"}),
    ("u23", "Wendy King",       26,  "Los Angeles", {"art", "cooking", "travel"}),
    ("u24", "Xander Scott",     33,  "Chicago",     {"hiking", "photography", "coding"}),
    ("u25", "Yara Green",       24,  "Houston",     {"yoga", "art", "music"}),
    ("u26", "Zoe Baker",        30,  "New York",    {"travel", "photography", "hiking"}),
    ("u27", "Aaron Nelson",     27,  "Los Angeles", {"music", "gaming", "cooking"}),
    ("u28", "Bella Carter",     32,  "Chicago",     {"coding", "yoga", "art"}),
    ("u29", "Carlos Mitchell",  29,  "Houston",     {"hiking", "music", "travel"}),
    ("u30", "Diana Perez",      25,  "New York",    {"cooking", "art", "photography"}),
]

# ── Friendship edges (a, b, days_ago) ─────────────────────────────────────────
# Designed to create:
#  - A large NYC cluster
#  - LA and Chicago sub-clusters
#  - Cross-city bridges (for interesting BFS paths)
#  - A small Houston island (2 components total)

FRIENDSHIPS = [
    # NYC cluster
    ("u01","u02", 90), ("u01","u04", 85), ("u01","u07", 80),
    ("u02","u04", 75), ("u02","u10", 70), ("u02","u22", 65),
    ("u04","u10", 60), ("u04","u14", 55), ("u04","u18", 50),
    ("u07","u18", 45), ("u07","u30", 40), ("u10","u14", 35),
    ("u10","u22", 30), ("u14","u26", 25), ("u18","u26", 20),
    ("u22","u26", 15), ("u22","u30", 10),

    # LA cluster
    ("u03","u05", 88), ("u03","u09", 83), ("u03","u15", 78),
    ("u05","u09", 73), ("u05","u19", 68), ("u05","u27", 63),
    ("u09","u15", 58), ("u09","u23", 53), ("u15","u27", 48),
    ("u19","u23", 43), ("u19","u27", 38), ("u23","u27", 33),

    # Chicago cluster
    ("u06","u08", 86), ("u06","u11", 81), ("u06","u24", 76),
    ("u08","u16", 71), ("u08","u28", 66), ("u11","u16", 61),
    ("u11","u20", 56), ("u16","u24", 51), ("u20","u24", 46),
    ("u20","u28", 41), ("u24","u28", 36),

    # Houston sub-cluster (separate component)
    ("u12","u13", 84), ("u12","u17", 79), ("u12","u25", 74),
    ("u13","u17", 69), ("u13","u29", 64), ("u17","u21", 59),
    ("u21","u25", 54), ("u21","u29", 49), ("u25","u29", 44),

    # Cross-city bridges (NYC ↔ LA ↔ Chicago)
    ("u01","u03", 95), ("u04","u06", 92), ("u02","u08", 89),
    ("u10","u19", 72), ("u07","u15", 67), ("u14","u24", 62),
    ("u18","u11", 57), ("u22","u16", 52), ("u26","u20", 47),
    ("u30","u23", 42),
]


def seed():
    store = Store("social_graph.db")
    store.clear_all()

    graph = FriendGraph()
    mgr   = FriendRequestManager(graph)

    base_date = datetime.now(timezone.utc)
    timestamps: dict[tuple[str, str], datetime] = {}

    print("Seeding users…")
    for uid, name, age, city, interests in USERS:
        user = User(name=name, age=age, city=city, interests=interests, user_id=uid)
        graph.add_user(user)
    print(f"  ✓ {len(USERS)} users registered")

    print("Seeding friendships…")
    for a, b, days_ago in FRIENDSHIPS:
        try:
            graph.add_friend(a, b)
            key = (min(a, b), max(a, b))
            timestamps[key] = base_date - timedelta(days=days_ago)
        except Exception as e:
            print(f"  ⚠ {a}↔{b}: {e}")
    print(f"  ✓ {graph.edge_count()} friendships created")

    print("Seeding pending requests…")
    pending = [
        ("u12", "u01"),  # Houston → NYC bridge request (pending)
        ("u13", "u05"),  # Houston → LA bridge request (pending)
        ("u25", "u07"),  # Houston → NYC (pending)
    ]
    for from_id, to_id in pending:
        try:
            mgr.send_request(from_id, to_id)
        except Exception:
            pass
    print(f"  ✓ {mgr.total_pending()} pending requests queued")

    print("Persisting to SQLite…")
    store.save_state(graph, mgr, timestamps)
    print("  ✓ Saved to social_graph.db")

    # ── Summary ────────────────────────────────────────────────────────────────
    from app.services.analytics import NetworkAnalytics, connected_components
    an = NetworkAnalytics(graph, timestamps)
    s  = an.summary()
    comps = connected_components(graph)

    print("\n" + "─" * 50)
    print("  NETWORK SUMMARY")
    print("─" * 50)
    print(f"  Users:            {s['total_users']}")
    print(f"  Friendships:      {s['total_edges']}")
    print(f"  Density:          {s['density']:.4f}")
    print(f"  Components:       {s['num_components']}  ({', '.join(str(len(c))+' users' for c in comps)})")
    print(f"  Diameter:         {s['diameter']:.1f}")
    print(f"  Avg separation:   {s['average_separation']:.3f}")
    print(f"  Avg degree:       {s['degree_stats']['mean']:.2f}")
    print("─" * 50)
    print("\n  Top 5 most connected:")
    for row in an.most_connected(5).itertuples():
        print(f"    {row.name:<20} {row.degree} friends  ({row.city})")
    print("\n✅ Seed complete — start the API server and explore!\n")


if __name__ == "__main__":
    seed()
