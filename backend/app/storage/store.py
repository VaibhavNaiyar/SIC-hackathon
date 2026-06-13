"""SQLite persistence layer — save and reload the full graph state.

Design
------
* Uses the stdlib ``sqlite3`` module only — no ORM.
* All SQL uses **parameterised queries** (``?`` placeholders) — no string
  interpolation, no SQL injection risk.
* Writes are wrapped in explicit transactions so a crash mid-write leaves the
  database in its previous consistent state.
* ``load_state()`` fully rehydrates a ``FriendGraph`` + ``FriendRequestManager``
  from disk, so the server is stateless between restarts.

Schema
------
    users(id TEXT PK, name TEXT, age INTEGER, city TEXT, interests_json TEXT)
    friendships(user_a TEXT, user_b TEXT, created_at TEXT,
                PRIMARY KEY (user_a, user_b))
    requests(from_id TEXT, to_id TEXT, status TEXT, created_at TEXT,
             PRIMARY KEY (from_id, to_id))
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from app.errors import StorageError
from app.models.graph import FriendGraph
from app.models.requests import FriendRequest, FriendRequestManager, RequestStatus
from app.models.user import User


# ── DDL ────────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    age            INTEGER NOT NULL,
    city           TEXT NOT NULL,
    interests_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS friendships (
    user_a     TEXT NOT NULL,
    user_b     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_a, user_b)
);

CREATE TABLE IF NOT EXISTS requests (
    from_id    TEXT NOT NULL,
    to_id      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    PRIMARY KEY (from_id, to_id)
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Store ──────────────────────────────────────────────────────────────────────


class Store:
    """SQLite-backed persistence for the social graph.

    Args:
        db_path: Path to the ``.db`` file.  Pass ``":memory:"`` for an
                 in-memory database (useful for tests).
    """

    def __init__(self, db_path: str | Path = "social_graph.db") -> None:
        self.db_path = str(db_path)
        # In-memory databases lose all data when the connection closes, so we
        # keep a single persistent connection for the lifetime of the Store.
        self._persistent_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
            self._persistent_conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    # ── Schema ─────────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        """Create tables if they don't already exist."""
        try:
            with self._connect() as conn:
                conn.executescript(_DDL)
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to initialise schema: {exc}") from exc

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that yields a connection and commits on exit.

        For ``:memory:`` databases the persistent connection is reused;
        for file-based databases a fresh connection is opened per call.
        """
        if self._persistent_conn is not None:
            # Reuse the single in-memory connection — don't close it
            try:
                yield self._persistent_conn
                self._persistent_conn.commit()
            except sqlite3.Error as exc:
                self._persistent_conn.rollback()
                raise StorageError(f"Database error: {exc}") from exc
            return

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise StorageError(f"Database error: {exc}") from exc
        finally:
            conn.close()

    # ── Users ──────────────────────────────────────────────────────────────────

    def upsert_user(self, user: User) -> None:
        """Insert or replace a user record."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO users (id, name, age, city, interests_json)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name           = excluded.name,
                        age            = excluded.age,
                        city           = excluded.city,
                        interests_json = excluded.interests_json
                    """,
                    (
                        user.user_id,
                        user.name,
                        user.age,
                        user.city,
                        json.dumps(sorted(user.interests)),
                    ),
                )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"Failed to upsert user {user.user_id}: {exc}") from exc

    def delete_user(self, user_id: str) -> None:
        """Remove a user and all their associated friendships and requests."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
                conn.execute(
                    "DELETE FROM friendships WHERE user_a = ? OR user_b = ?",
                    (user_id, user_id),
                )
                conn.execute(
                    "DELETE FROM requests WHERE from_id = ? OR to_id = ?",
                    (user_id, user_id),
                )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"Failed to delete user {user_id}: {exc}") from exc

    # ── Friendships ────────────────────────────────────────────────────────────

    def upsert_friendship(
        self,
        a: str,
        b: str,
        created_at: str | None = None,
    ) -> None:
        """Persist a friendship edge (canonical order: smaller ID first)."""
        key = (min(a, b), max(a, b))
        ts = created_at or _now_iso()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO friendships (user_a, user_b, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_a, user_b) DO NOTHING
                    """,
                    (key[0], key[1], ts),
                )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"Failed to upsert friendship ({a},{b}): {exc}") from exc

    def delete_friendship(self, a: str, b: str) -> None:
        """Remove a friendship edge."""
        key = (min(a, b), max(a, b))
        try:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM friendships WHERE user_a = ? AND user_b = ?",
                    key,
                )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"Failed to delete friendship ({a},{b}): {exc}") from exc

    # ── Requests ───────────────────────────────────────────────────────────────

    def upsert_request(
        self,
        from_id: str,
        to_id: str,
        status: str = "PENDING",
        created_at: str | None = None,
    ) -> None:
        """Persist a friend request record."""
        ts = created_at or _now_iso()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO requests (from_id, to_id, status, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(from_id, to_id) DO UPDATE SET
                        status = excluded.status
                    """,
                    (from_id, to_id, status, ts),
                )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(
                f"Failed to upsert request {from_id}->{to_id}: {exc}"
            ) from exc

    def delete_request(self, from_id: str, to_id: str) -> None:
        """Remove a request record."""
        try:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM requests WHERE from_id = ? AND to_id = ?",
                    (from_id, to_id),
                )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(
                f"Failed to delete request {from_id}->{to_id}: {exc}"
            ) from exc

    # ── Bulk save / load ───────────────────────────────────────────────────────

    def save_state(
        self,
        graph: FriendGraph,
        request_manager: FriendRequestManager,
        timestamps: dict[tuple[str, str], datetime] | None = None,
    ) -> None:
        """Atomically persist the entire graph + pending requests.

        Replaces existing data with a full snapshot inside a single
        transaction to avoid partial writes.

        Args:
            graph:           The ``FriendGraph`` to persist.
            request_manager: The ``FriendRequestManager`` to persist.
            timestamps:      Optional edge → datetime mapping for growth charts.
        """
        try:
            with self._connect() as conn:
                # --- Users ---
                conn.execute("DELETE FROM users")
                for user in graph.users():
                    conn.execute(
                        "INSERT INTO users (id, name, age, city, interests_json) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            user.user_id,
                            user.name,
                            user.age,
                            user.city,
                            json.dumps(sorted(user.interests)),
                        ),
                    )

                # --- Friendships ---
                conn.execute("DELETE FROM friendships")
                seen: set[tuple[str, str]] = set()
                for uid in graph.user_ids():
                    for nid in graph.neighbors(uid):
                        key = (min(uid, nid), max(uid, nid))
                        if key in seen:
                            continue
                        seen.add(key)
                        ts_val = None
                        if timestamps:
                            ts_dt = timestamps.get(key)
                            ts_val = ts_dt.isoformat() if ts_dt else None
                        conn.execute(
                            "INSERT INTO friendships (user_a, user_b, created_at) "
                            "VALUES (?, ?, ?)",
                            (key[0], key[1], ts_val or _now_iso()),
                        )

                # --- Pending requests ---
                conn.execute("DELETE FROM requests")
                for uid in graph.user_ids():
                    for req in request_manager.pending_for(uid):
                        conn.execute(
                            "INSERT INTO requests (from_id, to_id, status, created_at) "
                            "VALUES (?, ?, ?, ?)",
                            (req.from_id, req.to_id, req.status.value, _now_iso()),
                        )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"save_state failed: {exc}") from exc

    def load_state(self) -> tuple[FriendGraph, FriendRequestManager, dict[tuple[str, str], datetime]]:
        """Rehydrate the full graph and request manager from SQLite.

        Returns:
            A 3-tuple: (FriendGraph, FriendRequestManager, timestamps_dict).
            ``timestamps_dict`` maps ``(user_a, user_b)`` → ``datetime``.

        Raises:
            StorageError: On any database error.
        """
        try:
            graph = FriendGraph()
            timestamps: dict[tuple[str, str], datetime] = {}

            with self._connect() as conn:
                # --- Load users ---
                for row in conn.execute("SELECT * FROM users"):
                    interests = set(json.loads(row["interests_json"]))
                    user = User(
                        name=row["name"],
                        age=row["age"],
                        city=row["city"],
                        interests=interests,
                        user_id=row["id"],
                    )
                    graph.add_user(user)

                # --- Load friendships ---
                for row in conn.execute("SELECT * FROM friendships"):
                    a, b = row["user_a"], row["user_b"]
                    # Guard: both users must have loaded successfully
                    if graph.has_user(a) and graph.has_user(b):
                        if not graph.are_friends(a, b):
                            graph.add_friend(a, b)
                        key = (min(a, b), max(a, b))
                        if row["created_at"]:
                            try:
                                timestamps[key] = datetime.fromisoformat(
                                    row["created_at"]
                                )
                            except ValueError:
                                pass

                # --- Load pending requests ---
                mgr = FriendRequestManager(graph)
                for row in conn.execute(
                    "SELECT * FROM requests WHERE status = 'PENDING' ORDER BY created_at"
                ):
                    from_id, to_id = row["from_id"], row["to_id"]
                    if not (graph.has_user(from_id) and graph.has_user(to_id)):
                        continue
                    # Re-create the pending entry without going through guards
                    # (the state is already validated — we're just reloading it)
                    req = FriendRequest(from_id=from_id, to_id=to_id)
                    mgr._incoming.setdefault(to_id, __import__("collections").deque()).append(req)
                    mgr._sent_by.setdefault(from_id, set()).add(to_id)

            return graph, mgr, timestamps

        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"load_state failed: {exc}") from exc

    # ── Utility ────────────────────────────────────────────────────────────────

    def clear_all(self) -> None:
        """Wipe all tables (useful for tests and seeding)."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM requests")
                conn.execute("DELETE FROM friendships")
                conn.execute("DELETE FROM users")
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"clear_all failed: {exc}") from exc

    def friendship_timestamps(self) -> dict[tuple[str, str], datetime]:
        """Return all stored friendship timestamps as a dict."""
        result: dict[tuple[str, str], datetime] = {}
        try:
            with self._connect() as conn:
                for row in conn.execute("SELECT user_a, user_b, created_at FROM friendships"):
                    if row["created_at"]:
                        try:
                            result[(row["user_a"], row["user_b"])] = datetime.fromisoformat(
                                row["created_at"]
                            )
                        except ValueError:
                            pass
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"friendship_timestamps failed: {exc}") from exc
        return result
