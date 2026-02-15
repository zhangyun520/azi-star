from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .diagnose import diagnose
from .state import State10D


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class EventRecord:
    event_id: int
    ts: str
    source: str
    content: str
    payload: dict[str, Any]


class EventStore:
    def __init__(self, db_path: str = "az_v2_events.db") -> None:
        self.db_path = Path(db_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    source TEXT NOT NULL,
                    content TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    ts TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES events(id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_decisions_event ON decisions(event_id)")
            conn.commit()
        finally:
            conn.close()

    def append_event(self, source: str, content: str, payload: dict[str, Any] | None = None) -> int:
        ts = _now_iso()
        pjson = json.dumps(payload or {}, ensure_ascii=False)
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT INTO events(ts, source, content, payload_json) VALUES(?, ?, ?, ?)",
                (ts, str(source), str(content), pjson),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def append_decision(self, event_id: int, result: dict[str, Any]) -> int:
        ts = _now_iso()
        rjson = json.dumps(result, ensure_ascii=False)
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT INTO decisions(event_id, ts, result_json) VALUES(?, ?, ?)",
                (int(event_id), ts, rjson),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def list_recent(self, limit: int = 20) -> list[EventRecord]:
        n = max(1, min(int(limit), 500))
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, ts, source, content, payload_json FROM events ORDER BY id DESC LIMIT ?",
                (n,),
            ).fetchall()
        finally:
            conn.close()
        out: list[EventRecord] = []
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"]))
            except Exception:
                payload = {}
            out.append(
                EventRecord(
                    event_id=int(row["id"]),
                    ts=str(row["ts"]),
                    source=str(row["source"]),
                    content=str(row["content"]),
                    payload=payload,
                )
            )
        return out


class AziEngineV2:
    def __init__(self, state: State10D | None = None, event_db_path: str = "az_v2_events.db") -> None:
        self.state = state or State10D()
        self.store = EventStore(event_db_path)

    def handle_input(
        self,
        content: str,
        *,
        source: str = "manual",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_id = self.store.append_event(source=source, content=content, payload=payload)
        result = diagnose(content, state=self.state)
        decision_id = self.store.append_decision(event_id, result)
        return {
            "event_id": event_id,
            "decision_id": decision_id,
            "result": result,
        }

    def snapshot(self, limit: int = 10) -> dict[str, Any]:
        return {
            "state": self.state.model_dump(mode="json"),
            "recent_events": [r.__dict__ for r in self.store.list_recent(limit=limit)],
        }

