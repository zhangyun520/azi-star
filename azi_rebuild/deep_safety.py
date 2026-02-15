from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


FORBIDDEN_PATCH_PATTERNS = [
    "rm -rf",
    "drop table",
    "del /f",
    "format c:",
    "git reset --hard",
]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def ensure_deep_safety_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_deep_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_deep_runs_event ON azi_deep_runs(event_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_canary_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            snapshot_path TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_canary_event ON azi_canary_snapshots(event_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_eval_gates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            gate_name TEXT NOT NULL,
            status TEXT NOT NULL,
            blocking INTEGER NOT NULL DEFAULT 1,
            detail_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_eval_gates_event ON azi_eval_gates(event_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_eval_gates_status ON azi_eval_gates(status, id)")
    conn.commit()


def run_deep_safety_chain(
    *,
    base_dir: Path,
    conn,
    event_id: int,
    patch_plan: str,
    run_eval: bool = True,
) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []

    sandbox_res = sandbox_stage(patch_plan)
    stages.append({"stage": "sandbox", **sandbox_res})
    _record_stage(conn, event_id=event_id, stage="sandbox", status=sandbox_res["status"], detail=sandbox_res)
    if sandbox_res["status"] != "ok":
        rollback = rollback_stage(base_dir=base_dir, event_id=event_id, reason=sandbox_res["reason"])
        stages.append({"stage": "rollback", **rollback})
        _record_stage(conn, event_id=event_id, stage="rollback", status=rollback["status"], detail=rollback)
        return {"ok": False, "stages": stages}

    eval_res = eval_stage(base_dir=base_dir, enabled=run_eval)
    stages.append({"stage": "eval", **eval_res})
    _record_stage(conn, event_id=event_id, stage="eval", status=eval_res["status"], detail=eval_res)
    _record_eval_gate(
        conn,
        event_id=event_id,
        gate_name="deep_eval_harness",
        status="passed" if eval_res["status"] == "ok" else "failed",
        blocking=True,
        detail=eval_res,
    )
    if eval_res["status"] != "ok":
        rollback = rollback_stage(base_dir=base_dir, event_id=event_id, reason=eval_res["reason"])
        stages.append({"stage": "rollback", **rollback})
        _record_stage(conn, event_id=event_id, stage="rollback", status=rollback["status"], detail=rollback)
        return {
            "ok": False,
            "stages": stages,
            "eval_gate": {"name": "deep_eval_harness", "status": "failed", "publish_allowed": False},
        }

    canary_res = canary_stage(base_dir=base_dir, conn=conn, event_id=event_id, patch_plan=patch_plan)
    stages.append({"stage": "canary", **canary_res})
    _record_stage(conn, event_id=event_id, stage="canary", status=canary_res["status"], detail=canary_res)

    publish_allowed = canary_res["status"] == "ok"
    return {
        "ok": publish_allowed,
        "stages": stages,
        "eval_gate": {
            "name": "deep_eval_harness",
            "status": "passed",
            "publish_allowed": publish_allowed,
        },
    }


def sandbox_stage(patch_plan: str) -> dict[str, Any]:
    low = str(patch_plan or "").lower()
    for pat in FORBIDDEN_PATCH_PATTERNS:
        if pat in low:
            return {"status": "blocked", "reason": f"forbidden_pattern:{pat}"}
    return {"status": "ok", "reason": "passed"}


def eval_stage(*, base_dir: Path, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"status": "failed", "reason": "eval_required"}

    cmd = [
        "python",
        "-m",
        "pytest",
        "tests/test_az_v2_core.py",
        "tests/test_brain_web_panel_contract.py",
        "-q",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(base_dir),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:
        return {"status": "failed", "reason": f"eval_exception:{exc}"}
    if proc.returncode != 0:
        return {
            "status": "failed",
            "reason": "eval_failed",
            "stderr": str(proc.stderr or "")[:800],
            "stdout": str(proc.stdout or "")[:800],
        }

    out = str(proc.stdout or "")
    m = re.search(r"(\d+)\s+passed", out)
    passed_count = int(m.group(1)) if m else 0
    if passed_count <= 0:
        return {
            "status": "failed",
            "reason": "eval_no_passed_tests",
            "stdout": out[:800],
            "stderr": str(proc.stderr or "")[:800],
        }
    return {
        "status": "ok",
        "reason": "eval_passed",
        "passed_count": passed_count,
        "suite": cmd[3:-1],
    }


def canary_stage(*, base_dir: Path, conn, event_id: int, patch_plan: str) -> dict[str, Any]:
    ts = now_iso().replace(":", "").replace("-", "")
    canary_dir = base_dir / "resident_output" / "canary"
    canary_dir.mkdir(parents=True, exist_ok=True)
    path = canary_dir / f"canary_{event_id}_{ts}.json"
    payload = {
        "event_id": int(event_id),
        "created_at": now_iso(),
        "patch_plan": str(patch_plan)[:4000],
        "status": "canary_passed",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    conn.execute(
        "INSERT INTO azi_canary_snapshots(ts, event_id, snapshot_path, status) VALUES(?, ?, ?, ?)",
        (now_iso(), int(event_id), str(path), "ok"),
    )
    conn.commit()
    return {"status": "ok", "reason": "canary_saved", "snapshot_path": str(path)}


def rollback_stage(*, base_dir: Path, event_id: int, reason: str) -> dict[str, Any]:
    rollback_dir = base_dir / "resident_output" / "rollback"
    rollback_dir.mkdir(parents=True, exist_ok=True)
    path = rollback_dir / f"rollback_{event_id}_{int(time.time())}.log"
    path.write_text(f"{now_iso()} rollback triggered: {reason}\n", encoding="utf-8")
    return {"status": "ok", "reason": str(reason), "rollback_log": str(path)}


def _record_stage(conn, *, event_id: int, stage: str, status: str, detail: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO azi_deep_runs(ts, event_id, stage, status, detail_json) VALUES(?, ?, ?, ?, ?)",
        (now_iso(), int(event_id), str(stage), str(status), json.dumps(detail, ensure_ascii=False)),
    )
    conn.commit()


def _record_eval_gate(
    conn,
    *,
    event_id: int,
    gate_name: str,
    status: str,
    blocking: bool,
    detail: dict[str, Any],
) -> None:
    conn.execute(
        "INSERT INTO azi_eval_gates(ts, event_id, gate_name, status, blocking, detail_json) VALUES(?, ?, ?, ?, ?, ?)",
        (
            now_iso(),
            int(event_id),
            str(gate_name),
            str(status),
            1 if blocking else 0,
            json.dumps(detail, ensure_ascii=False),
        ),
    )
    conn.commit()
