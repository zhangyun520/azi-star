from __future__ import annotations

import json
import time
from difflib import unified_diff
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def ensure_data_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")


def append_reflection(path: Path, payload: dict[str, Any]) -> None:
    ensure_data_file(path)
    record = dict(payload)
    record.setdefault("ts", now_iso())
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_recent(path: Path, limit: int = 8) -> list[dict[str, Any]]:
    ensure_data_file(path)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: list[dict[str, Any]] = []
    for raw in lines[-max(1, int(limit)) :]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def build_memory_context(recent: list[dict[str, Any]]) -> str:
    if not recent:
        return "No previous reflections."
    chunks: list[str] = []
    for item in recent[-6:]:
        chunks.append(
            (
                f"ts={item.get('ts','-')} "
                f"risk={item.get('risk_level','-')} "
                f"outcome={item.get('outcome','-')} "
                f"goal={str(item.get('user_goal',''))[:120]}"
            )
        )
        note = str(item.get("notes", "")).strip()
        if note:
            chunks.append(f"note={note[:140]}")
    return "\n".join(chunks)


def text_diff(old: str, new: str) -> str:
    old_lines = str(old or "").splitlines()
    new_lines = str(new or "").splitlines()
    return "\n".join(
        unified_diff(
            old_lines,
            new_lines,
            fromfile="draft_before",
            tofile="draft_after",
            lineterm="",
        )
    )

