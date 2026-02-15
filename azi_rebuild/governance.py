from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


HIGH_RISK_KEYWORDS = {
    "delete",
    "drop table",
    "rm -rf",
    "format",
    "shutdown",
    "override policy",
    "destructive",
    "生产",
    "删除",
    "覆盖",
    "重置",
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def ensure_governance_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_risk_gate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            requires_approval INTEGER NOT NULL DEFAULT 0,
            approved INTEGER NOT NULL DEFAULT 0,
            reason_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_risk_gate_event ON azi_risk_gate(event_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            risk_gate_id INTEGER NOT NULL,
            approver TEXT NOT NULL,
            decision TEXT NOT NULL,
            note TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_approvals_gate ON azi_approvals(risk_gate_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_guard_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            guard_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            detail TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_guard_events_type ON azi_guard_events(guard_type)")
    conn.commit()


def assess_risk(
    *,
    event_id: int,
    action: str,
    content: str,
    source: str,
    source_trust: float = 0.6,
) -> dict[str, Any]:
    text = f"{str(action or '')} {str(content or '')}".lower()
    reasons: list[str] = []
    score = 0.0

    for kw in HIGH_RISK_KEYWORDS:
        if kw in text:
            score += 0.35
            reasons.append(f"keyword:{kw}")
    if source_trust < 0.45:
        score += 0.20
        reasons.append("low_source_trust")
    if str(source).lower().startswith(("web", "social", "device")):
        score += 0.10
        reasons.append("untrusted_input_surface")

    if score >= 0.55:
        level = "high"
    elif score >= 0.25:
        level = "mid"
    else:
        level = "low"
    requires_approval = level == "high"
    return {
        "event_id": int(event_id),
        "risk_level": level,
        "requires_approval": requires_approval,
        "reasons": reasons,
    }


def record_risk_gate(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    action: str,
    risk_level: str,
    requires_approval: bool,
    approved: bool,
    reasons: list[str],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO azi_risk_gate(ts, event_id, action, risk_level, requires_approval, approved, reason_json)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            int(event_id),
            str(action),
            str(risk_level),
            1 if requires_approval else 0,
            1 if approved else 0,
            json.dumps({"reasons": reasons}, ensure_ascii=False),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def load_approval_override(base_dir: Path | str, event_id: int) -> bool:
    path = Path(base_dir) / "resident_output" / "approvals.json"
    if not path.exists() or not path.is_file():
        return False
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception:
        return False
    if not isinstance(obj, dict):
        return False
    approved_events = {int(x) for x in list(obj.get("approved_event_ids", []) or []) if str(x).isdigit()}
    return int(event_id) in approved_events


def check_immutable_guard(content: str, immutable_paths: list[str]) -> dict[str, Any]:
    text = str(content or "").lower()
    hits = []
    for p in immutable_paths:
        if str(p).lower() in text:
            hits.append(str(p))
    blocked = bool(hits)
    return {"blocked": blocked, "hits": hits}


def record_guard_event(conn: sqlite3.Connection, guard_type: str, severity: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO azi_guard_events(ts, guard_type, severity, detail) VALUES(?, ?, ?, ?)",
        (now_iso(), str(guard_type), str(severity), str(detail)[:1000]),
    )
    conn.commit()


def emergence_guard(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT action FROM azi_decisions
        ORDER BY id DESC
        LIMIT 6
        """
    ).fetchall()
    actions = [str(r["action"] or "") for r in rows]
    if len(actions) < 4:
        return {"alert": False, "reason": None}
    top = actions[0]
    repeat = sum(1 for x in actions if x == top)
    if repeat >= 5:
        reason = f"repeated_action_loop:{top}"
        record_guard_event(conn, "emergence", "warn", reason)
        return {"alert": True, "reason": reason}
    return {"alert": False, "reason": None}
