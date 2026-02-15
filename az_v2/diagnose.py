from __future__ import annotations

from typing import Any

from .state import State10D, WuxingChannel


HALT_KEYWORDS = [
    "终极",
    "绝对真理",
    "自指",
    "循环",
    "无限递归",
    "cannot act",
]


def halt_check(text: str, actionable_advice: list[str]) -> dict[str, Any]:
    content = str(text or "").lower()
    for kw in HALT_KEYWORDS:
        if kw.lower() in content:
            return {"triggered": True, "reason": f"keyword:{kw}"}
    if not actionable_advice:
        return {"triggered": True, "reason": "no_new_actionability"}
    return {"triggered": False, "reason": None}


def diagnose(object_description: str, state: State10D | None = None) -> dict[str, Any]:
    s = state or State10D()
    text = str(object_description or "").strip()

    dimension_state: dict[str, dict[str, Any]] = {}
    invalidations: list[str] = []
    actionable: list[str] = []
    summaries: list[str] = []

    d4 = _diagnose_4d(text, s)
    dimension_state["d4"] = d4["payload"]
    invalidations.extend(d4["invalidation_conditions"])
    actionable.extend(d4["actionable_advice"])
    summaries.append(d4["summary"])
    if not d4["valid"]:
        return _build_result(dimension_state, summaries, actionable, invalidations, text)

    d5 = _diagnose_5d(text, s)
    dimension_state["d5"] = d5["payload"]
    invalidations.extend(d5["invalidation_conditions"])
    actionable.extend(d5["actionable_advice"])
    summaries.append(d5["summary"])
    if not d5["valid"]:
        return _build_result(dimension_state, summaries, actionable, invalidations, text)

    d6 = _diagnose_6d(text, s)
    dimension_state["d6"] = d6["payload"]
    invalidations.extend(d6["invalidation_conditions"])
    actionable.extend(d6["actionable_advice"])
    summaries.append(d6["summary"])
    if not d6["valid"]:
        return _build_result(dimension_state, summaries, actionable, invalidations, text)

    d7 = _diagnose_7d(text, s)
    dimension_state["d7"] = d7["payload"]
    invalidations.extend(d7["invalidation_conditions"])
    actionable.extend(d7["actionable_advice"])
    summaries.append(d7["summary"])
    if not d7["valid"]:
        return _build_result(dimension_state, summaries, actionable, invalidations, text)

    d8 = _diagnose_8d(text, s)
    dimension_state["d8"] = d8["payload"]
    invalidations.extend(d8["invalidation_conditions"])
    actionable.extend(d8["actionable_advice"])
    summaries.append(d8["summary"])

    return _build_result(dimension_state, summaries, actionable, invalidations, text)


def _build_result(
    dimension_state: dict[str, dict[str, Any]],
    summaries: list[str],
    actionable: list[str],
    invalidations: list[str],
    text: str,
) -> dict[str, Any]:
    actionable = _ensure_actionable(actionable, dimension_state)
    halt = halt_check(text, actionable)
    return {
        "state": dimension_state,
        "diagnosis": " ".join([s for s in summaries if s]),
        "actionable_advice": actionable,
        "invalidation_conditions": invalidations,
        "halt_check": halt,
    }


def _ensure_actionable(
    actionable: list[str],
    dimension_state: dict[str, dict[str, Any]],
) -> list[str]:
    out = [a for a in actionable if a]
    has_67 = any(a.startswith("[6D]") or a.startswith("[7D]") for a in out)
    if has_67:
        return out

    d6 = dimension_state.get("d6", {})
    low_paths = d6.get("low_cost_paths") or []
    if low_paths:
        out.append(f"[6D] 优先沿低耗散路径执行: {low_paths[0]}")
        return out

    d7 = dimension_state.get("d7", {})
    role = d7.get("current_role")
    if role:
        out.append(f"[7D] 先明确角色边界与退出代价: {role}")
    return out


def _diagnose_4d(text: str, state: State10D) -> dict[str, Any]:
    near_threshold = state.d4_approaching_threshold or any(
        kw in text for kw in ("阈值", "临界", "崩", "耗尽", "deadline")
    )
    change_type = state.d4_change.value
    payload = {
        "key_variables": _pick_key_variables(text),
        "threshold_proximity": "high" if near_threshold else "normal",
        "change_type": change_type,
        "phase_transition": state.d4_phase_transition,
    }
    return {
        "valid": bool(payload["key_variables"]),
        "payload": payload,
        "summary": f"4D: 变化类型={change_type}, 临界接近={payload['threshold_proximity']}",
        "actionable_advice": [
            "[4D] 对关键快变量设置阈值告警，并定义触发动作。"
        ],
        "invalidation_conditions": [
            "若关键变量发生替换或观测延迟超过1个周期，4D判断失效。"
        ],
    }


def _diagnose_5d(text: str, state: State10D) -> dict[str, Any]:
    risk = state.d5_depletion_risk
    payload = {
        "recovery_exists": state.d5_recovery_rate >= 0.3,
        "recovery_rate": state.d5_recovery_rate,
        "long_term_cost": state.d5_long_term_cost,
        "cycle_phase": state.d5_cycle_phase.value,
        "depletion_risk": risk,
    }
    advice: list[str] = []
    if risk >= 0.7:
        advice.append("[5D] 将高耗散任务拆分为短周期批次，优先降低枯竭风险。")
    if state.d5_recovery_rate < 0.3:
        advice.append("[5D] 增加恢复窗口或替换执行节奏，提升恢复率。")
    return {
        "valid": True,
        "payload": payload,
        "summary": f"5D: 恢复率={state.d5_recovery_rate:.2f}, 枯竭风险={risk:.2f}",
        "actionable_advice": advice,
        "invalidation_conditions": [
            "若外部资源注入或约束突然变化，5D持续性判断需重算。"
        ],
    }


def _diagnose_6d(text: str, state: State10D) -> dict[str, Any]:
    ordered = sorted(state.d6_kappa.items(), key=lambda item: item[1])
    low = [pair[0].value for pair in ordered[:2]]
    high = [pair[0].value for pair in ordered[-2:]]
    payload = {
        "kappa_vector": {k.value: float(v) for k, v in state.d6_kappa.items()},
        "low_cost_paths": low,
        "high_cost_paths": high,
    }
    advice = []
    if low:
        advice.append(f"[6D] 当前优先走低耗散通道: {', '.join(low)}")
    if high:
        advice.append(f"[6D] 对高耗散通道设置限流: {', '.join(high)}")
    return {
        "valid": True,
        "payload": payload,
        "summary": f"6D: 低耗散={','.join(low)}; 高耗散={','.join(high)}",
        "actionable_advice": advice,
        "invalidation_conditions": [
            "若偏置矩阵被策略更新，6D建议需同步刷新。"
        ],
    }


def _diagnose_7d(text: str, state: State10D) -> dict[str, Any]:
    role = state.d7_role_id.strip()
    payload = {
        "current_role": role or None,
        "irreversible_items": list(state.d7_irreversible_commitments),
        "exit_cost": state.d7_exit_cost,
    }
    valid = bool(role)
    advice = []
    if valid:
        advice.append(f"[7D] 以角色 `{role}` 为边界定义可逆与不可逆动作清单。")
    else:
        advice.append("[7D] 先定义角色ID，否则无法稳定评估不可逆承诺。")
    return {
        "valid": valid,
        "payload": payload,
        "summary": f"7D: 角色={'未定义' if not role else role}, 退出代价={state.d7_exit_cost:.2f}",
        "actionable_advice": advice,
        "invalidation_conditions": [
            "若角色责任重组，7D判断失效。"
        ],
    }


def _diagnose_8d(text: str, state: State10D) -> dict[str, Any]:
    payload = {
        "needs_退位": bool(state.d8_active),
        "return_path": state.d8_return_path,
        "projection_loss": list(state.d8_projection_loss),
        "max_duration": state.d8_max_duration,
    }
    advice: list[str] = []
    if state.d8_active:
        advice.append(
            f"[8D] 退位模式已激活，必须在 {state.d8_max_duration} 步内按 `{state.d8_return_path}` 回到6D/7D。"
        )
    return {
        "valid": True,
        "payload": payload,
        "summary": "8D: 退位激活" if state.d8_active else "8D: 无需退位",
        "actionable_advice": advice,
        "invalidation_conditions": [
            "若退位路径不可达，必须立即退出8D并回落7D。"
        ],
    }


def _pick_key_variables(text: str) -> list[str]:
    if not text:
        return []
    keyword_map = {
        "资金": "资金燃烧率",
        "团队": "团队吞吐",
        "风险": "风险暴露",
        "周期": "迭代周期",
        "并发": "并发冲突",
        "缓存": "上下文缓存命中",
        "性能": "延迟与吞吐",
    }
    found = [name for k, name in keyword_map.items() if k in text]
    if not found:
        return ["关键变量待补充"]
    return found

