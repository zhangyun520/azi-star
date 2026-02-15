from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def new_run_id() -> str:
    return f"run_{int(time.time())}_{uuid.uuid4().hex[:8]}"


def ensure_data_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")


def append_trace(path: Path, payload: dict[str, Any]) -> None:
    ensure_data_file(path)
    record = dict(payload)
    record.setdefault("ts", now_iso())
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_event(
    *,
    path: Path,
    run_id: str,
    stage: str,
    status: str,
    payload: dict[str, Any] | None = None,
) -> None:
    item: dict[str, Any] = {
        "run_id": run_id,
        "stage": stage,
        "status": status,
    }
    if payload:
        item["payload"] = payload
    append_trace(path, item)
