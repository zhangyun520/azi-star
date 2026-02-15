from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute v0.1 gold calibration stats from reflections.")
    p.add_argument("--data-dir", default="", help="Data directory path. Defaults to ./data beside this script.")
    p.add_argument("--limit", type=int, default=0, help="Only use the latest N reflection records. 0 means all.")
    p.add_argument("--write-json", action="store_true", help="Write summary to data/stats.json")
    return p.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _pct(num: int, den: int) -> str:
    if den <= 0:
        return "n/a"
    return f"{(num / den) * 100:.1f}%"


def _task_breakdown(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for rec in records:
        gold = rec.get("gold_result")
        if not isinstance(gold, dict):
            continue
        if not bool(gold.get("matched")):
            continue
        task_id = str(gold.get("task_id") or "unknown")
        bucket = out.setdefault(task_id, {"matched": 0, "hit": 0, "miss": 0})
        bucket["matched"] += 1
        if gold.get("hit") is True:
            bucket["hit"] += 1
        elif gold.get("hit") is False:
            bucket["miss"] += 1
    return out


def build_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)

    with_gold = 0
    matched = 0
    hit = 0
    miss = 0
    no_match = 0

    by_outcome: dict[str, int] = {}
    by_risk: dict[str, int] = {}

    for rec in records:
        outcome = str(rec.get("outcome") or "unknown")
        risk = str(rec.get("risk_level") or "unknown")
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        by_risk[risk] = by_risk.get(risk, 0) + 1

        gold = rec.get("gold_result")
        if not isinstance(gold, dict):
            continue
        with_gold += 1
        if bool(gold.get("matched")):
            matched += 1
            if gold.get("hit") is True:
                hit += 1
            elif gold.get("hit") is False:
                miss += 1
        else:
            no_match += 1

    task_stats = _task_breakdown(records)
    return {
        "total_runs": total,
        "runs_with_gold_result": with_gold,
        "gold_matched": matched,
        "gold_hit": hit,
        "gold_miss": miss,
        "gold_no_match": no_match,
        "gold_hit_rate": _pct(hit, matched),
        "outcome_distribution": by_outcome,
        "risk_distribution": by_risk,
        "task_breakdown": task_stats,
    }


def print_stats(console: Console, stats: dict[str, Any]) -> None:
    summary = Table(title="Gold Calibration Summary")
    summary.add_column("Metric")
    summary.add_column("Value")
    summary.add_row("total_runs", str(stats["total_runs"]))
    summary.add_row("runs_with_gold_result", str(stats["runs_with_gold_result"]))
    summary.add_row("gold_matched", str(stats["gold_matched"]))
    summary.add_row("gold_hit", str(stats["gold_hit"]))
    summary.add_row("gold_miss", str(stats["gold_miss"]))
    summary.add_row("gold_no_match", str(stats["gold_no_match"]))
    summary.add_row("gold_hit_rate", str(stats["gold_hit_rate"]))
    console.print(summary)

    task_table = Table(title="Gold Task Breakdown")
    task_table.add_column("task_id")
    task_table.add_column("matched", justify="right")
    task_table.add_column("hit", justify="right")
    task_table.add_column("miss", justify="right")
    task_table.add_column("hit_rate", justify="right")
    task_stats = stats.get("task_breakdown", {})
    if isinstance(task_stats, dict) and task_stats:
        for task_id, bucket in sorted(task_stats.items()):
            matched = int(bucket.get("matched", 0))
            hit = int(bucket.get("hit", 0))
            miss = int(bucket.get("miss", 0))
            task_table.add_row(task_id, str(matched), str(hit), str(miss), _pct(hit, matched))
    else:
        task_table.add_row("(no matched gold tasks)", "-", "-", "-", "-")
    console.print(task_table)

    console.print(
        Panel(
            json.dumps(
                {
                    "outcome_distribution": stats.get("outcome_distribution", {}),
                    "risk_distribution": stats.get("risk_distribution", {}),
                },
                ensure_ascii=False,
                indent=2,
            ),
            title="Distributions",
        )
    )


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    data_dir = Path(args.data_dir).resolve() if args.data_dir else (base_dir / "data")
    reflections_path = data_dir / "reflections.jsonl"

    records = _load_jsonl(reflections_path)
    if args.limit and args.limit > 0:
        records = records[-args.limit :]

    stats = build_stats(records)
    console = Console()
    print_stats(console, stats)

    if args.write_json:
        out = data_dir / "stats.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]Wrote stats JSON:[/green] {out}")


if __name__ == "__main__":
    main()
