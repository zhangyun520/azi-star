from __future__ import annotations

import argparse
import time
from pathlib import Path

from azi_rebuild.runtime import (
    connect_runtime_db,
    enqueue_event,
    load_runtime_state,
    run_single_brain_cycle,
    save_runtime_state,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Azi rebuild fast loop")
    parser.add_argument("--db", default="azi_rebuild.db")
    parser.add_argument("--state", default="azi_state.json")
    parser.add_argument("--interval-sec", type=float, default=15.0)
    parser.add_argument("--max-events", type=int, default=12)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force-deep", action="store_true")
    parser.add_argument("--force-dream", action="store_true")
    parser.add_argument("--force-debate", action="store_true")
    return parser.parse_args()


def inject_force_events(conn, args: argparse.Namespace) -> None:
    if args.force_deep:
        enqueue_event(
            conn,
            source="brain-loop",
            event_type="deep_request",
            content="forced deep reflection",
            meta={"force": True},
        )
    if args.force_dream:
        enqueue_event(
            conn,
            source="brain-loop",
            event_type="dream_request",
            content="forced dream replay request",
            meta={"force": True, "mode": "dream"},
        )
    if args.force_debate:
        enqueue_event(
            conn,
            source="brain-loop",
            event_type="input",
            content="forced devils advocate request",
            meta={"force": True, "mode": "debate"},
        )


def run_once(conn, state_path: Path, state: dict, args: argparse.Namespace) -> int:
    inject_force_events(conn, args)
    handled = run_single_brain_cycle(
        conn,
        state,
        max_events=int(args.max_events),
        force_deep=bool(args.force_deep),
        base_dir=Path(__file__).resolve().parent,
    )
    save_runtime_state(state_path, state)
    return handled


def run_forever(conn, state_path: Path, state: dict, args: argparse.Namespace) -> None:
    inject_force_events(conn, args)
    interval_sec = max(0.2, float(args.interval_sec))
    max_events = max(1, int(args.max_events))

    while True:
        handled = run_single_brain_cycle(
            conn,
            state,
            max_events=max_events,
            force_deep=False,
            base_dir=Path(__file__).resolve().parent,
        )
        save_runtime_state(state_path, state)
        if handled <= 0:
            time.sleep(interval_sec)


def main() -> None:
    args = parse_args()
    state_path = Path(args.state)
    if not state_path.is_absolute():
        state_path = Path(__file__).resolve().parent / state_path

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = Path(__file__).resolve().parent / db_path

    conn = connect_runtime_db(str(db_path))
    try:
        state = load_runtime_state(state_path)

        if args.once:
            handled = run_once(conn, state_path, state, args)
            print(f"[brain-loop] handled={handled}")
            return

        print("[brain-loop] running")
        run_forever(conn, state_path, state, args)
    except KeyboardInterrupt:
        print("[brain-loop] stopped by keyboard")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
