from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from .state import State10D


_COMPARE = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


class OperatorRule(BaseModel):
    dim: str
    check: str
    reason: str = ""
    field: str | None = None

    def target_key(self) -> str:
        return self.field or self.dim


class OperatorDelta(BaseModel):
    op_id: str
    op_name: str
    target_dims: list[str] = Field(default_factory=list)
    delta_values: dict[str, Any] = Field(default_factory=dict)
    kappa_policy: Literal["decrease", "increase", "hold", "封装"] = "hold"
    preconditions: list[OperatorRule] = Field(default_factory=list)
    postconditions: list[OperatorRule] = Field(default_factory=list)
    fallback_if_fail: str | None = None
    invalidation_condition: str = ""


@dataclass
class ApplyResult:
    success: bool
    state: State10D
    errors: list[str]
    fallback_op_id: str | None = None


def apply_operator(state: State10D, op: OperatorDelta) -> ApplyResult:
    pre_errors = _evaluate_rules(state, op.preconditions, stage="pre")
    if pre_errors:
        return ApplyResult(
            success=False,
            state=state,
            errors=pre_errors,
            fallback_op_id=op.fallback_if_fail,
        )

    payload = state.model_dump()
    patch_errors: list[str] = []
    for key, delta in op.delta_values.items():
        if key not in payload:
            patch_errors.append(f"delta key not found: {key}")
            continue
        try:
            payload[key] = _apply_delta(payload[key], delta)
        except Exception as exc:
            patch_errors.append(f"delta apply failed for {key}: {exc}")

    if patch_errors:
        return ApplyResult(
            success=False,
            state=state,
            errors=patch_errors,
            fallback_op_id=op.fallback_if_fail,
        )

    try:
        next_state = State10D.model_validate(payload)
    except Exception as exc:
        return ApplyResult(
            success=False,
            state=state,
            errors=[f"state validation failed: {exc}"],
            fallback_op_id=op.fallback_if_fail,
        )

    post_errors = _evaluate_rules(next_state, op.postconditions, stage="post")
    if post_errors:
        return ApplyResult(
            success=False,
            state=state,
            errors=post_errors,
            fallback_op_id=op.fallback_if_fail,
        )

    return ApplyResult(success=True, state=next_state, errors=[])


def _apply_delta(current: Any, delta: Any) -> Any:
    if isinstance(delta, dict) and "set" in delta:
        return delta["set"]

    if isinstance(delta, (int, float)):
        if isinstance(current, (int, float)):
            return float(current) + float(delta)
        return delta

    if isinstance(delta, str):
        inc = re.match(r"^\s*([+-]\d+(?:\.\d+)?)\s*$", delta)
        if inc and isinstance(current, (int, float)):
            return float(current) + float(inc.group(1))
        return delta

    return delta


def _evaluate_rules(state: State10D, rules: list[OperatorRule], stage: str) -> list[str]:
    errors: list[str] = []
    for rule in rules:
        key = rule.target_key()
        try:
            actual = getattr(state, key)
        except AttributeError:
            errors.append(f"{stage}condition key not found: {key}")
            continue
        ok, err = _eval_check(actual, rule.check)
        if not ok:
            reason = f", reason={rule.reason}" if rule.reason else ""
            errors.append(f"{stage}condition failed: {key} {rule.check}, actual={actual}{reason}")
            if err:
                errors.append(f"{stage}condition eval error: {err}")
    return errors


def _eval_check(actual: Any, check: str) -> tuple[bool, str]:
    m = re.match(r"^\s*(<=|>=|==|!=|<|>)\s*(.+?)\s*$", str(check))
    if not m:
        return False, f"unsupported check syntax: {check}"
    op_str, rhs_raw = m.group(1), m.group(2)
    comp = _COMPARE[op_str]

    rhs = _parse_literal(rhs_raw)
    if isinstance(actual, (int, float)) and isinstance(rhs, (int, float)):
        return bool(comp(float(actual), float(rhs))), ""
    return bool(comp(str(actual), str(rhs))), ""


def _parse_literal(text: str) -> Any:
    t = str(text).strip()
    if t.lower() == "true":
        return True
    if t.lower() == "false":
        return False
    try:
        return float(t)
    except Exception:
        return t.strip("\"'")

