from __future__ import annotations

from azi_rebuild.routing import (
    choose_provider_group_with_meta,
    generate_structured_response,
    infer_task_type,
)


def test_infer_task_type_covers_core_paths() -> None:
    assert (
        infer_task_type(
            action="escalate_dream",
            risk_level="mid",
            event_type="dream_request",
            prompt="",
            objective="",
        )
        == "dream"
    )
    assert (
        infer_task_type(
            action="plan_next",
            risk_level="low",
            event_type="input",
            prompt="请修复这个 python traceback",
            objective="",
        )
        == "coding"
    )
    assert (
        infer_task_type(
            action="plan_next",
            risk_level="high",
            event_type="input",
            prompt="评估这个高风险操作",
            objective="",
        )
        == "risk_control"
    )


def test_choose_provider_group_with_meta_uses_scoreboard() -> None:
    cfg = {
        "provider_groups": {
            "shallow_chain": ["a"],
            "fast_chain": ["b"],
            "medium_chain": ["c"],
            "deep_chain": ["d"],
        }
    }
    orch = {
        "group_metrics": {
            "shallow_chain": {"total": 10, "success": 9, "success_rate": 0.9, "latency_ms_ema": 1200, "cost_usd_ema": 0.001},
            "fast_chain": {"total": 10, "success": 4, "success_rate": 0.4, "latency_ms_ema": 400, "cost_usd_ema": 0.001},
            "medium_chain": {"total": 10, "success": 5, "success_rate": 0.5, "latency_ms_ema": 1600, "cost_usd_ema": 0.002},
            "deep_chain": {"total": 10, "success": 3, "success_rate": 0.3, "latency_ms_ema": 5000, "cost_usd_ema": 0.01},
        }
    }
    meta = choose_provider_group_with_meta(
        action="plan_next",
        risk_level="low",
        llm_config=cfg,
        route_context={"event_type": "input", "prompt": "给一个简短建议", "objective": "短反馈"},
        orchestration=orch,
    )
    assert str(meta.get("group")) == "shallow_chain"
    assert str(meta.get("task_type")) in {"shallow_reaction", "analysis"}
    assert isinstance(meta.get("scores"), dict)


def test_choose_provider_group_with_meta_forces_deep_for_high_risk() -> None:
    cfg = {
        "provider_groups": {
            "shallow_chain": ["a"],
            "fast_chain": ["b"],
            "deep_chain": ["d"],
        }
    }
    meta = choose_provider_group_with_meta(
        action="plan_next",
        risk_level="high",
        llm_config=cfg,
        route_context={"event_type": "input", "prompt": "高风险操作", "objective": "审查"},
        orchestration={},
    )
    assert str(meta.get("group")) == "deep_chain"
    assert str(meta.get("reason")) == "risk_high_force_deep"


def test_route_candidates_respect_custom_task_preferences() -> None:
    cfg = {
        "provider_groups": {
            "coder_chain": ["a"],
            "deep_chain": ["b"],
            "medium_chain": ["c"],
            "shallow_chain": ["d"],
        },
        "routing_policy": {
            "task_preferences": {
                "coding": ["coder_chain", "deep_chain", "medium_chain"],
            }
        },
    }
    meta = choose_provider_group_with_meta(
        action="plan_next",
        risk_level="low",
        llm_config=cfg,
        route_context={"event_type": "input", "prompt": "请帮我修复这个 bug", "objective": "代码修复"},
        orchestration={},
    )
    candidates = list(meta.get("candidates", []) or [])
    assert candidates[:2] == ["coder_chain", "deep_chain"]


def test_generate_structured_response_fallback_keeps_orchestration_fields() -> None:
    payload = generate_structured_response(
        group="shallow_chain",
        prompt="hello",
        objective="world",
        llm_config={"api_live_enabled": False, "provider_groups": {"shallow_chain": []}},
        task_type="shallow_reaction",
    )
    assert str(payload.get("provider")) == "fallback-local"
    assert bool(payload.get("live_api", False)) is False
    assert "latency_ms" in payload
    assert "estimated_cost_usd" in payload
    assert str(payload.get("task_type")) == "shallow_reaction"
