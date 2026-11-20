"""SQLite persistence for the harness (memory items, working turns, summaries, episodes, agent runs).

Separate from the business database on purpose: the backend only passes a file path.
Use ":memory:" for tests. Thread-safe via a single connection + lock.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from agents.harness.memory.models import Episode, MemoryItem, WorkingTurn

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL, namespace TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
  status TEXT NOT NULL, source TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '',
  confidence REAL NOT NULL DEFAULT 1.0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mem_user ON memory_items(user_id, namespace, status);
CREATE TABLE IF NOT EXISTS working_turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL, agent TEXT NOT NULL, session TEXT NOT NULL,
  role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_turn ON working_turns(user_id, agent, session, id);
CREATE TABLE IF NOT EXISTS working_summaries (
  user_id TEXT NOT NULL, agent TEXT NOT NULL, session TEXT NOT NULL,
  summary TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, agent, session)
);
CREATE TABLE IF NOT EXISTS episodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL, agent TEXT NOT NULL, spec_id TEXT NOT NULL, session TEXT NOT NULL,
  summary TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_episode ON episodes(user_id, agent, id);
CREATE TABLE IF NOT EXISTS agent_runs (
  run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, agent TEXT NOT NULL, spec_id TEXT NOT NULL,
  status TEXT NOT NULL, started_at TEXT NOT NULL, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_run ON agent_runs(user_id, started_at);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLiteMemoryStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            if self.path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------ memory items
    @staticmethod
    def _item(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(**{k: row[k] for k in row.keys()})

    def add_item(self, user_id: str, namespace: str, key: str, value: str, status: str,
                 source: str = "", evidence: str = "", confidence: float = 1.0) -> MemoryItem:
        ts = now()
        cur = self._exec(
            "INSERT INTO memory_items(user_id, namespace, key, value, status, source, evidence, confidence,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, namespace, key, value, status, source, evidence, confidence, ts, ts))
        return self.get_item(cur.lastrowid)

    def get_item(self, item_id: int) -> MemoryItem | None:
        rows = self._all("SELECT * FROM memory_items WHERE id=?", (item_id,))
        return self._item(rows[0]) if rows else None

    def list_items(self, user_id: str, namespaces: tuple[str, ...] | list[str] | None = None,
                   statuses: tuple[str, ...] | list[str] | None = None, key: str | None = None,
                   limit: int = 200) -> list[MemoryItem]:
        sql, params = "SELECT * FROM memory_items WHERE user_id=?", [user_id]
        if namespaces is not None:
            if not namespaces:
                return []
            sql += f" AND namespace IN ({','.join('?' * len(namespaces))})"
            params += list(namespaces)
        if statuses:
            sql += f" AND status IN ({','.join('?' * len(statuses))})"
            params += list(statuses)
        if key is not None:
            sql += " AND key=?"
            params.append(key)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(limit)
        return [self._item(r) for r in self._all(sql, tuple(params))]

    def update_item(self, item_id: int, **fields) -> MemoryItem | None:
        allowed = {"value", "status", "evidence", "confidence", "key", "source"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at=?"
            self._exec(f"UPDATE memory_items SET {sets} WHERE id=?", (*fields.values(), now(), item_id))
        return self.get_item(item_id)

    # ------------------------------------------------------------ working memory
    def add_turn(self, user_id: str, agent: str, session: str, role: str, content: str) -> None:
        self._exec("INSERT INTO working_turns(user_id, agent, session, role, content, created_at)"
                   " VALUES (?,?,?,?,?,?)", (user_id, agent, session, role, content, now()))

    def list_turns(self, user_id: str, agent: str, session: str) -> list[WorkingTurn]:
        rows = self._all("SELECT id, role, content, created_at FROM working_turns"
                         " WHERE user_id=? AND agent=? AND session=? ORDER BY id", (user_id, agent, session))
        return [WorkingTurn(id=r["id"], role=r["role"], content=r["content"], created_at=r["created_at"])
                for r in rows]

    def delete_turns(self, ids: list[int]) -> None:
        if ids:
            self._exec(f"DELETE FROM working_turns WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))

    def get_summary(self, user_id: str, agent: str, session: str) -> str:
        rows = self._all("SELECT summary FROM working_summaries WHERE user_id=? AND agent=? AND session=?",
                         (user_id, agent, session))
        return rows[0]["summary"] if rows else ""

    def set_summary(self, user_id: str, agent: str, session: str, summary: str) -> None:
        self._exec("INSERT INTO working_summaries(user_id, agent, session, summary, updated_at) VALUES (?,?,?,?,?)"
                   " ON CONFLICT(user_id, agent, session) DO UPDATE SET summary=excluded.summary,"
                   " updated_at=excluded.updated_at", (user_id, agent, session, summary, now()))

    def clear_session(self, user_id: str, agent: str, session: str) -> None:
        self._exec("DELETE FROM working_turns WHERE user_id=? AND agent=? AND session=?", (user_id, agent, session))
        self._exec("DELETE FROM working_summaries WHERE user_id=? AND agent=? AND session=?",
                   (user_id, agent, session))

    def delete_user_data(self, user_id: str) -> None:
        """Erase all persisted memory and audit records for a deleted account."""
        with self._lock:
            for table in ("memory_items", "working_turns", "working_summaries", "episodes", "agent_runs"):
                self._conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
            self._conn.commit()

    # ------------------------------------------------------------ episodes
    def add_episode(self, user_id: str, agent: str, spec_id: str, session: str, summary: str, status: str) -> None:
        self._exec("INSERT INTO episodes(user_id, agent, spec_id, session, summary, status, created_at)"
                   " VALUES (?,?,?,?,?,?,?)", (user_id, agent, spec_id, session, summary, status, now()))

    def list_episodes(self, user_id: str, agents: list[str] | None = None, limit: int = 50) -> list[Episode]:
        sql, params = "SELECT * FROM episodes WHERE user_id=?", [user_id]
        if agents:
            sql += f" AND agent IN ({','.join('?' * len(agents))})"
            params += agents
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [Episode(**{k: r[k] for k in r.keys()}) for r in self._all(sql, tuple(params))]

    # ------------------------------------------------------------ agent runs
    def record_run(self, run: dict) -> None:
        self._exec("INSERT OR REPLACE INTO agent_runs(run_id, user_id, agent, spec_id, status, started_at, data)"
                   " VALUES (?,?,?,?,?,?,?)",
                   (run["run_id"], run["user_id"], run["agent"], run["spec_id"], run["status"],
                    run["started_at"], json.dumps(run, ensure_ascii=False, default=str)))

    def list_runs(self, user_id: str, limit: int = 30) -> list[dict]:
        rows = self._all("SELECT data FROM agent_runs WHERE user_id=? ORDER BY started_at DESC, rowid DESC LIMIT ?",
                         (user_id, limit))
        return [json.loads(r["data"]) for r in rows]
