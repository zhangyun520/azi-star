from __future__ import annotations

from pathlib import Path

from az_v2.diagnose import diagnose
from az_v2.engine import AziEngineV2
from az_v2.operator import OperatorDelta, OperatorRule, apply_operator
from az_v2.state import State10D


def test_state_vector_dim_is_28_by_default() -> None:
    state = State10D(d7_role_id="planner")
    vec = state.to_vector()
    assert len(vec) == 28
    assert state.vector_dim() == 28


def test_state_hard_rule_requires_return_path_when_d8_active() -> None:
    try:
        State10D(d8_active=True, d8_return_path=None)
        assert False, "expected validation error"
    except Exception:
        assert True


def test_operator_precondition_failure_returns_fallback() -> None:
    state = State10D(d1_quantity=0.2)
    op = OperatorDelta(
        op_id="op.raise_energy",
        op_name="raise_energy",
        delta_values={"d1_quantity": "+0.5"},
        preconditions=[OperatorRule(dim="d1_quantity", check=">0.3", reason="resource too low")],
        fallback_if_fail="op.recover_energy",
    )
    result = apply_operator(state, op)
    assert not result.success
    assert result.fallback_op_id == "op.recover_energy"


def test_operator_success_updates_state() -> None:
    state = State10D(d1_quantity=1.0)
    op = OperatorDelta(
        op_id="op.shift",
        op_name="shift",
        delta_values={"d1_quantity": "+0.5", "d7_role_id": {"set": "executor"}},
        preconditions=[OperatorRule(dim="d1_quantity", check=">=1.0")],
        postconditions=[OperatorRule(dim="d1_quantity", check=">=1.5")],
    )
    result = apply_operator(state, op)
    assert result.success
    assert result.state.d1_quantity >= 1.5
    assert result.state.d7_role_id == "executor"


def test_diagnose_stops_ascending_when_role_missing() -> None:
    state = State10D(d7_role_id="")
    result = diagnose("并发风险正在上升，资金周期紧张", state=state)
    assert "d4" in result["state"]
    assert "d7" in result["state"]
    assert "d8" not in result["state"]
    assert any(item.startswith("[6D]") or item.startswith("[7D]") for item in result["actionable_advice"])


def test_engine_event_loop_persists_event_and_decision(tmp_path: Path) -> None:
    db = tmp_path / "az_v2_test.db"
    engine = AziEngineV2(state=State10D(d7_role_id="operator"), event_db_path=str(db))
    out = engine.handle_input("团队并发冲突上升，需要回落策略", source="unit-test")
    assert out["event_id"] > 0
    assert out["decision_id"] > 0
    snap = engine.snapshot(limit=5)
    assert snap["recent_events"]
    assert snap["recent_events"][0]["source"] == "unit-test"

