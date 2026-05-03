# Structured memory layer — SQLite-backed, Memori-style classification
# Categories: fact, preference, rule, summary, episode

import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import settings

log = logging.getLogger(__name__)


class MemoriStore:
    def __init__(self, db_path: Path = settings.MEMORY_DB):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category    TEXT NOT NULL,
                key         TEXT,
                content     TEXT NOT NULL,
                context     TEXT,
                metadata    TEXT DEFAULT '{}',
                confidence  REAL DEFAULT 1.0,
                accepts     INTEGER DEFAULT 0,
                declines    INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                accessed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_category ON memories(category);
            CREATE INDEX IF NOT EXISTS idx_key ON memories(key);

            CREATE TABLE IF NOT EXISTS episodes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                summary     TEXT NOT NULL,
                user_msg    TEXT,
                edis_msg    TEXT,
                tools_used  TEXT DEFAULT '[]',
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_time ON episodes(created_at);

            CREATE TABLE IF NOT EXISTS preferences (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                context_type TEXT NOT NULL,
                actions     TEXT NOT NULL,
                confidence  REAL DEFAULT 1.0,
                accepts     INTEGER DEFAULT 1,
                declines    INTEGER DEFAULT 0,
                last_offered TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pref_context ON preferences(context_type);
        """)
        self._conn.commit()

    # ── Memories ──────────────────────────────────────────────────────────────

    def get_by_id(self, memory_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return dict(row) if row else None

    def add(self, category: str, content: str, key: str = None,
            context: str = None, metadata: dict = None, confidence: float = 1.0) -> int:
        now = datetime.now().isoformat()
        cur = self._conn.execute(
            """INSERT INTO memories (category, key, content, context, metadata,
               confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (category, key, content, context,
             json.dumps(metadata or {}), confidence, now, now)
        )
        self._conn.commit()
        return cur.lastrowid

    def get(self, category: str = None, key: str = None, limit: int = 20) -> list[dict]:
        query = "SELECT * FROM memories WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if key:
            query += " AND key = ?"
            params.append(key)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def search(self, text: str, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            """SELECT * FROM memories
               WHERE content LIKE ? OR key LIKE ? OR context LIKE ?
               ORDER BY updated_at DESC LIMIT ?""",
            (f"%{text}%", f"%{text}%", f"%{text}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def update(self, memory_id: int, content: str = None, confidence: float = None):
        now = datetime.now().isoformat()
        if content:
            self._conn.execute(
                "UPDATE memories SET content=?, updated_at=? WHERE id=?",
                (content, now, memory_id)
            )
        if confidence is not None:
            self._conn.execute(
                "UPDATE memories SET confidence=?, updated_at=? WHERE id=?",
                (confidence, now, memory_id)
            )
        self._conn.commit()

    def delete(self, memory_id: int):
        self._conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        self._conn.commit()

    # ── Episodes ──────────────────────────────────────────────────────────────

    def add_episode(self, summary: str, user_msg: str = None,
                    edis_msg: str = None, tools_used: list = None) -> int:
        now = datetime.now().isoformat()
        cur = self._conn.execute(
            """INSERT INTO episodes (summary, user_msg, edis_msg, tools_used, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (summary, user_msg, edis_msg, json.dumps(tools_used or []), now)
        )
        self._conn.commit()
        # trim old episodes
        self._conn.execute(
            """DELETE FROM episodes WHERE id NOT IN
               (SELECT id FROM episodes ORDER BY created_at DESC LIMIT ?)""",
            (settings.MEMORY_MAX_EPISODES,)
        )
        self._conn.commit()
        return cur.lastrowid

    def get_episodes(self, limit: int = 10) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Preferences (context-based learned behaviors) ─────────────────────────

    def get_preference(self, context_type: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM preferences WHERE context_type=?", (context_type,)
        ).fetchone()
        return dict(row) if row else None

    def set_preference(self, context_type: str, actions: list):
        now = datetime.now().isoformat()
        existing = self.get_preference(context_type)
        if existing:
            self._conn.execute(
                """UPDATE preferences SET actions=?, updated_at=? WHERE context_type=?""",
                (json.dumps(actions), now, context_type)
            )
        else:
            self._conn.execute(
                """INSERT INTO preferences
                   (context_type, actions, confidence, accepts, created_at, updated_at)
                   VALUES (?, ?, 1.0, 1, ?, ?)""",
                (context_type, json.dumps(actions), now, now)
            )
        self._conn.commit()

    def record_preference_outcome(self, context_type: str, accepted: bool):
        now = datetime.now().isoformat()
        if accepted:
            self._conn.execute(
                """UPDATE preferences SET accepts=accepts+1,
                   confidence=MIN(1.0, confidence+0.1), last_offered=?, updated_at=?
                   WHERE context_type=?""",
                (now, now, context_type)
            )
        else:
            self._conn.execute(
                """UPDATE preferences SET declines=declines+1,
                   confidence=MAX(0.0, confidence-0.15), last_offered=?, updated_at=?
                   WHERE context_type=?""",
                (now, now, context_type)
            )
        self._conn.commit()

    def all_preferences(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM preferences ORDER BY confidence DESC").fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()


_store: MemoriStore | None = None


def get_store() -> MemoriStore:
    global _store
    if _store is None:
        _store = MemoriStore()
    return _store
