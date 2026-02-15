from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from core.calibration import ensure_default_gold_tasks, evaluate_gold_hit, load_gold_tasks
from core.engine import EngineConfig, generate_action_plan
from core.memory import append_reflection, load_recent, text_diff
from core.regression import maybe_record_regression
from core.sandbox import enforce_plan, sanitize_execution_steps
from core.trace import log_event, new_run_id
from tools.dummy_tools import TOOL_REGISTRY


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cognitive OS v0.1 (minimal local loop)")
    p.add_argument("--goal", default="", help="User goal text")
    p.add_argument("--auto-approve", action="store_true", help="Auto approve when confirmation is required")
    p.add_argument("--model", default="gpt-4.1-mini", help="Model name for planning call")
    p.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI-compatible base URL")
    return p.parse_args()


def _print_plan(console: Console, payload: dict[str, Any]) -> None:
    console.print(Panel(json.dumps(payload, ensure_ascii=False, indent=2), title="ActionPlan"))


def _print_execution_table(console: Console, steps: list[dict[str, Any]]) -> None:
    t = Table(title="Execution Steps")
    t.add_column("#", justify="right")
    t.add_column("Tool")
    t.add_column("Params (short)")
    for i, step in enumerate(steps, start=1):
        t.add_row(str(i), str(step.get("tool_name", "-")), json.dumps(step.get("parameters", {}), ensure_ascii=False)[:120])
    console.print(t)


def _append_reflection(
    *,
    data_file: Path,
    run_id: str,
    goal: str,
    outcome: str,
    risk_level: str,
    model_plan: dict[str, Any],
    final_plan: dict[str, Any],
    edit_diff: str,
    artifacts: list[dict[str, Any]],
    gold_result: dict[str, Any],
    notes: str = "",
) -> None:
    payload = {
        "ts": now_iso(),
        "run_id": run_id,
        "user_goal": goal,
        "outcome": outcome,
        "risk_level": risk_level,
        "model_plan": model_plan,
        "final_plan": final_plan,
        "edit_diff": edit_diff,
        "notes": notes,
        "gold_result": gold_result,
        "artifacts": artifacts,
    }
    append_reflection(data_file, payload)


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent

    reflections_file = base_dir / "data" / "reflections.jsonl"
    trace_file = base_dir / "data" / "execution_trace.jsonl"
    regression_file = base_dir / "data" / "regression_set.jsonl"
    gold_file = base_dir / "data" / "gold_tasks.json"

    ensure_default_gold_tasks(gold_file)
    gold_tasks = load_gold_tasks(gold_file)

    console = Console()
    run_id = new_run_id()

    goal = str(args.goal or "").strip()
    if not goal:
        goal = Prompt.ask("Enter goal")
    if not goal:
        console.print("[red]Empty goal, exit.[/red]")
        return

    log_event(
        path=trace_file,
        run_id=run_id,
        stage="run_start",
        status="ok",
        payload={"goal": goal, "model": args.model, "base_url": args.base_url},
    )

    recent = load_recent(reflections_file, limit=8)
    log_event(
        path=trace_file,
        run_id=run_id,
        stage="memory_loaded",
        status="ok",
        payload={"recent_count": len(recent)},
    )

    plan, meta = generate_action_plan(
        base_dir=base_dir,
        user_goal=goal,
        recent_reflections=recent,
        config=EngineConfig(base_url=args.base_url, model=args.model),
    )

    log_event(
        path=trace_file,
        run_id=run_id,
        stage="plan_generated",
        status="ok",
        payload={"engine": meta, "plan_risk": plan.risk.level, "plan_steps": len(plan.plan)},
    )

    console.print(f"[cyan]engine mode:[/cyan] {meta.get('mode')} | model={meta.get('model')}")
    if meta.get("error"):
        console.print(f"[yellow]engine warning:[/yellow] {meta.get('error')}")

    _print_plan(console, plan.model_dump(mode="json"))

    guard = enforce_plan(plan)
    log_event(
        path=trace_file,
        run_id=run_id,
        stage="sandbox_checked",
        status="ok",
        payload={
            "final_level": guard.final_level,
            "requires_confirmation": guard.requires_confirmation,
            "blocked": guard.blocked,
            "reasons": guard.reasons,
        },
    )

    console.print(
        Panel(
            f"final_level={guard.final_level}\nrequires_confirmation={guard.requires_confirmation}\n"
            f"blocked={guard.blocked}\nreasons={guard.reasons}",
            title="Sandbox Decision",
        )
    )

    final_plan = plan.model_copy(deep=True)
    artifacts: list[dict[str, Any]] = []
    edit_delta = ""

    if guard.blocked:
        gold_result = evaluate_gold_hit(
            goal=goal,
            plan=final_plan,
            final_risk_level=guard.final_level,
            final_requires_confirmation=guard.requires_confirmation,
            tasks=gold_tasks,
        )
        regression_saved = maybe_record_regression(
            path=regression_file,
            run_id=run_id,
            user_goal=goal,
            outcome="blocked",
            risk_level=guard.final_level,
            model_plan=plan.model_dump(mode="json"),
            final_plan=final_plan.model_dump(mode="json"),
            edit_diff="",
            blocked=True,
            artifacts=artifacts,
            gold_result=gold_result,
        )

        _append_reflection(
            data_file=reflections_file,
            run_id=run_id,
            goal=goal,
            outcome="blocked",
            risk_level=guard.final_level,
            model_plan=plan.model_dump(mode="json"),
            final_plan=final_plan.model_dump(mode="json"),
            edit_diff="",
            artifacts=artifacts,
            gold_result=gold_result,
            notes="; ".join(guard.reasons),
        )

        log_event(
            path=trace_file,
            run_id=run_id,
            stage="gold_check",
            status="ok",
            payload=gold_result,
        )
        log_event(
            path=trace_file,
            run_id=run_id,
            stage="regression_record",
            status="ok",
            payload={"saved": regression_saved},
        )
        log_event(path=trace_file, run_id=run_id, stage="run_end", status="blocked")

        console.print(Panel(json.dumps(gold_result, ensure_ascii=False, indent=2), title="Gold Check"))
        console.print("[red]Blocked by hard policy. Logged to reflections/trace/regression.[/red]")
        return

    if guard.requires_confirmation:
        decision = "y" if args.auto_approve else Prompt.ask(
            "Confirm execution? [y=approve / n=reject / e=edit-draft]",
            choices=["y", "n", "e"],
            default="n",
        )
        log_event(
            path=trace_file,
            run_id=run_id,
            stage="confirmation",
            status="ok",
            payload={"decision": decision},
        )

        if decision == "n":
            gold_result = evaluate_gold_hit(
                goal=goal,
                plan=final_plan,
                final_risk_level=guard.final_level,
                final_requires_confirmation=guard.requires_confirmation,
                tasks=gold_tasks,
            )
            regression_saved = maybe_record_regression(
                path=regression_file,
                run_id=run_id,
                user_goal=goal,
                outcome="rejected",
                risk_level=guard.final_level,
                model_plan=plan.model_dump(mode="json"),
                final_plan=final_plan.model_dump(mode="json"),
                edit_diff="",
                blocked=False,
                artifacts=artifacts,
                gold_result=gold_result,
            )

            _append_reflection(
                data_file=reflections_file,
                run_id=run_id,
                goal=goal,
                outcome="rejected",
                risk_level=guard.final_level,
                model_plan=plan.model_dump(mode="json"),
                final_plan=final_plan.model_dump(mode="json"),
                edit_diff="",
                artifacts=artifacts,
                gold_result=gold_result,
                notes="user rejected at confirmation gate",
            )

            log_event(path=trace_file, run_id=run_id, stage="gold_check", status="ok", payload=gold_result)
            log_event(
                path=trace_file,
                run_id=run_id,
                stage="regression_record",
                status="ok",
                payload={"saved": regression_saved},
            )
            log_event(path=trace_file, run_id=run_id, stage="run_end", status="rejected")

            console.print(Panel(json.dumps(gold_result, ensure_ascii=False, indent=2), title="Gold Check"))
            console.print("[yellow]Rejected. Logged to reflections/trace/regression.[/yellow]")
            return

        if decision == "e":
            before = str(final_plan.draft_content or "")
            console.print(Panel(before or "(empty draft)", title="Draft Before"))
            edited = Prompt.ask("Enter edited draft (single line)")
            final_plan.draft_content = edited
            edit_delta = text_diff(before, edited)

            for step in final_plan.plan:
                if str(step.tool_name) == "dummy_send_email":
                    step.parameters["body"] = edited

            log_event(
                path=trace_file,
                run_id=run_id,
                stage="draft_edited",
                status="ok",
                payload={"edited": bool(edit_delta)},
            )

    steps = sanitize_execution_steps(final_plan)
    _print_execution_table(console, steps)

    outcome = "approved"
    for idx, step in enumerate(steps, start=1):
        name = str(step.get("tool_name", ""))
        log_event(
            path=trace_file,
            run_id=run_id,
            stage="tool_execute",
            status="start",
            payload={"index": idx, "tool": name},
        )

        fn = TOOL_REGISTRY.get(name)
        if fn is None:
            err = "tool_not_found"
            artifacts.append({"tool": name, "ok": False, "error": err})
            outcome = "failed"
            log_event(
                path=trace_file,
                run_id=run_id,
                stage="tool_execute",
                status="error",
                payload={"index": idx, "tool": name, "error": err},
            )
            continue

        try:
            result = fn(base_dir=base_dir, **dict(step.get("parameters", {})))
            artifacts.append({"tool": name, "result": result})
            if not bool(result.get("ok", False)):
                outcome = "failed"

            log_event(
                path=trace_file,
                run_id=run_id,
                stage="tool_execute",
                status="ok" if bool(result.get("ok", False)) else "error",
                payload={"index": idx, "tool": name, "result": result},
            )
        except Exception as exc:
            artifacts.append({"tool": name, "ok": False, "error": str(exc)})
            outcome = "failed"
            log_event(
                path=trace_file,
                run_id=run_id,
                stage="tool_execute",
                status="error",
                payload={"index": idx, "tool": name, "error": str(exc)},
            )

    gold_result = evaluate_gold_hit(
        goal=goal,
        plan=final_plan,
        final_risk_level=guard.final_level,
        final_requires_confirmation=guard.requires_confirmation,
        tasks=gold_tasks,
    )
    log_event(path=trace_file, run_id=run_id, stage="gold_check", status="ok", payload=gold_result)

    regression_saved = maybe_record_regression(
        path=regression_file,
        run_id=run_id,
        user_goal=goal,
        outcome=outcome,
        risk_level=guard.final_level,
        model_plan=plan.model_dump(mode="json"),
        final_plan=final_plan.model_dump(mode="json"),
        edit_diff=edit_delta,
        blocked=False,
        artifacts=artifacts,
        gold_result=gold_result,
    )

    notes = json.dumps({"gold": gold_result, "artifacts": artifacts}, ensure_ascii=False)[:1800]
    _append_reflection(
        data_file=reflections_file,
        run_id=run_id,
        goal=goal,
        outcome=outcome,
        risk_level=guard.final_level,
        model_plan=plan.model_dump(mode="json"),
        final_plan=final_plan.model_dump(mode="json"),
        edit_diff=edit_delta,
        artifacts=artifacts,
        gold_result=gold_result,
        notes=notes,
    )

    log_event(
        path=trace_file,
        run_id=run_id,
        stage="regression_record",
        status="ok",
        payload={"saved": regression_saved},
    )
    log_event(path=trace_file, run_id=run_id, stage="run_end", status=outcome)

    console.print(Panel(json.dumps(gold_result, ensure_ascii=False, indent=2), title="Gold Check"))
    console.print(Panel(json.dumps(artifacts, ensure_ascii=False, indent=2), title="Execution Artifacts"))
    console.print("[green]Done. Reflection/trace written, regression updated if needed.[/green]")


if __name__ == "__main__":
    main()
