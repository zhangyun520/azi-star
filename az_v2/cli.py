from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .diagnose import diagnose
from .engine import AziEngineV2
from .state import State10D


def _load_state(path: str | None) -> State10D:
    if not path:
        return State10D()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"state file not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return State10D.model_validate(data)


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Azi v2 10D core CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_diag = sub.add_parser("diagnose", help="run 4D-8D diagnose + halt check")
    p_diag.add_argument("--text", required=True, help="object description")
    p_diag.add_argument("--state", default="", help="optional state json path")

    p_run = sub.add_parser("run-loop", help="ingest one event and persist diagnose result")
    p_run.add_argument("--text", required=True, help="input content")
    p_run.add_argument("--source", default="manual", help="event source")
    p_run.add_argument("--state", default="", help="optional state json path")
    p_run.add_argument("--db", default="az_v2_events.db", help="sqlite path")

    p_snap = sub.add_parser("snapshot", help="show recent state/events")
    p_snap.add_argument("--state", default="", help="optional state json path")
    p_snap.add_argument("--db", default="az_v2_events.db", help="sqlite path")
    p_snap.add_argument("--limit", type=int, default=10, help="recent events limit")

    args = parser.parse_args()

    if args.cmd == "diagnose":
        state = _load_state(args.state)
        _print_json(diagnose(args.text, state=state))
        return

    if args.cmd == "run-loop":
        state = _load_state(args.state)
        engine = AziEngineV2(state=state, event_db_path=args.db)
        _print_json(engine.handle_input(args.text, source=args.source))
        return

    if args.cmd == "snapshot":
        state = _load_state(args.state)
        engine = AziEngineV2(state=state, event_db_path=args.db)
        _print_json(engine.snapshot(limit=args.limit))
        return


if __name__ == "__main__":
    main()

