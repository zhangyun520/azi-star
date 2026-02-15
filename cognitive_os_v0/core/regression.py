from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def ensure_data_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")


def append_regression_case(path: Path, payload: dict[str, Any]) -> None:
    ensure_data_file(path)
    record = dict(payload)
    record.setdefault("ts", now_iso())
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _artifact_tags(artifacts: list[dict[str, Any]]) -> list[str]:
    tags: list[str] = []
    for item in artifacts:
        if str(item.get("error", "")).strip():
            tags.append("execution_error")
        result = item.get("result")
        if isinstance(result, dict) and not bool(result.get("ok", True)):
            tags.append("tool_returned_not_ok")
    return tags


def build_regression_tags(
    *,
    outcome: str,
    blocked: bool,
    edit_diff: str,
    artifacts: list[dict[str, Any]],
    gold_result: dict[str, Any],
    extra_tags: list[str] | None = None,
) -> list[str]:
    tags: list[str] = []
    if blocked:
        tags.append("policy_blocked")
    if outcome == "failed":
        tags.append("execution_failed")
    if outcome == "rejected":
        tags.append("user_rejected")
    if str(edit_diff or "").strip():
        tags.append("draft_edited_by_user")
    tags.extend(_artifact_tags(artifacts))

    if bool(gold_result.get("matched")) and gold_result.get("hit") is False:
        tags.append("gold_miss")

    if extra_tags:
        tags.extend([str(x) for x in extra_tags if str(x).strip()])

    # de-dup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for item in tags:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def maybe_record_regression(
    *,
    path: Path,
    run_id: str,
    user_goal: str,
    outcome: str,
    risk_level: str,
    model_plan: dict[str, Any],
    final_plan: dict[str, Any],
    edit_diff: str,
    blocked: bool,
    artifacts: list[dict[str, Any]],
    gold_result: dict[str, Any],
    extra_tags: list[str] | None = None,
) -> bool:
    tags = build_regression_tags(
        outcome=outcome,
        blocked=blocked,
        edit_diff=edit_diff,
        artifacts=artifacts,
        gold_result=gold_result,
        extra_tags=extra_tags,
    )
    if not tags:
        return False

    append_regression_case(
        path,
        {
            "run_id": run_id,
            "user_goal": user_goal,
            "outcome": outcome,
            "risk_level": risk_level,
            "failure_tags": tags,
            "model_plan": model_plan,
            "final_plan": final_plan,
            "edit_diff": edit_diff,
            "gold_result": gold_result,
            "artifacts": artifacts,
        },
    )
    return True
