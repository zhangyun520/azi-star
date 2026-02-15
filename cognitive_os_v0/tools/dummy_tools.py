from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _safe_root(base_dir: Path) -> Path:
    root = base_dir / "data" / "sandbox_files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_safe_path(base_dir: Path, relative_path: str) -> Path:
    root = _safe_root(base_dir).resolve()
    raw = (root / str(relative_path or "").strip().replace("\\", "/")).resolve()
    if root not in raw.parents and raw != root:
        raise ValueError("path escapes sandbox root")
    return raw


def dummy_read_file(*, base_dir: Path, path: str) -> dict[str, Any]:
    target = _resolve_safe_path(base_dir, path)
    if not target.exists():
        return {"ok": False, "message": "file not found", "path": str(target)}
    txt = target.read_text(encoding="utf-8", errors="ignore")
    return {"ok": True, "path": str(target), "content": txt[:4000]}


def dummy_write_file(*, base_dir: Path, path: str, content: str) -> dict[str, Any]:
    target = _resolve_safe_path(base_dir, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(content or ""), encoding="utf-8")
    return {"ok": True, "path": str(target), "bytes": len(str(content or "").encode("utf-8"))}


def dummy_send_email(*, base_dir: Path, to: str, subject: str, body: str) -> dict[str, Any]:
    outbox = base_dir / "data" / "outbox_drafts.jsonl"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": now_iso(),
        "to": str(to or ""),
        "subject": str(subject or ""),
        "body": str(body or ""),
        "status": "draft_only",
    }
    with outbox.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return {"ok": True, "message": "draft saved (not sent)", "outbox": str(outbox)}


TOOL_REGISTRY = {
    "dummy_read_file": dummy_read_file,
    "dummy_write_file": dummy_write_file,
    "dummy_send_email": dummy_send_email,
}

