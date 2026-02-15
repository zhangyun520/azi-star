from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

from azi_rebuild.runtime import (
    connect_runtime_db,
    enqueue_event,
    load_runtime_state,
    run_single_worker_cycle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Azi rebuild deep worker")
    parser.add_argument("--db", default="azi_rebuild.db")
    parser.add_argument("--state", default="azi_state.json")
    parser.add_argument("--llm-config", default="llm_config.json")
    parser.add_argument("--directive-file", default="existence_directive.json")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force-skill", action="store_true")
    parser.add_argument("--force-deep", action="store_true")
    parser.add_argument("--force-dream", action="store_true")
    parser.add_argument("--interval-sec", type=float, default=20.0)
    parser.add_argument("--max-events", type=int, default=6)
    return parser.parse_args()


def _state_dump_path() -> Path:
    return Path(__file__).resolve().parent / "resident_output" / "deep_coder_worker_state.json"


def _write_worker_state(payload: dict) -> None:
    path = _state_dump_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _inject_force_events(conn, args: argparse.Namespace) -> None:
    if args.force_skill:
        enqueue_event(
            conn,
            source="deep-worker",
            event_type="iteration",
            content="forced skill evolution request",
            meta={"force": True, "mode": "skill"},
        )
    if args.force_deep:
        enqueue_event(
            conn,
            source="deep-worker",
            event_type="deep_request",
            content="forced deep worker request",
            meta={"force": True, "mode": "deep"},
        )
    if args.force_dream:
        enqueue_event(
            conn,
            source="deep-worker",
            event_type="dream_request",
            content="forced dream worker request",
            meta={"force": True, "mode": "dream"},
        )


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = root / db_path

    state_path = Path(args.state)
    if not state_path.is_absolute():
        state_path = root / state_path

    conn = connect_runtime_db(str(db_path))
    state = load_runtime_state(state_path)

    try:
        _inject_force_events(conn, args)

        if args.once:
            try:
                handled = run_single_worker_cycle(
                    conn,
                    state,
                    max_events=int(args.max_events),
                    base_dir=root,
                )
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                handled = 0
            _write_worker_state({"mode": "once", "handled": handled, "ts": time.time()})
            print(f"[deep-worker] handled={handled}")
            return

        interval_sec = max(0.5, float(args.interval_sec))
        max_events = max(1, int(args.max_events))
        print("[deep-worker] running")

        while True:
            try:
                handled = run_single_worker_cycle(conn, state, max_events=max_events, base_dir=root)
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                handled = 0
                time.sleep(0.8)
            _write_worker_state({"mode": "loop", "handled": handled, "ts": time.time()})
            if handled <= 0:
                time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("[deep-worker] stopped by keyboard")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
