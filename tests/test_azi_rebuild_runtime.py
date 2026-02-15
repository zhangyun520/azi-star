from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from azi_rebuild.runtime import (
    build_snapshot_payload,
    connect_runtime_db,
    enqueue_event,
    load_runtime_state,
    run_single_brain_cycle,
    run_single_worker_cycle,
    save_runtime_state,
)


def test_brain_cycle_processes_input_and_updates_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "azi_rebuild.db"
    state_path = tmp_path / "azi_state.json"

    conn = connect_runtime_db(str(db_path))
    try:
        state = load_runtime_state(state_path)
        enqueue_event(
            conn,
            source="manual",
            event_type="input",
            content="并发风险上升，需要回落策略",
            meta={"test": True},
        )
        handled = run_single_brain_cycle(conn, state, max_events=4)
        assert handled == 1

        save_runtime_state(state_path, state)
        reloaded = load_runtime_state(state_path)
        snap = build_snapshot_payload(conn, reloaded)
        assert "state" in snap
        assert "decision_text" in snap
        assert "stability" in snap
        assert "orchestration" in snap
        assert "work_memory" in snap
        assert "dispatch" in snap
        assert int(snap["state"]["last_event_id"]) > 0
        assert "mvcc_version" in snap["state"]
        assert int(snap["stability"]["brain_budget"]["effective"]) >= 1
        assert str(snap["orchestration"]["last_route_group"])
        assert isinstance(snap["work_memory"].get("task_totals", {}), dict)

        version_row = conn.execute("SELECT version FROM azi_state_versions WHERE id=1").fetchone()
        assert version_row is not None
        assert int(version_row["version"] or 0) >= 1

        cw_row = conn.execute(
            "SELECT actor, status FROM azi_commit_windows ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert cw_row is not None
        assert str(cw_row["actor"]) == "brain-loop"
        assert str(cw_row["status"]) in {"committed", "rebase_committed", "drift_unresolved"}

        contract_rows = conn.execute(
            "SELECT kind FROM azi_contracts ORDER BY id DESC LIMIT 12"
        ).fetchall()
        contract_kinds = {str(r["kind"]) for r in contract_rows}
        assert "plan" in contract_kinds
        assert "risk_report" in contract_kinds
        assert "exec_trace" in contract_kinds
        assert "dispatch_plan" in contract_kinds
    finally:
        conn.close()


def test_stability_budget_shrinks_under_high_pressure(tmp_path: Path) -> None:
    db_path = tmp_path / "azi_rebuild.db"
    state_path = tmp_path / "azi_state.json"

    conn = connect_runtime_db(str(db_path))
    try:
        state = load_runtime_state(state_path)
        state["stress"] = 0.92
        state["energy"] = 0.12
        state["uncertainty"] = 0.82
        state["continuity"] = 0.22

        enqueue_event(
            conn,
            source="manual",
            event_type="input",
            content="高压下先收敛预算",
            meta={"test": True},
        )
        handled = run_single_brain_cycle(conn, state, max_events=10)
        assert handled == 1

        stability = dict(state.get("stability", {}) or {})
        requested = int(stability.get("requested_brain_events", 0) or 0)
        effective = int(stability.get("effective_brain_events", 0) or 0)
        assert requested == 10
        assert 1 <= effective < requested

        snap = build_snapshot_payload(conn, state)
        assert "stability" in snap
        assert int(snap["stability"]["brain_budget"]["effective"]) == effective
    finally:
        conn.close()


def test_stability_route_cooldown_trips_on_consecutive_live_failures(tmp_path: Path) -> None:
    db_path = tmp_path / "azi_rebuild.db"
    state_path = tmp_path / "azi_state.json"
    llm_cfg_path = tmp_path / "llm_config.json"
    llm_cfg_path.write_text(
        """
{
  "api_live_enabled": true,
  "provider_groups": {
    "shallow_chain": ["bad-provider"],
    "fast_chain": ["bad-provider"],
    "medium_chain": ["bad-provider"],
    "deep_chain": ["bad-provider"]
  },
  "providers": {
    "bad-provider": {
      "provider": "api",
      "enabled": true,
      "endpoint": "",
      "model": "dummy-model",
      "api_key": "dummy-key",
      "timeout_sec": 5
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    conn = connect_runtime_db(str(db_path))
    try:
        state = load_runtime_state(state_path)
        for i in range(3):
            enqueue_event(
                conn,
                source="manual",
                event_type="input",
                content=f"连续失败触发熔断 #{i}",
                meta={"test": True},
            )
        handled = run_single_brain_cycle(conn, state, max_events=6, base_dir=tmp_path)
        assert handled == 3

        stability = dict(state.get("stability", {}) or {})
        assert int(stability.get("panic_count", 0) or 0) >= 1
        assert str(stability.get("mode", "normal")) == "degraded"
        cooldowns = dict(stability.get("route_cooldown_until", {}) or {})
        assert cooldowns
        assert max(int(v or 0) for v in cooldowns.values()) > int(state.get("cycle", 0) or 0)

        orch = dict(state.get("orchestration", {}) or {})
        group_metrics = dict(orch.get("group_metrics", {}) or {})
        assert group_metrics
        assert any(int(dict(v or {}).get("total", 0) or 0) >= 1 for v in group_metrics.values())
    finally:
        conn.close()


def test_worker_cycle_emits_evidence_and_proposal_with_eval_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "azi_rebuild.db"
    state_path = tmp_path / "azi_state.json"

    conn = connect_runtime_db(str(db_path))
    try:
        state = load_runtime_state(state_path)
        enqueue_event(
            conn,
            source="manual",
            event_type="iteration",
            content="请重构协议流",
            meta={"test": True},
        )
        handled = run_single_worker_cycle(conn, state, max_events=4)
        assert handled == 1

        rows = conn.execute(
            "SELECT event_type FROM azi_events WHERE event_type IN ('evidence','proposal','deep_release')"
        ).fetchall()
        kinds = {str(r["event_type"]) for r in rows}
        assert "evidence" in kinds
        assert "proposal" in kinds
        assert "deep_release" in kinds

        gate_row = conn.execute(
            "SELECT status FROM azi_eval_gates ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert gate_row is not None
        assert str(gate_row["status"]) == "passed"

        cw_row = conn.execute(
            "SELECT actor, status FROM azi_commit_windows ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert cw_row is not None
        assert str(cw_row["actor"]) == "deep-worker"
        assert str(cw_row["status"]) == "committed"

        contract_rows = conn.execute(
            "SELECT kind FROM azi_contracts ORDER BY id DESC LIMIT 12"
        ).fetchall()
        contract_kinds = {str(r["kind"]) for r in contract_rows}
        assert "eval_result" in contract_kinds
        assert "reward_update" in contract_kinds
    finally:
        conn.close()


def test_worker_cycle_handles_dream_request(tmp_path: Path) -> None:
    db_path = tmp_path / "azi_rebuild.db"
    state_path = tmp_path / "azi_state.json"

    conn = connect_runtime_db(str(db_path))
    try:
        state = load_runtime_state(state_path)
        enqueue_event(
            conn,
            source="manual",
            event_type="dream_request",
            content="做一次记忆重放，给出新的线索",
            meta={"test": True, "mode": "dream"},
        )
        handled = run_single_worker_cycle(conn, state, max_events=4)
        assert handled == 1

        rows = conn.execute(
            "SELECT event_type FROM azi_events WHERE event_type IN ('dream','dream_release')"
        ).fetchall()
        kinds = {str(r["event_type"]) for r in rows}
        assert "dream" in kinds
        assert "dream_release" in kinds

        decision_row = conn.execute(
            "SELECT action FROM azi_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert decision_row is not None
        assert str(decision_row["action"]) == "dream_reflect"

        contract_rows = conn.execute(
            "SELECT kind FROM azi_contracts ORDER BY id DESC LIMIT 12"
        ).fetchall()
        contract_kinds = {str(r["kind"]) for r in contract_rows}
        assert "eval_result" in contract_kinds
        assert "reward_update" in contract_kinds
    finally:
        conn.close()


def test_work_memory_bias_prefers_learned_group(tmp_path: Path) -> None:
    db_path = tmp_path / "azi_rebuild.db"
    state_path = tmp_path / "azi_state.json"
    llm_cfg_path = tmp_path / "llm_config.json"
    llm_cfg_path.write_text(
        """
{
  "api_live_enabled": false,
  "provider_groups": {
    "fast_chain": [],
    "medium_chain": []
  },
  "routing_policy": {
    "task_preferences": {
      "coding": ["medium_chain"]
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    conn = connect_runtime_db(str(db_path))
    try:
        state = load_runtime_state(state_path)
        state["work_memory"] = {
            "task_preferences": {"coding": ["fast_chain"]},
            "task_route_stats": {},
            "recent_successes": [],
            "updated_at": "-",
        }
        enqueue_event(
            conn,
            source="manual",
            event_type="input",
            content="请帮我修复这个 python bug",
            meta={"test": True},
        )
        handled = run_single_brain_cycle(conn, state, max_events=4, base_dir=tmp_path)
        assert handled == 1

        route_row = conn.execute(
            "SELECT provider_group, detail_json FROM azi_provider_routes ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert route_row is not None
        assert str(route_row["provider_group"]) == "fast_chain"
        detail = str(route_row["detail_json"] or "")
        assert "memory_bias" in detail
        assert "fast_chain" in detail
    finally:
        conn.close()


def test_work_memory_strength_controls_first_shot_learning(tmp_path: Path) -> None:
    def _fake_generate_structured_response(**kwargs):
        group = str(kwargs.get("group", "medium_chain"))
        return {
            "group": group,
            "generated_at": "2026-02-15T00:00:00",
            "summary": f"ok:{group}",
            "next_step": "ok",
            "raw": "ok",
            "provider": "mock-live",
            "model": "mock-model",
            "live_api": True,
            "latency_ms": 88,
            "estimated_cost_usd": 0.0003,
            "task_type": str(kwargs.get("task_type", "coding")),
            "error": None,
        }

    def _run_once(strength: str, suffix: str) -> dict:
        db_path = tmp_path / f"azi_rebuild_{suffix}.db"
        state_path = tmp_path / f"azi_state_{suffix}.json"
        llm_cfg_path = tmp_path / "llm_config.json"
        llm_cfg_path.write_text(
            f"""
{{
  "api_live_enabled": false,
  "provider_groups": {{
    "fast_chain": [],
    "medium_chain": []
  }},
  "routing_policy": {{
    "task_preferences": {{
      "coding": ["medium_chain"]
    }},
    "work_memory_strength": "{strength}"
  }}
}}
""".strip(),
            encoding="utf-8",
        )

        conn = connect_runtime_db(str(db_path))
        try:
            state = load_runtime_state(state_path)
            enqueue_event(
                conn,
                source="manual",
                event_type="input",
                content="请修复这个 python bug",
                meta={"test": True},
            )
            with patch("azi_rebuild.runtime.generate_structured_response", side_effect=_fake_generate_structured_response):
                handled = run_single_brain_cycle(conn, state, max_events=4, base_dir=tmp_path)
            assert handled == 1
            return dict(state.get("work_memory", {}) or {})
        finally:
            conn.close()

    conservative = _run_once("conservative", "cons")
    conservative_prefs = dict(conservative.get("task_preferences", {}) or {})
    assert str(conservative.get("strength", "")) == "conservative"
    assert "coding" not in conservative_prefs

    aggressive = _run_once("aggressive", "aggr")
    aggressive_prefs = dict(aggressive.get("task_preferences", {}) or {})
    assert str(aggressive.get("strength", "")) == "aggressive"
    assert "coding" in aggressive_prefs
    assert str((aggressive_prefs.get("coding") or [""])[0]) == "medium_chain"


def test_dispatch_issue_detection_marks_smalltalk_as_non_work(tmp_path: Path) -> None:
    db_path = tmp_path / "azi_rebuild.db"
    state_path = tmp_path / "azi_state.json"

    conn = connect_runtime_db(str(db_path))
    try:
        state = load_runtime_state(state_path)
        enqueue_event(
            conn,
            source="manual",
            event_type="input",
            content="你好呀",
            meta={"test": True},
        )
        handled = run_single_brain_cycle(conn, state, max_events=2)
        assert handled == 1

        row = conn.execute(
            "SELECT payload_json FROM azi_contracts WHERE kind='dispatch_plan' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        import json
        payload = json.loads(str(row["payload_json"] or "{}"))
        assert bool(payload.get("issue_detected", True)) is False
        assert str(payload.get("task_type", "")) in {"shallow", "ops", "coding", "dream", "deep"}
        assert isinstance(payload.get("dispatch_plan", []), list)
    finally:
        conn.close()


def test_dispatch_plan_includes_dream_skill_pack(tmp_path: Path) -> None:
    db_path = tmp_path / "azi_rebuild.db"
    state_path = tmp_path / "azi_state.json"
    llm_cfg_path = tmp_path / "llm_config.json"
    llm_cfg_path.write_text(
        """
{
  "api_live_enabled": false,
  "provider_groups": {
    "dream_chain": [],
    "deep_chain": [],
    "medium_chain": []
  },
  "routing_policy": {
    "task_preferences": {
      "dream": ["dream_chain", "deep_chain"]
    },
    "task_skill_packs": {
      "dream": ["algorithmic-art", "generative-art", "imagegen"]
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    conn = connect_runtime_db(str(db_path))
    try:
        state = load_runtime_state(state_path)
        enqueue_event(
            conn,
            source="manual",
            event_type="dream_request",
            content="做一次梦境回放并产出灵感",
            meta={"test": True},
        )
        handled = run_single_brain_cycle(conn, state, max_events=4, base_dir=tmp_path)
        assert handled == 1

        row = conn.execute(
            "SELECT payload_json FROM azi_contracts WHERE kind='dispatch_plan' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row["payload_json"] or "{}"))
        skills = list(payload.get("recommended_skills", []) or [])
        assert "algorithmic-art" in skills
        assert "generative-art" in skills
        assert str(payload.get("task_type", "")) == "dream"
    finally:
        conn.close()
