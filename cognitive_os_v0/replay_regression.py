from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from core.calibration import evaluate_gold_hit, load_gold_tasks
from core.engine import EngineConfig, generate_action_plan
from core.memory import load_recent
from core.sandbox import enforce_plan, sanitize_execution_steps
from tools.dummy_tools import TOOL_REGISTRY


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay regression cases against current planner/sandbox.")
    p.add_argument("--data-dir", default="", help="Data directory path. Defaults to ./data beside this script.")
    p.add_argument("--limit", type=int, default=20, help="Replay latest N regression cases.")
    p.add_argument("--model", default="gpt-4.1-mini", help="Model name for planning call")
    p.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI-compatible base URL")
    p.add_argument("--execute", action="store_true", help="Execute tool calls during replay (default: plan-only)")
    p.add_argument("--write-json", action="store_true", help="Write replay summary to data/replay_report.json")
    return p.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _run_tools_if_enabled(*, execute: bool, base_dir: Path, plan: Any) -> tuple[str, list[dict[str, Any]]]:
    if not execute:
        return "plan_only", []

    steps = sanitize_execution_steps(plan)
    artifacts: list[dict[str, Any]] = []
    outcome = "approved"
    for step in steps:
        name = str(step.get("tool_name", ""))
        fn = TOOL_REGISTRY.get(name)
        if fn is None:
            artifacts.append({"tool": name, "ok": False, "error": "tool_not_found"})
            outcome = "failed"
            continue
        try:
            result = fn(base_dir=base_dir, **dict(step.get("parameters", {})))
            artifacts.append({"tool": name, "result": result})
            if not bool(result.get("ok", False)):
                outcome = "failed"
        except Exception as exc:
            artifacts.append({"tool": name, "ok": False, "error": str(exc)})
            outcome = "failed"
    return outcome, artifacts


def _resolved(*, old_tags: list[str], blocked: bool, gold_result: dict[str, Any], new_outcome: str) -> bool:
    if "policy_blocked" in old_tags:
        return blocked
    if blocked:
        return False
    if bool(gold_result.get("matched")) and gold_result.get("hit") is True:
        return True
    if any(tag in old_tags for tag in ["execution_failed", "execution_error", "tool_returned_not_ok"]):
        return new_outcome == "approved"
    return False


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    data_dir = Path(args.data_dir).resolve() if args.data_dir else (base_dir / "data")

    reg_path = data_dir / "regression_set.jsonl"
    reflections_path = data_dir / "reflections.jsonl"
    gold_path = data_dir / "gold_tasks.json"
    gold_tasks = load_gold_tasks(gold_path)

    rows = _load_jsonl(reg_path)
    rows = rows[-max(1, int(args.limit)) :]

    console = Console()
    if not rows:
        console.print("[yellow]No regression cases found.[/yellow]")
        return

    recent = load_recent(reflections_path, limit=8)
    replay_results: list[dict[str, Any]] = []

    for idx, row in enumerate(rows, start=1):
        goal = str(row.get("user_goal", "")).strip()
        old_tags = [str(x) for x in row.get("failure_tags", []) if str(x).strip()]

        plan, meta = generate_action_plan(
            base_dir=base_dir,
            user_goal=goal,
            recent_reflections=recent,
            config=EngineConfig(base_url=args.base_url, model=args.model),
        )
        guard = enforce_plan(plan)
        gold_result = evaluate_gold_hit(
            goal=goal,
            plan=plan,
            final_risk_level=guard.final_level,
            final_requires_confirmation=guard.requires_confirmation,
            tasks=gold_tasks,
        )

        if guard.blocked:
            new_outcome = "blocked"
            artifacts: list[dict[str, Any]] = []
        else:
            new_outcome, artifacts = _run_tools_if_enabled(
                execute=bool(args.execute),
                base_dir=base_dir,
                plan=plan,
            )

        is_resolved = _resolved(
            old_tags=old_tags,
            blocked=guard.blocked,
            gold_result=gold_result,
            new_outcome=new_outcome,
        )

        replay_results.append(
            {
                "idx": idx,
                "old_run_id": str(row.get("run_id", "")),
                "goal": goal,
                "old_tags": old_tags,
                "new_risk": guard.final_level,
                "blocked": guard.blocked,
                "new_outcome": new_outcome,
                "gold_result": gold_result,
                "resolved": is_resolved,
                "engine": meta,
                "artifacts": artifacts,
            }
        )

    table = Table(title="Regression Replay Results")
    table.add_column("#", justify="right")
    table.add_column("old_run_id")
    table.add_column("new_risk")
    table.add_column("blocked")
    table.add_column("gold_hit")
    table.add_column("resolved")
    table.add_column("tags")

    resolved_count = 0
    for item in replay_results:
        gold_hit = item["gold_result"].get("hit")
        if item["resolved"]:
            resolved_count += 1
        table.add_row(
            str(item["idx"]),
            str(item["old_run_id"])[:18],
            str(item["new_risk"]),
            str(item["blocked"]),
            str(gold_hit),
            str(item["resolved"]),
            ",".join(item["old_tags"])[:48],
        )
    console.print(table)

    total = len(replay_results)
    console.print(
        f"[cyan]Replay summary:[/cyan] total={total}, resolved={resolved_count}, unresolved={total - resolved_count}"
    )

    if args.write_json:
        out = data_dir / "replay_report.json"
        payload = {
            "total": total,
            "resolved": resolved_count,
            "unresolved": total - resolved_count,
            "execute": bool(args.execute),
            "model": args.model,
            "base_url": args.base_url,
            "results": replay_results,
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote replay report:[/green] {out}")


if __name__ == "__main__":
    main()
