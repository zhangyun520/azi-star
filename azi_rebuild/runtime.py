from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from az_v2.diagnose import diagnose
from az_v2.state import ChangeType, CyclePhase, State10D, WuxingChannel
from .deep_safety import ensure_deep_safety_schema, rollback_stage, run_deep_safety_chain
from .contracts import (
    Approval,
    DispatchItem,
    DispatchPlan,
    EvalResult,
    ExecTrace,
    Plan,
    PlanStep,
    RewardUpdate,
    RiskReport,
    ToolCallTrace,
    contract_to_row,
    make_contract_id,
)
from .governance import (
    assess_risk,
    check_immutable_guard,
    emergence_guard,
    ensure_governance_schema,
    load_approval_override,
    record_guard_event,
    record_risk_gate,
)
from .memory import ensure_memory_schema, hybrid_retrieve, ingest_event_memory
from .protocol import make_evidence_pack, make_proposal, make_task, protocol_to_row
from .routing import (
    choose_provider_group_with_meta,
    generate_structured_response,
    infer_task_type,
    load_llm_config,
)


DEFAULT_RUNTIME_STATE: dict[str, Any] = {
    "cycle": 0,
    "energy": 0.8,
    "stress": 0.2,
    "uncertainty": 0.3,
    "integrity": 0.85,
    "continuity": 0.7,
    "permission_level": 1,
    "last_event_id": 0,
    "role_id": "operator",
    "last_action": "-",
    "last_reason": "-",
    "stability": {},
    "orchestration": {},
    "work_memory": {},
}

DEFAULT_STABILITY_STATE: dict[str, Any] = {
    "mode": "normal",
    "panic_count": 0,
    "degraded_cycles": 0,
    "requested_brain_events": 12,
    "effective_brain_events": 12,
    "requested_worker_events": 6,
    "effective_worker_events": 6,
    "last_budget_reason": "normal",
    "last_route_group": "-",
    "last_route_override": "",
    "last_route_error": "",
    "consecutive_fallbacks": 0,
    "route_fail_streak": {},
    "route_success_count": {},
    "route_cooldown_until": {},
    "last_updated": "-",
}


DEFAULT_ORCHESTRATION_STATE: dict[str, Any] = {
    "last_task_type": "-",
    "last_route_group": "-",
    "last_route_reason": "-",
    "last_provider": "-",
    "last_model": "-",
    "last_error": "",
    "last_latency_ms": 0,
    "last_cost_usd": 0.0,
    "updated_at": "-",
    "group_metrics": {},
    "model_metrics": {},
    "task_route_stats": {},
}


DEFAULT_WORK_MEMORY_STATE: dict[str, Any] = {
    "task_route_stats": {},
    "task_preferences": {},
    "recent_successes": [],
    "strength": "balanced",
    "updated_at": "-",
}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _ensure_stability_state(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get("stability")
    merged = dict(DEFAULT_STABILITY_STATE)
    if isinstance(raw, dict):
        merged.update(raw)

    for key in ("route_fail_streak", "route_success_count", "route_cooldown_until"):
        if not isinstance(merged.get(key), dict):
            merged[key] = {}
        else:
            merged[key] = {
                str(k): _to_int(v, default=0)
                for k, v in dict(merged.get(key) or {}).items()
                if str(k).strip()
            }

    merged["mode"] = str(merged.get("mode", "normal")).strip().lower() or "normal"
    merged["panic_count"] = max(0, _to_int(merged.get("panic_count", 0), default=0))
    merged["degraded_cycles"] = max(0, _to_int(merged.get("degraded_cycles", 0), default=0))
    merged["requested_brain_events"] = max(1, _to_int(merged.get("requested_brain_events", 12), default=12))
    merged["effective_brain_events"] = max(1, _to_int(merged.get("effective_brain_events", 12), default=12))
    merged["requested_worker_events"] = max(1, _to_int(merged.get("requested_worker_events", 6), default=6))
    merged["effective_worker_events"] = max(1, _to_int(merged.get("effective_worker_events", 6), default=6))
    merged["consecutive_fallbacks"] = max(0, _to_int(merged.get("consecutive_fallbacks", 0), default=0))
    merged["last_budget_reason"] = str(merged.get("last_budget_reason", "normal"))[:320]
    merged["last_route_group"] = str(merged.get("last_route_group", "-"))[:120]
    merged["last_route_override"] = str(merged.get("last_route_override", ""))[:220]
    merged["last_route_error"] = str(merged.get("last_route_error", ""))[:320]
    merged["last_updated"] = str(merged.get("last_updated", "-"))[:40]
    state["stability"] = merged
    return merged


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _ensure_orchestration_state(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get("orchestration")
    merged = dict(DEFAULT_ORCHESTRATION_STATE)
    if isinstance(raw, dict):
        merged.update(raw)

    for key in ("group_metrics", "model_metrics", "task_route_stats"):
        if not isinstance(merged.get(key), dict):
            merged[key] = {}
        else:
            merged[key] = dict(merged.get(key) or {})

    merged["last_task_type"] = str(merged.get("last_task_type", "-"))[:80]
    merged["last_route_group"] = str(merged.get("last_route_group", "-"))[:80]
    merged["last_route_reason"] = str(merged.get("last_route_reason", "-"))[:220]
    merged["last_provider"] = str(merged.get("last_provider", "-"))[:80]
    merged["last_model"] = str(merged.get("last_model", "-"))[:120]
    merged["last_error"] = str(merged.get("last_error", ""))[:320]
    merged["last_latency_ms"] = max(0, _to_int(merged.get("last_latency_ms", 0), default=0))
    merged["last_cost_usd"] = max(0.0, _safe_float(merged.get("last_cost_usd", 0.0), default=0.0))
    merged["updated_at"] = str(merged.get("updated_at", "-"))[:40]

    state["orchestration"] = merged
    return merged


def _ensure_work_memory_state(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get("work_memory")
    merged = dict(DEFAULT_WORK_MEMORY_STATE)
    if isinstance(raw, dict):
        merged.update(raw)

    task_stats_raw = merged.get("task_route_stats")
    if not isinstance(task_stats_raw, dict):
        task_stats_raw = {}
    normalized_stats: dict[str, dict[str, dict[str, Any]]] = {}
    for task_key, group_rows in dict(task_stats_raw or {}).items():
        tk = str(task_key or "").strip()[:80]
        if not tk or not isinstance(group_rows, dict):
            continue
        out_row: dict[str, dict[str, Any]] = {}
        for group_key, item in dict(group_rows or {}).items():
            gk = str(group_key or "").strip()[:80]
            if not gk or not isinstance(item, dict):
                continue
            out_row[gk] = {
                "total": max(0, _to_int(item.get("total", 0), default=0)),
                "success": max(0, _to_int(item.get("success", 0), default=0)),
                "fail": max(0, _to_int(item.get("fail", 0), default=0)),
                "fallback": max(0, _to_int(item.get("fallback", 0), default=0)),
                "success_rate": round(max(0.0, _safe_float(item.get("success_rate", 0.0), default=0.0)), 4),
                "fallback_ratio": round(max(0.0, _safe_float(item.get("fallback_ratio", 0.0), default=0.0)), 4),
                "last_provider": str(item.get("last_provider", "-"))[:80],
                "last_model": str(item.get("last_model", "-"))[:120],
                "last_error": str(item.get("last_error", ""))[:220],
                "last_seen": str(item.get("last_seen", "-"))[:40],
            }
        if out_row:
            normalized_stats[tk] = out_row
    merged["task_route_stats"] = normalized_stats

    task_prefs_raw = merged.get("task_preferences")
    if not isinstance(task_prefs_raw, dict):
        task_prefs_raw = {}
    normalized_prefs: dict[str, list[str]] = {}
    for task_key, groups in dict(task_prefs_raw or {}).items():
        tk = str(task_key or "").strip()[:80]
        if not tk:
            continue
        if isinstance(groups, list):
            items = [str(x).strip()[:80] for x in groups if str(x).strip()]
        elif isinstance(groups, str):
            items = [x.strip()[:80] for x in str(groups).split(",") if x.strip()]
        else:
            items = []
        dedup: list[str] = []
        for g in items:
            if g not in dedup:
                dedup.append(g)
        normalized_prefs[tk] = dedup[:6]
    merged["task_preferences"] = normalized_prefs

    recent = merged.get("recent_successes")
    if not isinstance(recent, list):
        recent = []
    normalized_recent: list[dict[str, Any]] = []
    for item in list(recent)[-30:]:
        if not isinstance(item, dict):
            continue
        normalized_recent.append(
            {
                "ts": str(item.get("ts", "-"))[:40],
                "task_type": str(item.get("task_type", "analysis"))[:80],
                "group": str(item.get("group", "-"))[:80],
                "provider": str(item.get("provider", "-"))[:80],
                "model": str(item.get("model", "-"))[:120],
                "summary": str(item.get("summary", ""))[:180],
            }
        )
    merged["recent_successes"] = normalized_recent
    merged["strength"] = _normalize_memory_strength(merged.get("strength", "balanced"))
    merged["updated_at"] = str(merged.get("updated_at", "-"))[:40]
    state["work_memory"] = merged
    return merged


def _normalize_memory_strength(value: Any) -> str:
    raw = str(value or "").strip().lower()
    alias = {
        "conservative": "conservative",
        "balanced": "balanced",
        "aggressive": "aggressive",
        "保守": "conservative",
        "均衡": "balanced",
        "激进": "aggressive",
    }
    return alias.get(raw, "balanced")


def _work_memory_policy_from_llm_cfg(llm_cfg: dict[str, Any]) -> dict[str, Any]:
    policy = dict(dict(llm_cfg or {}).get("routing_policy", {}) or {})
    strength = _normalize_memory_strength(policy.get("work_memory_strength", policy.get("memory_strength", "balanced")))
    if strength == "conservative":
        return {
            "strength": strength,
            "bias_limit": 2,
            "min_total_for_pref": 4,
            "min_score_for_pref": 0.68,
            "max_pref_groups": 2,
        }
    if strength == "aggressive":
        return {
            "strength": strength,
            "bias_limit": 6,
            "min_total_for_pref": 1,
            "min_score_for_pref": 0.35,
            "max_pref_groups": 6,
        }
    return {
        "strength": "balanced",
        "bias_limit": 4,
        "min_total_for_pref": 2,
        "min_score_for_pref": 0.5,
        "max_pref_groups": 4,
    }


def _memory_biased_llm_config(
    *,
    state: dict[str, Any],
    llm_cfg: dict[str, Any],
    task_type: str,
) -> tuple[dict[str, Any], list[str]]:
    wm = _ensure_work_memory_state(state)
    mem_policy = _work_memory_policy_from_llm_cfg(llm_cfg)
    prefs_map = dict(wm.get("task_preferences", {}) or {})
    preferred = [str(x).strip() for x in list(prefs_map.get(str(task_type), []) or []) if str(x).strip()][
        : max(1, _to_int(mem_policy.get("bias_limit", 4), default=4))
    ]
    if not preferred:
        return llm_cfg, []

    cfg = copy.deepcopy(dict(llm_cfg or {}))
    policy = dict(cfg.get("routing_policy", {}) or {})
    task_prefs = dict(policy.get("task_preferences", {}) or {})
    existing = task_prefs.get(str(task_type), [])
    if isinstance(existing, list):
        existing_list = [str(x).strip() for x in existing if str(x).strip()]
    elif isinstance(existing, str):
        existing_list = [x.strip() for x in str(existing).split(",") if x.strip()]
    else:
        existing_list = []

    merged: list[str] = []
    for g in [*preferred, *existing_list]:
        if g not in merged:
            merged.append(g)
    task_prefs[str(task_type)] = merged[:8]
    policy["task_preferences"] = task_prefs
    cfg["routing_policy"] = policy
    return cfg, merged[:8]


def _update_work_memory(
    state: dict[str, Any],
    *,
    task_type: str,
    requested_group: str,
    actual_group: str,
    route_payload: dict[str, Any],
    llm_cfg: dict[str, Any] | None = None,
) -> None:
    wm = _ensure_work_memory_state(state)
    mem_policy = _work_memory_policy_from_llm_cfg(dict(llm_cfg or {}))
    wm["strength"] = str(mem_policy.get("strength", "balanced"))
    task_stats = dict(wm.get("task_route_stats", {}) or {})
    task_prefs = dict(wm.get("task_preferences", {}) or {})
    recent_successes = list(wm.get("recent_successes", []) or [])

    tt = str(task_type or "analysis")[:80]
    group_key = str(actual_group or requested_group or "-")[:80]
    provider = str(route_payload.get("provider", "-") or "-")[:80]
    model = str(route_payload.get("model", "-") or "-")[:120]
    live_api = bool(route_payload.get("live_api", False))
    error = str(route_payload.get("error", "") or "").strip()
    success = live_api and (not bool(error)) and provider not in {"fallback-local", "-"}
    fallback_used = provider in {"fallback-local", "-"} or (not live_api)

    row = dict(task_stats.get(tt, {}) or {})
    item = dict(row.get(group_key, {}) or {})
    total = _to_int(item.get("total", 0), default=0) + 1
    succ = _to_int(item.get("success", 0), default=0) + (1 if success else 0)
    fail = _to_int(item.get("fail", 0), default=0) + (0 if success else 1)
    fallback = _to_int(item.get("fallback", 0), default=0) + (1 if fallback_used else 0)
    item["total"] = total
    item["success"] = succ
    item["fail"] = fail
    item["fallback"] = fallback
    item["success_rate"] = round(succ / max(1, total), 4)
    item["fallback_ratio"] = round(fallback / max(1, total), 4)
    item["last_provider"] = provider
    item["last_model"] = model
    item["last_error"] = error[:220]
    item["last_seen"] = now_iso()
    row[group_key] = item
    task_stats[tt] = row

    ranked: list[tuple[str, float, int]] = []
    for g, metrics in row.items():
        m = dict(metrics or {})
        g_total = max(0, _to_int(m.get("total", 0), default=0))
        if g_total <= 0:
            continue
        sr = max(0.0, min(1.0, _safe_float(m.get("success_rate", 0.0), default=0.0)))
        fr = max(0.0, min(1.0, _safe_float(m.get("fallback_ratio", 0.0), default=0.0)))
        confidence = min(1.0, g_total / 10.0)
        score = (sr * 0.72) + ((1.0 - fr) * 0.18) + (confidence * 0.1)
        ranked.append((str(g), score, g_total))
    ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)
    min_total_for_pref = max(1, _to_int(mem_policy.get("min_total_for_pref", 2), default=2))
    min_score_for_pref = max(0.0, min(1.0, _safe_float(mem_policy.get("min_score_for_pref", 0.5), default=0.5)))
    max_pref_groups = max(1, _to_int(mem_policy.get("max_pref_groups", 4), default=4))
    preferred_groups = [
        g for g, score, total_count in ranked if total_count >= min_total_for_pref and score >= min_score_for_pref
    ][:max_pref_groups]
    strength = str(mem_policy.get("strength", "balanced"))
    if not preferred_groups and success:
        if strength == "aggressive":
            preferred_groups = [group_key]
        elif strength == "balanced" and total >= 2:
            preferred_groups = [group_key]
    if preferred_groups:
        task_prefs[tt] = preferred_groups

    if success:
        recent_successes.append(
            {
                "ts": now_iso(),
                "task_type": tt,
                "group": group_key,
                "provider": provider,
                "model": model,
                "summary": str(route_payload.get("summary", ""))[:180],
            }
        )
        recent_successes = recent_successes[-30:]

    wm["task_route_stats"] = task_stats
    wm["task_preferences"] = task_prefs
    wm["recent_successes"] = recent_successes
    wm["updated_at"] = now_iso()


def _ema(old_value: float, new_value: float, alpha: float = 0.3) -> float:
    if old_value <= 0:
        return new_value
    a = clamp(float(alpha), 0.05, 0.95)
    return (old_value * (1.0 - a)) + (new_value * a)


def _update_orchestration_metrics(
    state: dict[str, Any],
    *,
    task_type: str,
    route_group: str,
    route_reason: str,
    route_payload: dict[str, Any],
) -> None:
    orch = _ensure_orchestration_state(state)
    g_metrics = dict(orch.get("group_metrics", {}) or {})
    m_metrics = dict(orch.get("model_metrics", {}) or {})
    t_stats = dict(orch.get("task_route_stats", {}) or {})

    group_key = str(route_group or "-")[:80]
    provider = str(route_payload.get("provider", "-") or "-")[:80]
    model = str(route_payload.get("model", "-") or "-")[:120]
    model_key = f"{provider}:{model}"
    latency_ms = max(0.0, _safe_float(route_payload.get("latency_ms", 0), default=0.0))
    cost_usd = max(0.0, _safe_float(route_payload.get("estimated_cost_usd", 0.0), default=0.0))
    live_api = bool(route_payload.get("live_api", False))
    error = str(route_payload.get("error", "") or "").strip()
    success = live_api and (not bool(error)) and provider not in {"fallback-local", "-"}
    fallback_used = provider in {"fallback-local", "-"} or (not live_api)

    g = dict(g_metrics.get(group_key, {}) or {})
    g_total = _to_int(g.get("total", 0), default=0) + 1
    g_success = _to_int(g.get("success", 0), default=0) + (1 if success else 0)
    g_fail = _to_int(g.get("fail", 0), default=0) + (0 if success else 1)
    g_fallback = _to_int(g.get("fallback", 0), default=0) + (1 if fallback_used else 0)
    g["total"] = g_total
    g["success"] = g_success
    g["fail"] = g_fail
    g["fallback"] = g_fallback
    g["fallback_ratio"] = round(g_fallback / max(1, g_total), 4)
    g["success_rate"] = round(g_success / max(1, g_total), 4)
    g["latency_ms_ema"] = round(_ema(_safe_float(g.get("latency_ms_ema", 0.0)), latency_ms), 2)
    g["cost_usd_ema"] = round(_ema(_safe_float(g.get("cost_usd_ema", 0.0)), cost_usd), 6)
    g["last_provider"] = provider
    g["last_model"] = model
    g["last_error"] = error[:220]
    g["updated_at"] = now_iso()
    g_metrics[group_key] = g

    m = dict(m_metrics.get(model_key, {}) or {})
    m_total = _to_int(m.get("total", 0), default=0) + 1
    m_success = _to_int(m.get("success", 0), default=0) + (1 if success else 0)
    m["provider"] = provider
    m["model"] = model
    m["total"] = m_total
    m["success"] = m_success
    m["success_rate"] = round(m_success / max(1, m_total), 4)
    m["latency_ms_ema"] = round(_ema(_safe_float(m.get("latency_ms_ema", 0.0)), latency_ms), 2)
    m["cost_usd_ema"] = round(_ema(_safe_float(m.get("cost_usd_ema", 0.0)), cost_usd), 6)
    m["updated_at"] = now_iso()
    m_metrics[model_key] = m

    tt = str(task_type or "analysis")[:80]
    tt_row = dict(t_stats.get(tt, {}) or {})
    tt_row[group_key] = _to_int(tt_row.get(group_key, 0), default=0) + 1
    t_stats[tt] = tt_row

    orch["group_metrics"] = g_metrics
    orch["model_metrics"] = m_metrics
    orch["task_route_stats"] = t_stats
    orch["last_task_type"] = tt
    orch["last_route_group"] = group_key
    orch["last_route_reason"] = str(route_reason or "-")[:220]
    orch["last_provider"] = provider
    orch["last_model"] = model
    orch["last_error"] = error[:320]
    orch["last_latency_ms"] = int(round(latency_ms))
    orch["last_cost_usd"] = float(round(cost_usd, 6))
    orch["updated_at"] = now_iso()


def _fallback_group(llm_cfg: dict[str, Any]) -> str:
    groups = dict(llm_cfg.get("provider_groups", {}) or {})
    if "shallow_chain" in groups:
        return "shallow_chain"
    if "fast_chain" in groups:
        return "fast_chain"
    if "medium_chain" in groups:
        return "medium_chain"
    return "fallback-local"


def _compute_brain_event_budget(state: dict[str, Any], requested_max: int) -> int:
    st = _ensure_stability_state(state)
    requested = max(1, min(int(requested_max), 200))
    stress = float(state.get("stress", 0.2))
    energy = float(state.get("energy", 0.8))
    uncertainty = float(state.get("uncertainty", 0.3))
    continuity = float(state.get("continuity", 0.7))

    scale = 1.0
    reasons: list[str] = []
    if stress >= 0.8:
        scale *= 0.45
        reasons.append("stress_high")
    elif stress >= 0.65:
        scale *= 0.7
        reasons.append("stress_up")

    if energy <= 0.2:
        scale *= 0.6
        reasons.append("energy_low")
    elif energy <= 0.35:
        scale *= 0.8
        reasons.append("energy_down")

    if uncertainty >= 0.75:
        scale *= 0.8
        reasons.append("uncertainty_high")

    if continuity <= 0.3:
        scale *= 0.8
        reasons.append("continuity_low")

    if str(st.get("mode", "normal")) == "degraded":
        scale *= 0.8
        reasons.append("degraded_mode")

    effective = max(1, min(requested, int(round(requested * scale))))
    st["requested_brain_events"] = requested
    st["effective_brain_events"] = effective
    st["last_budget_reason"] = "normal" if not reasons else ",".join(reasons)
    st["last_updated"] = now_iso()
    if effective < requested:
        st["degraded_cycles"] = _to_int(st.get("degraded_cycles", 0), default=0) + 1
    return effective


def _compute_worker_event_budget(state: dict[str, Any], requested_max: int) -> int:
    st = _ensure_stability_state(state)
    requested = max(1, min(int(requested_max), 200))
    stress = float(state.get("stress", 0.2))
    energy = float(state.get("energy", 0.8))

    scale = 1.0
    reasons: list[str] = []
    if stress >= 0.85:
        scale *= 0.6
        reasons.append("worker_stress_high")
    if energy <= 0.15:
        scale *= 0.7
        reasons.append("worker_energy_low")
    if str(st.get("mode", "normal")) == "degraded":
        scale *= 0.8
        reasons.append("worker_degraded_mode")

    effective = max(1, min(requested, int(round(requested * scale))))
    st["requested_worker_events"] = requested
    st["effective_worker_events"] = effective
    if reasons:
        st["last_budget_reason"] = str(st.get("last_budget_reason", "normal")) + "|" + ",".join(reasons)
    st["last_updated"] = now_iso()
    return effective


def _apply_route_cooldown_override(
    state: dict[str, Any],
    llm_cfg: dict[str, Any],
    route_group: str,
) -> tuple[str, str]:
    st = _ensure_stability_state(state)
    cooldowns = dict(st.get("route_cooldown_until", {}) or {})
    cycle = _to_int(state.get("cycle", 0), default=0)
    key = str(route_group or "").strip()
    if not key:
        return _fallback_group(llm_cfg), "empty_route_group"
    until = _to_int(cooldowns.get(key, 0), default=0)
    if until > cycle:
        fallback = _fallback_group(llm_cfg)
        reason = f"cooldown:{key}->{fallback}@{until}"
        st["mode"] = "degraded"
        st["last_route_override"] = reason[:220]
        st["last_updated"] = now_iso()
        return fallback, reason[:220]
    st["last_route_override"] = ""
    return key, ""


def _observe_route_outcome(
    state: dict[str, Any],
    *,
    requested_group: str,
    actual_group: str,
    route_payload: dict[str, Any],
    llm_cfg: dict[str, Any],
) -> None:
    st = _ensure_stability_state(state)
    key = str(requested_group or actual_group or "-")
    live_enabled = bool(llm_cfg.get("api_live_enabled", False))
    live_api = bool(route_payload.get("live_api", False))
    route_error = str(route_payload.get("error", "") or "").strip()
    provider = str(route_payload.get("provider", "-")).strip()

    fail_streak = dict(st.get("route_fail_streak", {}) or {})
    success_count = dict(st.get("route_success_count", {}) or {})
    cooldowns = dict(st.get("route_cooldown_until", {}) or {})
    cycle = _to_int(state.get("cycle", 0), default=0)

    failed = live_enabled and ((not live_api) or bool(route_error))
    if failed:
        streak = _to_int(fail_streak.get(key, 0), default=0) + 1
        fail_streak[key] = streak
        st["last_route_error"] = (route_error or "live_route_failed")[:320]
        if streak >= 3:
            cooldowns[key] = cycle + 15
            st["panic_count"] = _to_int(st.get("panic_count", 0), default=0) + 1
            st["mode"] = "degraded"
    else:
        fail_streak[key] = 0
        success_count[key] = _to_int(success_count.get(key, 0), default=0) + 1
        st["last_route_error"] = ""

    if provider == "fallback-local":
        fallback_count = _to_int(st.get("consecutive_fallbacks", 0), default=0) + 1
        st["consecutive_fallbacks"] = fallback_count
        if fallback_count == 3:
            cooldowns[key] = max(_to_int(cooldowns.get(key, 0), default=0), cycle + 12)
            st["panic_count"] = _to_int(st.get("panic_count", 0), default=0) + 1
            st["mode"] = "degraded"
    else:
        st["consecutive_fallbacks"] = 0

    active_cooldowns = {
        k: _to_int(v, default=0)
        for k, v in cooldowns.items()
        if _to_int(v, default=0) > cycle
    }
    if not active_cooldowns and str(st.get("mode", "normal")) == "degraded" and not failed:
        if _to_int(st.get("consecutive_fallbacks", 0), default=0) <= 1:
            st["mode"] = "normal"

    st["route_fail_streak"] = fail_streak
    st["route_success_count"] = success_count
    st["route_cooldown_until"] = cooldowns
    st["last_route_group"] = str(actual_group or key)[:120]
    st["last_updated"] = now_iso()


def _apply_runtime_pragmas(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
    except Exception:
        pass


def _quarantine_corrupted_db(db_path: Path) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup = db_path.with_name(f"{db_path.stem}.corrupt_{ts}{db_path.suffix}")
    try:
        db_path.rename(backup)
    except Exception:
        return db_path

    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db_path) + suffix)
        if not sidecar.exists():
            continue
        try:
            sidecar.rename(Path(str(backup) + suffix))
        except Exception:
            pass
    return backup


def connect_runtime_db(db_path: str) -> sqlite3.Connection:
    db_file = Path(str(db_path))
    conn = sqlite3.connect(str(db_file), timeout=30.0)
    conn.row_factory = sqlite3.Row
    _apply_runtime_pragmas(conn)
    try:
        ensure_runtime_schema(conn)
        return conn
    except sqlite3.DatabaseError as exc:
        msg = str(exc).lower()
        try:
            conn.close()
        except Exception:
            pass
        if "malformed" not in msg:
            raise
        _quarantine_corrupted_db(db_file)
        conn = sqlite3.connect(str(db_file), timeout=30.0)
        conn.row_factory = sqlite3.Row
        _apply_runtime_pragmas(conn)
        ensure_runtime_schema(conn)
        return conn


def ensure_runtime_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            source TEXT NOT NULL,
            event_type TEXT NOT NULL,
            content TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}',
            brain_done INTEGER NOT NULL DEFAULT 0,
            worker_done INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_events_brain ON azi_events(brain_done, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_events_worker ON azi_events(worker_done, event_type, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_events_source ON azi_events(source, id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            summary TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_decisions_event ON azi_decisions(event_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_decisions_ts ON azi_decisions(ts)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            service TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_health_service ON azi_health(service, id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_protocol_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_protocol_event ON azi_protocol_flow(event_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_protocol_kind ON azi_protocol_flow(kind, id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_provider_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            provider_group TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_provider_routes_event ON azi_provider_routes(event_id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_contracts_event ON azi_contracts(event_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_contracts_kind ON azi_contracts(kind, id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_state_versions (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            version INTEGER NOT NULL DEFAULT 0,
            updated_ts TEXT NOT NULL,
            actor TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS azi_commit_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            actor TEXT NOT NULL,
            base_version INTEGER NOT NULL,
            observed_version INTEGER NOT NULL,
            status TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_commit_windows_event ON azi_commit_windows(event_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_azi_commit_windows_status ON azi_commit_windows(status, id)")

    ensure_memory_schema(conn)
    ensure_governance_schema(conn)
    ensure_deep_safety_schema(conn)
    _ensure_state_version_row(conn)
    conn.commit()


def load_runtime_state(state_path: Path) -> dict[str, Any]:
    base = copy.deepcopy(DEFAULT_RUNTIME_STATE)
    if not state_path.exists() or not state_path.is_file():
        _ensure_stability_state(base)
        _ensure_orchestration_state(base)
        _ensure_work_memory_state(base)
        return base
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception:
        _ensure_stability_state(base)
        _ensure_orchestration_state(base)
        _ensure_work_memory_state(base)
        return base
    if not isinstance(raw, dict):
        _ensure_stability_state(base)
        _ensure_orchestration_state(base)
        _ensure_work_memory_state(base)
        return base
    base.update(raw)
    _ensure_stability_state(base)
    _ensure_orchestration_state(base)
    _ensure_work_memory_state(base)
    return base


def save_runtime_state(state_path: Path, state: dict[str, Any]) -> None:
    payload = json.dumps(state, ensure_ascii=False, indent=2)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(state_path)
    except Exception:
        state_path.write_text(payload, encoding="utf-8")


def enqueue_event(
    conn: sqlite3.Connection,
    *,
    source: str,
    event_type: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO azi_events(ts, source, event_type, content, meta_json, brain_done, worker_done)
        VALUES(?, ?, ?, ?, ?, 0, 0)
        """,
        (
            now_iso(),
            str(source),
            str(event_type),
            str(content),
            json.dumps(meta or {}, ensure_ascii=False),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _fetch_pending_brain(conn: sqlite3.Connection, max_events: int) -> list[sqlite3.Row]:
    n = max(1, min(int(max_events), 200))
    return conn.execute(
        """
        SELECT id, ts, source, event_type, content, meta_json
        FROM azi_events
        WHERE brain_done=0
          AND event_type IN (
            'input',
            'iteration',
            'deep_request',
            'dream_request',
            'health',
            'web_probe',
            'file_feed',
            'vscode_observer',
            'social',
            'device_capture',
            'manual',
            'shallow'
          )
        ORDER BY id ASC
        LIMIT ?
        """,
        (n,),
    ).fetchall()


def _fetch_pending_worker(conn: sqlite3.Connection, max_events: int) -> list[sqlite3.Row]:
    n = max(1, min(int(max_events), 200))
    return conn.execute(
        """
        SELECT id, ts, source, event_type, content, meta_json
        FROM azi_events
        WHERE worker_done=0
          AND event_type IN ('iteration', 'deep_request', 'dream_request')
        ORDER BY id ASC
        LIMIT ?
        """,
        (n,),
    ).fetchall()


def _mark_brain_done(conn: sqlite3.Connection, event_id: int) -> None:
    conn.execute("UPDATE azi_events SET brain_done=1 WHERE id=?", (int(event_id),))


def _mark_worker_done(conn: sqlite3.Connection, event_id: int) -> None:
    conn.execute("UPDATE azi_events SET worker_done=1 WHERE id=?", (int(event_id),))


def _insert_decision(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    action: str,
    reason: str,
    summary: str,
    meta: dict[str, Any] | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO azi_decisions(event_id, ts, action, reason, summary, meta_json)
        VALUES(?, ?, ?, ?, ?, ?)
        """,
        (
            int(event_id),
            now_iso(),
            str(action),
            str(reason),
            str(summary),
            json.dumps(meta or {}, ensure_ascii=False),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _insert_protocol_flow(conn: sqlite3.Connection, *, event_id: int, kind: str, payload_json: str) -> int:
    cur = conn.execute(
        "INSERT INTO azi_protocol_flow(ts, event_id, kind, payload_json) VALUES(?, ?, ?, ?)",
        (now_iso(), int(event_id), str(kind), str(payload_json)),
    )
    return int(cur.lastrowid)


def _insert_provider_route(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    action: str,
    provider_group: str,
    detail: dict[str, Any],
) -> int:
    cur = conn.execute(
        "INSERT INTO azi_provider_routes(ts, event_id, action, provider_group, detail_json) VALUES(?, ?, ?, ?, ?)",
        (now_iso(), int(event_id), str(action), str(provider_group), json.dumps(detail, ensure_ascii=False)),
    )
    return int(cur.lastrowid)


def _insert_contract(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    kind: str,
    payload_json: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO azi_contracts(ts, event_id, kind, payload_json) VALUES(?, ?, ?, ?)",
        (now_iso(), int(event_id), str(kind), str(payload_json)),
    )
    return int(cur.lastrowid)


def _ensure_state_version_row(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO azi_state_versions(id, version, updated_ts, actor, note)
        VALUES(1, 0, ?, 'bootstrap', 'init')
        """,
        (now_iso(),),
    )


def _get_state_version(conn: sqlite3.Connection) -> int:
    _ensure_state_version_row(conn)
    row = conn.execute("SELECT version FROM azi_state_versions WHERE id=1").fetchone()
    return int(row["version"] or 0) if row else 0


def _advance_state_version_if_match(
    conn: sqlite3.Connection,
    *,
    expected_version: int,
    actor: str,
    note: str,
) -> tuple[bool, int]:
    _ensure_state_version_row(conn)
    cur = conn.execute(
        """
        UPDATE azi_state_versions
        SET version = version + 1, updated_ts = ?, actor = ?, note = ?
        WHERE id = 1 AND version = ?
        """,
        (now_iso(), str(actor), str(note)[:220], int(expected_version)),
    )
    row = conn.execute("SELECT version FROM azi_state_versions WHERE id=1").fetchone()
    current = int(row["version"] or 0) if row else int(expected_version)
    conn.commit()
    return cur.rowcount == 1, current


def _record_commit_window(
    conn: sqlite3.Connection,
    *,
    event_id: int,
    actor: str,
    base_version: int,
    observed_version: int,
    status: str,
    note: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO azi_commit_windows(ts, event_id, actor, base_version, observed_version, status, note)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            int(event_id),
            str(actor),
            int(base_version),
            int(observed_version),
            str(status),
            str(note)[:500],
        ),
    )
    conn.commit()


def _source_trust_score(conn: sqlite3.Connection, source: str, default: float = 0.6) -> float:
    row = conn.execute("SELECT trust_score FROM azi_source_trust WHERE source=? LIMIT 1", (str(source),)).fetchone()
    if row is None:
        return float(default)
    try:
        return float(row["trust_score"])
    except Exception:
        return float(default)


def _load_immutable_paths(base_dir: Path) -> list[str]:
    defaults = [
        str(base_dir / "run.ps1"),
        str(base_dir / "brain_loop.py"),
        str(base_dir / "azi_rebuild" / "runtime.py"),
    ]
    cfg = base_dir / "permissions.json"
    if not cfg.exists() or not cfg.is_file():
        return defaults
    try:
        obj = json.loads(cfg.read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception:
        return defaults
    if not isinstance(obj, dict):
        return defaults
    extra = [str(x) for x in list(obj.get("immutable_paths", []) or []) if str(x).strip()]
    return defaults + extra


def _state_to_10d(state: dict[str, Any]) -> State10D:
    energy = float(state.get("energy", 0.8))
    stress = float(state.get("stress", 0.2))
    uncertainty = float(state.get("uncertainty", 0.3))
    integrity = float(state.get("integrity", 0.85))
    continuity = float(state.get("continuity", 0.7))

    if stress >= 0.7:
        change = ChangeType.TRANSFORM
    elif uncertainty >= 0.6:
        change = ChangeType.ROOT
    else:
        change = ChangeType.SYMPTOM

    if continuity >= 0.75:
        phase = CyclePhase.ASCENDING
    elif continuity >= 0.55:
        phase = CyclePhase.PEAK
    elif continuity >= 0.35:
        phase = CyclePhase.DESCENDING
    else:
        phase = CyclePhase.TROUGH

    role = str(state.get("role_id", "operator"))
    kappa = {
        WuxingChannel.WOOD: 1.0,
        WuxingChannel.FIRE: 1.0 + 0.2 * stress,
        WuxingChannel.EARTH: 1.0,
        WuxingChannel.METAL: 1.0 + 0.2 * uncertainty,
        WuxingChannel.WATER: 1.0 - 0.2 * continuity,
    }

    return State10D(
        d1_quantity=max(0.0, energy * 2.0),
        d4_change=change,
        d4_approaching_threshold=stress >= 0.75,
        d5_recovery_rate=clamp(integrity, 0.0, 1.0),
        d5_long_term_cost=max(0.0, 1.0 + stress * 2.0),
        d5_cycle_phase=phase,
        d5_depletion_risk=clamp(stress, 0.0, 1.0),
        d6_kappa=kappa,
        d7_role_id=role,
        d7_irreversible_commitments=[],
        d7_exit_cost=clamp(1.0 - continuity, 0.0, 1.0),
        d8_active=False,
        d8_return_path="fallback_to_7d",
        d10_halt_conditions=["no_new_actionability"] if uncertainty >= 0.95 else [],
    )


def _compose_dream_replay(conn: sqlite3.Connection, seed: str, limit: int = 10) -> str:
    n = max(3, min(int(limit), 20))
    rows = conn.execute(
        """
        SELECT source, event_type, content
        FROM azi_events
        WHERE event_type IN (
            'input', 'iteration', 'deep_request', 'dream_request',
            'web_probe', 'file_feed', 'vscode_observer', 'social', 'device_capture'
        )
        ORDER BY id DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()

    if not rows:
        return "Dream replay: input flow is quiet; keep stable rhythm and wait for higher-value signals."

    source_count: dict[str, int] = {}
    merged: list[str] = []
    for row in reversed(rows):
        source = str(row["source"] or "unknown")
        source_count[source] = int(source_count.get(source, 0)) + 1
        event_type = str(row["event_type"] or "-")
        content = str(row["content"] or "").replace("\n", " ").strip()
        merged.append(f"{source}/{event_type}:{content[:36]}")

    focus_source = max(source_count.items(), key=lambda x: x[1])[0]
    weave = " | ".join(merged[-5:])
    seed_text = str(seed or "").replace("\n", " ").strip()[:80]
    seed_part = f", trigger={seed_text}" if seed_text else ""
    return f"Dream replay focus `{focus_source}`{seed_part}. Reordered fragments: {weave}"


def _choose_action(
    result: dict[str, Any],
    event_type: str,
    force_deep: bool,
    *,
    meta: dict[str, Any] | None = None,
) -> str:
    halt = bool(dict(result.get("halt_check", {}) or {}).get("triggered", False))
    mode = str(dict(meta or {}).get("mode", "")).strip().lower()
    if halt:
        return "halt_and_fallback"
    if event_type == "dream_request" or mode == "dream":
        return "escalate_dream"
    if force_deep or event_type in {"iteration", "deep_request"}:
        return "escalate_deep"
    if event_type in {"health"}:
        return "stabilize"
    return "plan_next"


def _to_risk_level(risk_level: str, forbidden: bool) -> str:
    if forbidden:
        return "L3"
    raw = str(risk_level or "").strip().lower()
    if raw == "high":
        return "L2"
    if raw == "mid":
        return "L1"
    return "L0"


def _digest_text(text: str) -> str:
    return hashlib.sha1(str(text or "").encode("utf-8", errors="ignore")).hexdigest()[:16]


def _normalize_dispatch_task_type(task_type: str) -> str:
    raw = str(task_type or "").strip().lower()
    mapping = {
        "shallow_reaction": "shallow",
        "analysis": "shallow",
        "deep_reflection": "deep",
        "dream": "dream",
        "coding": "coding",
        "risk_control": "ops",
    }
    return mapping.get(raw, "shallow")


def _detect_actionable_issue(
    *,
    content: str,
    event_type: str,
    meta: dict[str, Any],
    action: str,
) -> dict[str, Any]:
    text = str(content or "").strip().lower()
    evt = str(event_type or "").strip().lower()
    act = str(action or "").strip().lower()
    if evt in {"iteration", "deep_request", "dream_request"}:
        return {"issue_detected": True, "issue_reason": f"event_type={evt}", "confidence": 0.92}
    if act in {"escalate_deep", "escalate_dream", "await_approval"}:
        return {"issue_detected": True, "issue_reason": f"action={act}", "confidence": 0.88}
    if not text:
        return {"issue_detected": False, "issue_reason": "empty_input", "confidence": 0.28}

    nonwork_tokens = {
        "你好",
        "hi",
        "hello",
        "谢谢",
        "ok",
        "好的",
        "收到",
        "在吗",
    }
    if len(text) <= 24 and any(tok in text for tok in nonwork_tokens):
        return {"issue_detected": False, "issue_reason": "smalltalk", "confidence": 0.33}

    work_tokens = {
        "修复",
        "重构",
        "实现",
        "排查",
        "分析",
        "优化",
        "部署",
        "编写",
        "生成",
        "写一个",
        "计划",
        "执行",
        "debug",
        "bug",
        "error",
        "traceback",
        "fix",
        "refactor",
        "implement",
        "build",
        "todo",
    }
    score = 0.0
    if any(tok in text for tok in work_tokens):
        score += 0.55
    if ("?" in text) or ("？" in text):
        score += 0.16
    if bool(meta.get("trigger_update", False)) or bool(meta.get("run_once", False)):
        score += 0.12
    if len(text) >= 40:
        score += 0.08

    issue = score >= 0.45
    reason = "explicit_work_signal" if issue else "insufficient_action_signal"
    confidence = clamp(0.32 + score, 0.0, 0.96)
    return {"issue_detected": issue, "issue_reason": reason, "confidence": confidence}


def _dispatch_worker(*, task_type: str, content: str, event_type: str, meta: dict[str, Any]) -> str:
    text = str(content or "").lower()
    evt = str(event_type or "").lower()
    if bool(meta.get("connector_id")) and "mcp" in str(meta.get("connector_id", "")).lower():
        return "mcp"
    if "mcp" in text or evt.startswith("mcp"):
        return "mcp"
    if "api" in text or evt == "api_bridge":
        return "api"
    if task_type == "coding":
        return "coder"
    if task_type in {"deep", "dream"}:
        return "deep"
    return "shallow"


def _dispatch_model_group(*, task_type: str, route_group: str) -> str:
    rg = str(route_group or "").strip()
    if rg:
        return rg
    if task_type == "coding":
        return "coder_chain"
    if task_type in {"deep", "dream"}:
        return "deep_chain"
    return "shallow_chain"


def _dispatch_tool(*, worker: str, task_type: str) -> str:
    if worker == "coder":
        return "deep_coder_worker.run_once"
    if worker == "deep" and task_type == "dream":
        return "deep_worker.dream_replay_once"
    if worker == "deep":
        return "deep_worker.run_once"
    if worker == "mcp":
        return "panel_connector.call_mcp_tool"
    if worker == "api":
        return "panel_connector.call_api_connector"
    return "brain_loop.run_once"


def _dispatch_timeout(*, worker: str, task_type: str) -> int:
    if worker == "coder":
        return 240
    if worker == "deep" and task_type == "dream":
        return 120
    if worker == "deep":
        return 180
    if worker in {"mcp", "api"}:
        return 90
    return 45


def _build_hub_dispatch_prompt(
    *,
    goal: str,
    event_summary: str,
    state: dict[str, Any],
    risk_level: str,
    route_group: str,
    requires_approval: bool,
) -> str:
    workers = "shallow, deep, coder, mcp, api"
    tools = (
        "brain_loop.run_once, deep_worker.run_once, deep_worker.dream_replay_once, "
        "deep_coder_worker.run_once, panel_connector.call_mcp_tool, panel_connector.call_api_connector"
    )
    constraints = [
        "中枢只做调度，不直接执行",
        "输出必须是可执行任务单（1-3条）",
        f"当前风险={risk_level}",
        f"当前路由组={route_group or '-'}",
        f"requires_approval={bool(requires_approval)}",
        "默认优先可回滚动作",
    ]
    state_brief = (
        f"cycle={int(state.get('cycle', 0))}, energy={float(state.get('energy', 0.0)):.2f}, "
        f"stress={float(state.get('stress', 0.0)):.2f}, continuity={float(state.get('continuity', 0.0)):.2f}"
    )
    return (
        "你是阿紫调度中枢，不直接执行，只产出可执行任务单。\n"
        f"目标：{str(goal)[:220]}\n"
        f"输入事件流：{str(event_summary)[:420]}\n"
        f"状态：{state_brief}\n"
        f"可用执行单元：{workers}\n"
        f"可用工具：{tools}\n"
        "约束：" + "；".join(constraints)
    )


def _task_skill_pack(*, task_type: str, llm_cfg: dict[str, Any] | None = None) -> list[str]:
    cfg = dict(llm_cfg or {})
    policy = dict(cfg.get("routing_policy", {}) or {})
    packs = dict(policy.get("task_skill_packs", {}) or {})
    raw = packs.get(str(task_type), packs.get("*", []))
    if isinstance(raw, str):
        items = [x.strip().lower() for x in raw.split(",") if x.strip()]
    elif isinstance(raw, list):
        items = [str(x).strip().lower() for x in raw if str(x).strip()]
    else:
        items = []
    if not items and str(task_type) == "dream":
        items = [
            "algorithmic-art",
            "generative-art",
            "canvas-design",
            "theme-factory",
            "artifacts-builder",
            "web-artifacts-builder",
            "slack-gif-creator",
            "imagegen",
            "sora",
            "speech",
            "transcribe",
        ]
    out: list[str] = []
    seen: set[str] = set()
    for x in items:
        key = str(x).strip().lower()
        if not key or key in seen:
            continue
        out.append(key)
        seen.add(key)
    return out[:16]


def _build_dispatch_contract(
    *,
    event_id: int,
    state: dict[str, Any],
    content: str,
    event_type: str,
    meta: dict[str, Any],
    action: str,
    task_type: str,
    route_group: str,
    route_payload: dict[str, Any],
    result: dict[str, Any],
    risk: dict[str, Any],
    requires_approval: bool,
    approved: bool,
    llm_cfg: dict[str, Any] | None = None,
) -> DispatchPlan:
    dispatch_task_type = _normalize_dispatch_task_type(task_type)
    risk_level = _to_risk_level(str(risk.get("risk_level", "mid")), False)
    issue = _detect_actionable_issue(content=content, event_type=event_type, meta=meta, action=action)
    issue_detected = bool(issue.get("issue_detected", False))
    issue_reason = str(issue.get("issue_reason", "unknown"))[:160]
    issue_conf = float(issue.get("confidence", 0.5) or 0.5)

    worker = _dispatch_worker(task_type=dispatch_task_type, content=content, event_type=event_type, meta=meta)
    model_group = _dispatch_model_group(task_type=dispatch_task_type, route_group=route_group)
    tool = _dispatch_tool(worker=worker, task_type=dispatch_task_type)
    timeout_sec = _dispatch_timeout(worker=worker, task_type=dispatch_task_type)
    reversible = risk_level in {"L0", "L1"}

    dispatch_items: list[DispatchItem] = []
    primary_expected = str(route_payload.get("summary", "") or result.get("diagnosis", "") or "actionable output")[:180]
    primary_item = DispatchItem(
        worker=worker,  # type: ignore[arg-type]
        model_group=model_group,
        tool=tool,
        input=str(content)[:360],
        expected_output=primary_expected,
        timeout_sec=timeout_sec,
        reversible=reversible,
    )
    dispatch_items.append(primary_item)

    if issue_detected:
        if action == "escalate_deep":
            dispatch_items.append(
                DispatchItem(
                    worker="deep",
                    model_group="deep_chain",
                    tool="deep_worker.run_once",
                    input=f"deep request for event#{event_id}: {str(content)[:220]}",
                    expected_output="evidence + proposal + deep_release",
                    timeout_sec=180,
                    reversible=True,
                )
            )
        elif action == "escalate_dream":
            dispatch_items.append(
                DispatchItem(
                    worker="deep",
                    model_group="deep_chain",
                    tool="deep_worker.dream_replay_once",
                    input=f"dream replay for event#{event_id}: {str(content)[:220]}",
                    expected_output="dream insight + dream_release",
                    timeout_sec=120,
                    reversible=True,
                )
            )
        if dispatch_task_type == "coding" and worker != "coder":
            dispatch_items.append(
                DispatchItem(
                    worker="coder",
                    model_group="coder_chain",
                    tool="deep_coder_worker.run_once",
                    input=str(content)[:260],
                    expected_output="patch proposal + test hints",
                    timeout_sec=240,
                    reversible=True,
                )
            )

    dispatch_items = dispatch_items[:3]
    if requires_approval and not approved:
        for item in dispatch_items:
            item.expected_output = f"[待审批] {str(item.expected_output)[:150]}"

    recommended_skills = _task_skill_pack(task_type=dispatch_task_type, llm_cfg=llm_cfg)

    success_criteria = [
        "至少生成 1 条可执行任务单",
        "执行单包含 worker/model_group/tool/timeout/reversible",
        "输出可用于下一轮调度",
    ]
    if issue_detected:
        success_criteria.append("任务单覆盖当前事件的核心意图")
    else:
        success_criteria.append("识别为非执行型输入并保持系统稳定")
    if requires_approval:
        success_criteria.append("高风险任务进入审批流程")

    rollback_plan = "fallback_to_previous_state + reopen_at_7d"
    if risk_level in {"L2", "L3"} or requires_approval:
        rollback_plan = "block_external_side_effects + fallback_to_previous_state + require_human_review"

    confidence = clamp(issue_conf + (0.08 if bool(route_payload.get("live_api", False)) else 0.0), 0.05, 0.98)
    if not issue_detected:
        confidence = min(confidence, 0.58)

    event_summary = (
        f"event_type={event_type}; action={action}; diagnosis={str(result.get('diagnosis', '-'))[:200]}; "
        f"route={route_group}; next={str(route_payload.get('next_step', '-'))[:140]}"
    )
    hub_prompt = _build_hub_dispatch_prompt(
        goal=str(content)[:220],
        event_summary=event_summary,
        state=state,
        risk_level=risk_level,
        route_group=route_group,
        requires_approval=requires_approval,
    )

    intent = str(result.get("diagnosis", "")).strip() or str(content)[:180]
    return DispatchPlan(
        id=make_contract_id("dispatch", event_id),
        source="brain-loop",
        intent=intent[:220],
        task_type=dispatch_task_type,  # type: ignore[arg-type]
        risk_level=risk_level,  # type: ignore[arg-type]
        dispatch_plan=dispatch_items,
        recommended_skills=recommended_skills,
        success_criteria=success_criteria[:6],
        rollback_plan=rollback_plan[:280],
        confidence=round(float(confidence), 4),
        issue_detected=issue_detected,
        issue_reason=issue_reason,
        hub_prompt=hub_prompt[:1200],
    )


def _update_runtime_state(state: dict[str, Any], event_id: int, action: str, result: dict[str, Any]) -> None:
    st = _ensure_stability_state(state)
    old_energy = float(state.get("energy", 0.8))
    old_stress = float(state.get("stress", 0.2))
    old_uncertainty = float(state.get("uncertainty", 0.3))
    old_integrity = float(state.get("integrity", 0.85))
    old_continuity = float(state.get("continuity", 0.7))

    halt = bool(dict(result.get("halt_check", {}) or {}).get("triggered", False))
    actionable = list(result.get("actionable_advice", []) or [])

    energy_delta = -0.03
    stress_delta = 0.02
    continuity_delta = 0.01
    uncertainty_delta = -0.01
    integrity_delta = 0.005

    if action == "escalate_deep":
        energy_delta -= 0.03
        stress_delta += 0.03
    elif action == "escalate_dream":
        energy_delta -= 0.015
        stress_delta -= 0.01
        continuity_delta += 0.015
        uncertainty_delta -= 0.015
    elif action == "halt_and_fallback":
        stress_delta -= 0.05
        continuity_delta -= 0.02
        uncertainty_delta += 0.04
    elif action == "stabilize":
        stress_delta -= 0.04
        continuity_delta += 0.02
        uncertainty_delta -= 0.02

    if str(st.get("mode", "normal")) == "degraded":
        stress_delta += 0.01
        continuity_delta -= 0.005
        uncertainty_delta += 0.01

    if actionable:
        uncertainty_delta -= 0.02
        continuity_delta += 0.01

    if halt:
        uncertainty_delta += 0.06
        integrity_delta -= 0.01

    state["cycle"] = int(state.get("cycle", 0)) + 1
    state["energy"] = clamp(old_energy + energy_delta, 0.0, 1.0)
    state["stress"] = clamp(old_stress + stress_delta, 0.0, 1.0)
    state["uncertainty"] = clamp(old_uncertainty + uncertainty_delta, 0.0, 1.0)
    state["integrity"] = clamp(old_integrity + integrity_delta, 0.0, 1.0)
    state["continuity"] = clamp(old_continuity + continuity_delta, 0.0, 1.0)
    state["last_event_id"] = int(event_id)
    state["last_action"] = action
    state["last_reason"] = str(result.get("diagnosis", "-"))[:220]
    st["last_updated"] = now_iso()


def run_single_brain_cycle(
    conn: sqlite3.Connection,
    state: dict[str, Any],
    *,
    max_events: int = 12,
    force_deep: bool = False,
    base_dir: Path | None = None,
) -> int:
    root = base_dir or Path.cwd()
    llm_cfg = load_llm_config(root / "llm_config.json")
    immutable_paths = _load_immutable_paths(root)
    _ensure_stability_state(state)
    _ensure_orchestration_state(state)
    _ensure_work_memory_state(state)

    effective_max_events = _compute_brain_event_budget(state, requested_max=int(max_events))
    rows = _fetch_pending_brain(conn, max_events=effective_max_events)
    if not rows:
        return 0

    handled = 0
    for row in rows:
        event_id = int(row["id"])
        source = str(row["source"] or "")
        event_type = str(row["event_type"])
        content = str(row["content"] or "")
        base_version = _get_state_version(conn)
        meta_raw = str(row["meta_json"] or "{}")
        try:
            meta = json.loads(meta_raw)
        except Exception:
            meta = {}

        memory_stats = ingest_event_memory(
            conn,
            event_id=event_id,
            source=source,
            content=content,
            meta=meta,
        )
        retrieved = hybrid_retrieve(conn, query=content, top_k=8)
        state_10d = _state_to_10d(state)
        result = diagnose(content, state=state_10d)
        action = _choose_action(
            result,
            event_type=event_type,
            force_deep=force_deep,
            meta=meta,
        )
        trust_score = _source_trust_score(conn, source, default=0.6)
        risk = assess_risk(
            event_id=event_id,
            action=action,
            content=content,
            source=source,
            source_trust=trust_score,
        )
        immutable = check_immutable_guard(content, immutable_paths=immutable_paths)
        if immutable.get("blocked", False):
            action = "halt_and_fallback"
            record_guard_event(
                conn,
                guard_type="immutable",
                severity="high",
                detail=f"event#{event_id} blocked paths={immutable.get('hits', [])}",
            )

        requires_approval = bool(risk.get("requires_approval", False))
        approved = (not requires_approval) or load_approval_override(root, event_id)
        if requires_approval and not approved:
            action = "await_approval"

        route_ctx = {
            "event_type": event_type,
            "prompt": content,
            "objective": str(result.get("diagnosis", "")),
        }
        task_type_hint = infer_task_type(
            action=action,
            risk_level=str(risk.get("risk_level", "mid")),
            event_type=event_type,
            prompt=content,
            objective=str(result.get("diagnosis", "")),
        )
        llm_cfg_route, memory_pref_groups = _memory_biased_llm_config(
            state=state,
            llm_cfg=llm_cfg,
            task_type=task_type_hint,
        )
        route_meta = choose_provider_group_with_meta(
            action=action,
            risk_level=str(risk.get("risk_level", "mid")),
            llm_config=llm_cfg_route,
            route_context=route_ctx,
            orchestration=dict(state.get("orchestration", {}) or {}),
        )
        route_group_requested = str(route_meta.get("group", "fallback-local"))
        task_type = str(route_meta.get("task_type", "analysis"))
        route_reason = str(route_meta.get("reason", "task_policy"))
        route_group, route_override_reason = _apply_route_cooldown_override(
            state,
            llm_cfg_route,
            route_group_requested,
        )
        route_payload = generate_structured_response(
            group=route_group,
            prompt=content,
            objective=str(result.get("diagnosis", "")),
            llm_config=llm_cfg_route,
            task_type=task_type,
        )
        if route_override_reason:
            route_payload["stability_override"] = route_override_reason
        route_payload["task_type"] = task_type
        route_payload["route_reason"] = route_reason
        route_payload["route_candidates"] = list(route_meta.get("candidates", []) or [])
        route_payload["route_scores"] = dict(route_meta.get("scores", {}) or {})
        if memory_pref_groups:
            route_payload["memory_bias"] = {
                "task_type": task_type_hint,
                "preferred_groups": memory_pref_groups[:6],
                "strength": _work_memory_policy_from_llm_cfg(llm_cfg_route).get("strength", "balanced"),
            }
        _observe_route_outcome(
            state,
            requested_group=route_group_requested,
            actual_group=route_group,
            route_payload=route_payload,
            llm_cfg=llm_cfg_route,
        )
        route_payload["requested_group"] = route_group_requested
        route_payload["effective_group"] = route_group
        _update_orchestration_metrics(
            state,
            task_type=task_type,
            route_group=route_group,
            route_reason=(route_override_reason or route_reason),
            route_payload=route_payload,
        )
        _update_work_memory(
            state,
            task_type=task_type,
            requested_group=route_group_requested,
            actual_group=route_group,
            route_payload=route_payload,
            llm_cfg=llm_cfg_route,
        )
        _insert_provider_route(
            conn,
            event_id=event_id,
            action=action,
            provider_group=route_group,
            detail=route_payload,
        )

        plan_contract = Plan(
            id=make_contract_id("plan", event_id),
            source="brain-loop",
            goal=str(content)[:260] or f"event#{event_id}",
            steps=[
                PlanStep(
                    step_id=f"{event_id}-1",
                    action="analyze_event",
                    tool="diagnose+memory",
                    expected_output="diagnosis+risk",
                ),
                PlanStep(
                    step_id=f"{event_id}-2",
                    action=str(action),
                    tool=f"provider_group:{route_group}",
                    expected_output=str(route_payload.get("summary", "-"))[:180],
                ),
            ],
            assumptions=[
                "prefer_reversible_changes",
                "risk_checked_before_execution",
            ],
            rollback_plan="fallback_to_previous_state + reopen_at_7d",
        )
        kind, payload = contract_to_row("plan", plan_contract)
        _insert_contract(conn, event_id=event_id, kind=kind, payload_json=payload)

        risk_contract = RiskReport(
            id=make_contract_id("risk", event_id),
            source="gatekeeper",
            risk_level=_to_risk_level(str(risk.get("risk_level", "mid")), bool(immutable.get("blocked", False))),
            reasons=list(risk.get("reasons", []) or []),
            required_permission="approval" if requires_approval else "none",
            requires_approval=requires_approval,
            forbidden=bool(immutable.get("blocked", False)),
        )
        kind, payload = contract_to_row("risk_report", risk_contract)
        _insert_contract(conn, event_id=event_id, kind=kind, payload_json=payload)

        if requires_approval:
            approval_contract = Approval(
                id=make_contract_id("approval", event_id),
                source="risk-gate",
                decision="approve" if approved else "reject",
                approver=("override" if approved else "policy"),
                reason=("override_approved" if approved else "approval_required"),
                scope=[str(action)],
            )
            kind, payload = contract_to_row("approval", approval_contract)
            _insert_contract(conn, event_id=event_id, kind=kind, payload_json=payload)

        dispatch_contract = _build_dispatch_contract(
            event_id=event_id,
            state=state,
            content=content,
            event_type=event_type,
            meta=meta if isinstance(meta, dict) else {},
            action=action,
            task_type=task_type,
            route_group=route_group,
            route_payload=route_payload if isinstance(route_payload, dict) else {},
            result=result if isinstance(result, dict) else {},
            risk=risk if isinstance(risk, dict) else {},
            requires_approval=requires_approval,
            approved=approved,
            llm_cfg=llm_cfg_route if isinstance(llm_cfg_route, dict) else llm_cfg,
        )
        kind, payload = contract_to_row("dispatch_plan", dispatch_contract)
        _insert_contract(conn, event_id=event_id, kind=kind, payload_json=payload)

        tool_started = now_iso()
        tool_ended = now_iso()
        trace_status = "success"
        if action in {"await_approval", "halt_and_fallback"}:
            trace_status = "blocked"
        exec_trace = ExecTrace(
            id=make_contract_id("trace", event_id),
            trace_id=make_contract_id("trace-ref", event_id),
            source="brain-loop",
            plan_id=plan_contract.id,
            risk_report_id=risk_contract.id,
            tool_calls=[
                ToolCallTrace(
                    tool=f"provider_group:{route_group}",
                    args_hash=_digest_text(f"{event_id}|{action}|{route_group}|{content[:120]}"),
                    started_ts=tool_started,
                    ended_ts=tool_ended,
                    result_digest=_digest_text(str(route_payload.get("summary", ""))),
                )
            ],
            artifacts=[f"action:{action}", f"provider_group:{route_group}"],
            status=trace_status,  # type: ignore[arg-type]
        )
        kind, payload = contract_to_row("exec_trace", exec_trace)
        _insert_contract(conn, event_id=event_id, kind=kind, payload_json=payload)

        task_priority = "high" if str(risk.get("risk_level")) == "high" else "mid"
        task = make_task(event_id=event_id, content=content, source=source, priority=task_priority)
        evidence_pack = make_evidence_pack(
            source_task_id=task.task_id,
            facts=list(retrieved.get("facts", []) or []),
            vectors=list(retrieved.get("vectors", []) or []),
            observation=content,
            event_id=event_id,
        )
        proposal = make_proposal(
            source_task_id=task.task_id,
            action=action,
            rationale=f"{route_payload.get('next_step', '-')}; diagnosis={result.get('diagnosis', '-')}",
            risk_level=str(risk.get("risk_level", "mid")),
            requires_approval=requires_approval,
            rollback_plan="fallback_to_previous_state + reopen_at_7d",
        )

        kind, payload = protocol_to_row("task", task)
        _insert_protocol_flow(conn, event_id=event_id, kind=kind, payload_json=payload)
        kind, payload = protocol_to_row("evidence", evidence_pack)
        _insert_protocol_flow(conn, event_id=event_id, kind=kind, payload_json=payload)
        kind, payload = protocol_to_row("proposal", proposal)
        _insert_protocol_flow(conn, event_id=event_id, kind=kind, payload_json=payload)

        summary = ""
        actionables = list(result.get("actionable_advice", []) or [])
        if actionables:
            summary = str(actionables[0])[:240]
        else:
            summary = str(result.get("diagnosis", "-"))[:240]
        if action == "await_approval":
            summary = "high-risk action pending approval"

        _insert_decision(
            conn,
            event_id=event_id,
            action=action,
            reason=str(result.get("diagnosis", "-"))[:240],
            summary=summary,
            meta={
                "result": result,
                "event_meta": meta,
                "memory_stats": memory_stats,
                "retrieve": retrieved,
                "risk": risk,
                "route": route_payload,
                "dispatch": dispatch_contract.model_dump(mode="json"),
            },
        )
        record_risk_gate(
            conn,
            event_id=event_id,
            action=action,
            risk_level=str(risk.get("risk_level", "mid")),
            requires_approval=requires_approval,
            approved=approved,
            reasons=list(risk.get("reasons", []) or []),
        )

        if action == "escalate_deep" and approved and event_type != "deep_request":
            enqueue_event(
                conn,
                source="brain-loop",
                event_type="deep_request",
                content=f"deep request from event {event_id}: {content[:200]}",
                meta={"parent_event_id": event_id},
            )
        if action == "escalate_dream" and approved and event_type != "dream_request":
            enqueue_event(
                conn,
                source="brain-loop",
                event_type="dream_request",
                content=f"dream request from event {event_id}: {content[:200]}",
                meta={"parent_event_id": event_id},
            )
        if action == "await_approval":
            enqueue_event(
                conn,
                source="risk-gate",
                event_type="risk",
                content=f"approval required for event {event_id}: {content[:180]}",
                meta={"parent_event_id": event_id, "risk": risk},
            )

        observed_version = _get_state_version(conn)
        committed, new_version = _advance_state_version_if_match(
            conn,
            expected_version=base_version,
            actor="brain-loop",
            note=f"event#{event_id}:{action}",
        )
        commit_status = "committed"
        if not committed:
            commit_status = "rebase_committed"
            rebase_ok, new_version = _advance_state_version_if_match(
                conn,
                expected_version=observed_version,
                actor="brain-loop",
                note=f"event#{event_id}:{action}:rebase",
            )
            if not rebase_ok:
                commit_status = "drift_unresolved"
                new_version = _get_state_version(conn)
        _record_commit_window(
            conn,
            event_id=event_id,
            actor="brain-loop",
            base_version=base_version,
            observed_version=observed_version,
            status=commit_status,
            note=f"action={action}",
        )

        state["mvcc_version"] = int(new_version)
        _update_runtime_state(state, event_id=event_id, action=action, result=result)
        _mark_brain_done(conn, event_id)
        emergence = emergence_guard(conn)
        if bool(emergence.get("alert", False)):
            enqueue_event(
                conn,
                source="emergence-guard",
                event_type="guard",
                content=str(emergence.get("reason", "emergence_alert")),
                meta={"event_id": event_id},
            )
        handled += 1

    conn.commit()
    if int(state.get("cycle", 0)) % 40 == 0:
        runtime_gc(conn)
    return handled


def run_single_worker_cycle(
    conn: sqlite3.Connection,
    state: dict[str, Any],
    *,
    max_events: int = 6,
    base_dir: Path | None = None,
) -> int:
    root = base_dir or Path.cwd()
    llm_cfg = load_llm_config(root / "llm_config.json")
    _ensure_stability_state(state)
    _ensure_orchestration_state(state)
    _ensure_work_memory_state(state)
    effective_max_events = _compute_worker_event_budget(state, requested_max=int(max_events))
    rows = _fetch_pending_worker(conn, max_events=effective_max_events)
    if not rows:
        return 0

    handled = 0
    for row in rows:
        event_id = int(row["id"])
        content = str(row["content"] or "")
        source = str(row["source"] or "")
        event_type = str(row["event_type"] or "")
        base_version = _get_state_version(conn)

        if event_type == "dream_request":
            draft = _compose_dream_replay(conn, seed=content, limit=12)
            task_type = infer_task_type(
                action="escalate_dream",
                risk_level="mid",
                event_type=event_type,
                prompt=draft,
                objective="dream replay",
            )
            llm_cfg_route, memory_pref_groups = _memory_biased_llm_config(
                state=state,
                llm_cfg=llm_cfg,
                task_type=task_type,
            )
            route_meta = choose_provider_group_with_meta(
                action="escalate_dream",
                risk_level="mid",
                llm_config=llm_cfg_route,
                route_context={
                    "event_type": event_type,
                    "prompt": draft,
                    "objective": "Turn dream replay fragments into one concise actionable insight.",
                },
                orchestration=dict(state.get("orchestration", {}) or {}),
            )
            route_group_requested = str(route_meta.get("group", "deep_chain"))
            route_group, route_override_reason = _apply_route_cooldown_override(
                state,
                llm_cfg_route,
                route_group_requested,
            )
            dream_route = generate_structured_response(
                group=route_group,
                prompt=draft,
                objective="Turn dream replay fragments into one concise actionable insight.",
                llm_config=llm_cfg_route,
                task_type=task_type,
            )
            dream_route["task_type"] = task_type
            dream_route["route_reason"] = str(route_meta.get("reason", "task_policy"))[:220]
            dream_route["route_candidates"] = list(route_meta.get("candidates", []) or [])
            dream_route["route_scores"] = dict(route_meta.get("scores", {}) or {})
            if memory_pref_groups:
                dream_route["memory_bias"] = {
                    "task_type": task_type,
                    "preferred_groups": memory_pref_groups[:6],
                    "strength": _work_memory_policy_from_llm_cfg(llm_cfg_route).get("strength", "balanced"),
                }
            dream_route["requested_group"] = route_group_requested
            dream_route["effective_group"] = route_group
            if route_override_reason:
                dream_route["stability_override"] = route_override_reason
            _observe_route_outcome(
                state,
                requested_group=route_group_requested,
                actual_group=route_group,
                route_payload=dream_route if isinstance(dream_route, dict) else {},
                llm_cfg=llm_cfg_route,
            )
            _update_orchestration_metrics(
                state,
                task_type=task_type,
                route_group=route_group,
                route_reason=(route_override_reason or str(route_meta.get("reason", "task_policy"))),
                route_payload=dream_route if isinstance(dream_route, dict) else {},
            )
            _update_work_memory(
                state,
                task_type=task_type,
                requested_group=route_group_requested,
                actual_group=route_group,
                route_payload=dream_route if isinstance(dream_route, dict) else {},
                llm_cfg=llm_cfg_route,
            )
            dream_text = str(dream_route.get("summary", "")).strip() or draft
            enqueue_event(
                conn,
                source="deep-worker",
                event_type="dream",
                content=dream_text,
                meta={
                    "parent_event_id": event_id,
                    "seed": content[:200],
                    "provider": str(dream_route.get("provider", "-")),
                    "model": str(dream_route.get("model", "-")),
                    "live_api": bool(dream_route.get("live_api", False)),
                },
            )
            enqueue_event(
                conn,
                source="deep-worker",
                event_type="dream_release",
                content=f"dream replay published for event#{event_id}",
                meta={"parent_event_id": event_id, "mode": "dream"},
            )
            _record_commit_window(
                conn,
                event_id=event_id,
                actor="deep-worker",
                base_version=base_version,
                observed_version=base_version,
                status="dream_no_commit",
                note="memory replay only",
            )
            _insert_decision(
                conn,
                event_id=event_id,
                action="dream_reflect",
                reason="worker dream replay generated",
                summary=dream_text[:220],
                meta={
                    "worker": "dream",
                    "parent_event_id": event_id,
                    "mode": "dream",
                },
            )
            eval_contract = EvalResult(
                id=make_contract_id("eval", event_id),
                source="deep-worker",
                suite="dream_replay",
                score=0.78 if bool(dream_route.get("live_api", False)) else 0.64,
                pass_flag=True,
                regression=False,
                findings=[
                    f"provider={str(dream_route.get('provider', '-'))}",
                    f"model={str(dream_route.get('model', '-'))}",
                ],
            )
            kind, payload = contract_to_row("eval_result", eval_contract)
            _insert_contract(conn, event_id=event_id, kind=kind, payload_json=payload)

            rep_before = float(state.get("reward_rep_dream_worker", 50.0))
            delta = 0.35 if bool(dream_route.get("live_api", False)) else 0.1
            rep_after = rep_before + delta
            state["reward_rep_dream_worker"] = rep_after
            reward_contract = RewardUpdate(
                id=make_contract_id("reward", event_id),
                source="reward-engine",
                actor_id="dream-worker",
                rep_before=rep_before,
                rep_after=rep_after,
                delta=delta,
                reason_codes=["dream_reflect", "api_live" if bool(dream_route.get("live_api", False)) else "fallback"],
            )
            kind, payload = contract_to_row("reward_update", reward_contract)
            _insert_contract(conn, event_id=event_id, kind=kind, payload_json=payload)

            _mark_worker_done(conn, event_id)
            handled += 1
            continue

        patch_plan = (
            f"apply reversible refinement for event#{event_id}; "
            f"source={source}; type={event_type}; objective={content[:120]}"
        )
        chain = run_deep_safety_chain(
            base_dir=root,
            conn=conn,
            event_id=event_id,
            patch_plan=patch_plan,
            run_eval=True,
        )
        eval_gate = dict(chain.get("eval_gate", {}) or {})
        chain_ok = bool(chain.get("ok", False))
        gate_pass = chain_ok and bool(eval_gate.get("publish_allowed", False))

        observed_version = _get_state_version(conn)
        commit_status = "blocked_eval_gate"
        publish_allowed = False
        publish_reason = str(eval_gate.get("status", "failed"))

        if gate_pass:
            if observed_version != base_version:
                commit_status = "drift_rebase_required"
                publish_reason = f"mvcc drift: base={base_version}, observed={observed_version}"
                rb = rollback_stage(base_dir=root, event_id=event_id, reason=publish_reason)
                chain["mvcc_rollback"] = rb
            else:
                committed, new_version = _advance_state_version_if_match(
                    conn,
                    expected_version=base_version,
                    actor="deep-worker",
                    note=f"event#{event_id}:deep_publish",
                )
                if committed:
                    commit_status = "committed"
                    publish_allowed = True
                    publish_reason = f"published@v{new_version}"
                    state["mvcc_version"] = int(new_version)
                else:
                    commit_status = "drift_commit_race"
                    publish_reason = "mvcc commit race"
                    rb = rollback_stage(base_dir=root, event_id=event_id, reason=publish_reason)
                    chain["mvcc_rollback"] = rb

        _record_commit_window(
            conn,
            event_id=event_id,
            actor="deep-worker",
            base_version=base_version,
            observed_version=observed_version,
            status=commit_status,
            note=publish_reason,
        )

        proposal = f"proposal: {'apply' if publish_allowed else 'hold'} safe plan for `{content[:120]}`"
        evidence = (
            f"evidence: source={source}, type={event_type}, cycle={state.get('cycle', 0)}, "
            f"safety={'ok' if chain_ok else 'failed'}, publish={publish_allowed}, status={commit_status}"
        )

        enqueue_event(
            conn,
            source="deep-worker",
            event_type="evidence",
            content=evidence,
            meta={
                "parent_event_id": event_id,
                "safety_chain": chain,
                "commit_window": {
                    "base_version": base_version,
                    "observed_version": observed_version,
                    "status": commit_status,
                },
            },
        )
        if publish_allowed:
            enqueue_event(
                conn,
                source="deep-worker",
                event_type="proposal",
                content=proposal,
                meta={"parent_event_id": event_id, "safety_chain": chain},
            )
            enqueue_event(
                conn,
                source="deep-worker",
                event_type="deep_release",
                content=f"deep release published for event#{event_id}",
                meta={"parent_event_id": event_id, "commit_status": commit_status},
            )
        else:
            enqueue_event(
                conn,
                source="deep-worker",
                event_type="guard",
                content=f"deep publish blocked for event#{event_id}: {publish_reason}",
                meta={"parent_event_id": event_id, "commit_status": commit_status, "eval_gate": eval_gate},
            )
        enqueue_event(
            conn,
            source="deep-worker",
            event_type="trace",
            content=f"deep safety chain event#{event_id}: {json.dumps(chain, ensure_ascii=False)[:600]}",
            meta={"parent_event_id": event_id},
        )
        _insert_decision(
            conn,
            event_id=event_id,
            action="deep_publish" if publish_allowed else "rollback",
            reason="worker gate+mvcc checked",
            summary=(proposal if publish_allowed else f"blocked: {publish_reason}")[:220],
            meta={
                "worker": "deep",
                "parent_event_id": event_id,
                "safety_chain": chain,
                "eval_gate": eval_gate,
                "commit_window": {
                    "base_version": base_version,
                    "observed_version": observed_version,
                    "status": commit_status,
                },
            },
        )
        eval_score = 0.92 if publish_allowed else (0.66 if chain_ok else 0.3)
        eval_contract = EvalResult(
            id=make_contract_id("eval", event_id),
            source="deep-worker",
            suite="deep_eval_harness",
            score=eval_score,
            pass_flag=publish_allowed,
            regression=not chain_ok,
            findings=[
                str(eval_gate.get("status", "failed")),
                str(publish_reason)[:180],
            ],
        )
        kind, payload = contract_to_row("eval_result", eval_contract)
        _insert_contract(conn, event_id=event_id, kind=kind, payload_json=payload)

        rep_before = float(state.get("reward_rep_deep_worker", 50.0))
        delta = 0.45 if publish_allowed else -0.25
        rep_after = rep_before + delta
        state["reward_rep_deep_worker"] = rep_after
        reward_contract = RewardUpdate(
            id=make_contract_id("reward", event_id),
            source="reward-engine",
            actor_id="deep-worker",
            rep_before=rep_before,
            rep_after=rep_after,
            delta=delta,
            reason_codes=[commit_status, "publish_allowed" if publish_allowed else "publish_blocked"],
        )
        kind, payload = contract_to_row("reward_update", reward_contract)
        _insert_contract(conn, event_id=event_id, kind=kind, payload_json=payload)

        _mark_worker_done(conn, event_id)
        handled += 1

    conn.commit()
    if int(state.get("cycle", 0)) % 40 == 0:
        runtime_gc(conn)
    return handled


def runtime_gc(conn: sqlite3.Connection) -> None:
    thresholds = {
        "azi_events": 120000,
        "azi_decisions": 120000,
        "azi_protocol_flow": 120000,
        "azi_provider_routes": 120000,
        "azi_memory_vectors": 240000,
        "azi_causal_edges": 120000,
        "azi_deep_runs": 120000,
        "azi_eval_gates": 120000,
        "azi_commit_windows": 120000,
        "azi_guard_events": 120000,
        "azi_contracts": 120000,
    }
    for table, keep in thresholds.items():
        row = conn.execute(f"SELECT COUNT(1) AS c FROM {table}").fetchone()
        total = int(row["c"] or 0) if row else 0
        if total <= keep:
            continue
        drop_count = total - keep
        conn.execute(
            f"""
            DELETE FROM {table}
            WHERE id IN (
                SELECT id FROM {table}
                ORDER BY id ASC
                LIMIT ?
            )
            """,
            (drop_count,),
        )
    conn.commit()


def list_recent_decisions(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    n = max(1, min(int(limit), 200))
    return conn.execute(
        """
        SELECT id, event_id, ts, action, reason, summary, meta_json
        FROM azi_decisions
        ORDER BY id DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()


def _latest_by_type(conn: sqlite3.Connection, event_type: str) -> str:
    row = conn.execute(
        """
        SELECT ts, content
        FROM azi_events
        WHERE event_type=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (str(event_type),),
    ).fetchone()
    if row is None:
        return "-"
    ts = str(row["ts"])[-8:]
    content = str(row["content"] or "").replace("\n", " ").strip()
    return f"[{ts}] {content[:180]}"


def _recent_type_lines(conn: sqlite3.Connection, event_type: str, limit: int = 4) -> list[str]:
    n = max(1, min(int(limit), 20))
    rows = conn.execute(
        """
        SELECT ts, content
        FROM azi_events
        WHERE event_type=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (str(event_type), n),
    ).fetchall()
    out: list[str] = []
    for row in reversed(rows):
        out.append(f"[{str(row['ts'])[-8:]}] {str(row['content'] or '')[:180]}")
    return out


def _parse_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        obj = json.loads(str(raw or "{}"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _latest_event_detail(
    conn: sqlite3.Connection,
    event_types: list[str],
    *,
    source: str | None = None,
    content_like: str | None = None,
    limit_scan: int = 80,
) -> dict[str, Any] | None:
    types = [str(x).strip() for x in list(event_types or []) if str(x).strip()]
    if not types:
        return None
    n = max(1, min(int(limit_scan), 500))
    placeholders = ",".join("?" for _ in types)
    rows = conn.execute(
        f"""
        SELECT id, ts, source, event_type, content, meta_json
        FROM azi_events
        WHERE event_type IN ({placeholders})
        ORDER BY id DESC
        LIMIT ?
        """,
        (*types, n),
    ).fetchall()
    needle = str(content_like or "").strip().lower()
    for row in rows:
        row_source = str(row["source"] or "")
        row_content = str(row["content"] or "")
        if source and row_source != str(source):
            continue
        if needle and needle not in row_content.lower():
            continue
        return {
            "id": int(row["id"] or 0),
            "ts": str(row["ts"] or ""),
            "source": row_source,
            "event_type": str(row["event_type"] or ""),
            "content": row_content[:1000],
            "meta": _parse_json_dict(row["meta_json"]),
        }
    return None


def _recent_event_lines_by_types(
    conn: sqlite3.Connection,
    event_types: list[str],
    *,
    source: str | None = None,
    limit: int = 6,
) -> list[str]:
    types = [str(x).strip() for x in list(event_types or []) if str(x).strip()]
    if not types:
        return []
    n = max(1, min(int(limit), 30))
    scan = max(30, n * 6)
    placeholders = ",".join("?" for _ in types)
    rows = conn.execute(
        f"""
        SELECT ts, source, event_type, content
        FROM azi_events
        WHERE event_type IN ({placeholders})
        ORDER BY id DESC
        LIMIT ?
        """,
        (*types, scan),
    ).fetchall()
    out: list[str] = []
    for row in rows:
        row_source = str(row["source"] or "")
        if source and row_source != str(source):
            continue
        out.append(
            "[{ts}] {etype}({src}) {content}".format(
                ts=str(row["ts"])[-8:],
                etype=str(row["event_type"] or "-"),
                src=row_source or "-",
                content=str(row["content"] or "").replace("\n", " ")[:160],
            )
        )
        if len(out) >= n:
            break
    return list(reversed(out))


def _latest_decision_detail(
    conn: sqlite3.Connection,
    actions: list[str],
    *,
    worker: str | None = None,
    limit_scan: int = 120,
) -> dict[str, Any] | None:
    action_list = [str(x).strip() for x in list(actions or []) if str(x).strip()]
    if not action_list:
        return None
    n = max(1, min(int(limit_scan), 800))
    placeholders = ",".join("?" for _ in action_list)
    rows = conn.execute(
        f"""
        SELECT id, event_id, ts, action, reason, summary, meta_json
        FROM azi_decisions
        WHERE action IN ({placeholders})
        ORDER BY id DESC
        LIMIT ?
        """,
        (*action_list, n),
    ).fetchall()
    for row in rows:
        meta = _parse_json_dict(row["meta_json"])
        if worker and str(meta.get("worker", "")) != str(worker):
            continue
        return {
            "id": int(row["id"] or 0),
            "event_id": int(row["event_id"] or 0),
            "ts": str(row["ts"] or ""),
            "action": str(row["action"] or ""),
            "reason": str(row["reason"] or "")[:320],
            "summary": str(row["summary"] or "")[:320],
            "meta": meta,
        }
    return None


def _latest_contract_detail(
    conn: sqlite3.Connection,
    *,
    kind: str,
    suite: str | None = None,
    actor_id: str | None = None,
    limit_scan: int = 160,
) -> dict[str, Any] | None:
    n = max(1, min(int(limit_scan), 1000))
    rows = conn.execute(
        """
        SELECT id, ts, event_id, kind, payload_json
        FROM azi_contracts
        WHERE kind=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (str(kind), n),
    ).fetchall()
    for row in rows:
        payload = _parse_json_dict(row["payload_json"])
        if suite and str(payload.get("suite", "")) != str(suite):
            continue
        if actor_id and str(payload.get("actor_id", "")) != str(actor_id):
            continue
        return {
            "id": int(row["id"] or 0),
            "ts": str(row["ts"] or ""),
            "event_id": int(row["event_id"] or 0),
            "kind": str(row["kind"] or ""),
            "payload": payload,
        }
    return None


def _latest_dispatch_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    latest = _latest_contract_detail(conn, kind="dispatch_plan")
    if not latest:
        return {}
    payload = dict(latest.get("payload", {}) or {})
    items = list(payload.get("dispatch_plan", []) or [])
    compact_items: list[dict[str, Any]] = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        compact_items.append(
            {
                "worker": str(item.get("worker", "-"))[:32],
                "model_group": str(item.get("model_group", "-"))[:60],
                "tool": str(item.get("tool", "-"))[:100],
                "expected_output": str(item.get("expected_output", ""))[:160],
                "timeout_sec": max(0, _to_int(item.get("timeout_sec", 0), default=0)),
                "reversible": bool(item.get("reversible", True)),
            }
        )
    return {
        "id": str(payload.get("id", latest.get("id", "-"))),
        "ts": str(payload.get("ts", latest.get("ts", "-"))),
        "intent": str(payload.get("intent", ""))[:220],
        "task_type": str(payload.get("task_type", "-")),
        "risk_level": str(payload.get("risk_level", "-")),
        "issue_detected": bool(payload.get("issue_detected", False)),
        "issue_reason": str(payload.get("issue_reason", ""))[:180],
        "confidence": round(_safe_float(payload.get("confidence", 0.0), default=0.0), 4),
        "dispatch_plan": compact_items,
        "recommended_skills": [str(x).strip()[:80] for x in list(payload.get("recommended_skills", []) or [])[:16]],
        "success_criteria": [str(x)[:140] for x in list(payload.get("success_criteria", []) or [])[:5]],
        "rollback_plan": str(payload.get("rollback_plan", ""))[:220],
    }


def _build_deep_dream_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    deep_request = _latest_event_detail(conn, ["deep_request"])
    deep_release = _latest_event_detail(conn, ["deep_release"], source="deep-worker")
    deep_output = _latest_event_detail(conn, ["proposal", "evidence"], source="deep-worker")
    deep_blocked = _latest_event_detail(conn, ["guard"], source="deep-worker", content_like="deep publish blocked")
    deep_trace = _latest_event_detail(conn, ["trace"], source="deep-worker", content_like="deep safety chain")
    deep_decision = _latest_decision_detail(conn, ["deep_publish", "rollback"], worker="deep")
    deep_eval = _latest_contract_detail(conn, kind="eval_result", suite="deep_eval_harness")
    deep_reward = _latest_contract_detail(conn, kind="reward_update", actor_id="deep-worker")
    deep_recent = _recent_event_lines_by_types(
        conn,
        ["deep_request", "evidence", "proposal", "deep_release", "guard", "trace"],
        limit=6,
    )

    dream_request = _latest_event_detail(conn, ["dream_request"])
    dream_output = _latest_event_detail(conn, ["dream"], source="deep-worker")
    dream_release = _latest_event_detail(conn, ["dream_release"], source="deep-worker")
    dream_decision = _latest_decision_detail(conn, ["dream_reflect"], worker="dream")
    dream_eval = _latest_contract_detail(conn, kind="eval_result", suite="dream_replay")
    dream_reward = _latest_contract_detail(conn, kind="reward_update", actor_id="dream-worker")
    dream_recent = _recent_event_lines_by_types(
        conn,
        ["dream_request", "dream", "dream_release"],
        limit=6,
    )

    return {
        "deep": {
            "request": deep_request,
            "output": deep_output,
            "release": deep_release,
            "blocked": deep_blocked,
            "decision": deep_decision,
            "trace": deep_trace,
            "eval": deep_eval,
            "reward": deep_reward,
            "recent": deep_recent,
        },
        "dream": {
            "request": dream_request,
            "output": dream_output,
            "release": dream_release,
            "decision": dream_decision,
            "eval": dream_eval,
            "reward": dream_reward,
            "recent": dream_recent,
        },
    }


def _recent_protocol_lines(conn: sqlite3.Connection, kind: str, limit: int = 4) -> list[str]:
    n = max(1, min(int(limit), 20))
    rows = conn.execute(
        """
        SELECT ts, payload_json
        FROM azi_protocol_flow
        WHERE kind=?
        ORDER BY id DESC
        LIMIT ?
        """,
        (str(kind), n),
    ).fetchall()
    out: list[str] = []
    for row in reversed(rows):
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except Exception:
            payload = {}
        if kind == "task":
            msg = f"{payload.get('task_id', '-')}: {payload.get('title', '-')}"
        elif kind == "evidence":
            item_count = len(list(payload.get("items", []) or []))
            msg = f"{payload.get('pack_id', '-')}: items={item_count}"
        else:
            msg = f"{payload.get('proposal_id', '-')}: action={payload.get('action', '-')}"
        out.append(f"[{str(row['ts'])[-8:]}] {str(msg)[:180]}")
    return out


def _recent_commit_window_lines(conn: sqlite3.Connection, limit: int = 6) -> list[str]:
    n = max(1, min(int(limit), 30))
    rows = conn.execute(
        """
        SELECT ts, actor, event_id, base_version, observed_version, status, note
        FROM azi_commit_windows
        ORDER BY id DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    out: list[str] = []
    for row in reversed(rows):
        out.append(
            "[{ts}] {actor} event#{eid} v{base}->{obs} {status} {note}".format(
                ts=str(row["ts"])[-8:],
                actor=str(row["actor"] or "-"),
                eid=int(row["event_id"] or 0),
                base=int(row["base_version"] or 0),
                obs=int(row["observed_version"] or 0),
                status=str(row["status"] or "-"),
                note=str(row["note"] or "")[:80],
            )
        )
    return out


def _recent_eval_gate_lines(conn: sqlite3.Connection, limit: int = 6) -> list[str]:
    n = max(1, min(int(limit), 30))
    rows = conn.execute(
        """
        SELECT ts, event_id, gate_name, status, blocking
        FROM azi_eval_gates
        ORDER BY id DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    out: list[str] = []
    for row in reversed(rows):
        out.append(
            "[{ts}] event#{eid} {gate} {status} blocking={blocking}".format(
                ts=str(row["ts"])[-8:],
                eid=int(row["event_id"] or 0),
                gate=str(row["gate_name"] or "-"),
                status=str(row["status"] or "-"),
                blocking=int(row["blocking"] or 0),
            )
        )
    return out


def _recent_murmur_lines(conn: sqlite3.Connection, limit: int = 6) -> list[str]:
    return _recent_type_lines(conn, "shallow", limit=limit)


def _compose_flow_reflection(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """
        SELECT source, COUNT(1) AS c
        FROM (
            SELECT source
            FROM azi_events
            WHERE event_type IN (
                'input', 'iteration', 'deep_request', 'dream_request', 'dream',
                'web_probe', 'file_feed', 'vscode_observer', 'social', 'device_capture', 'shallow'
            )
              AND source NOT IN (
                'brain-loop', 'deep-worker', 'risk-gate', 'emergence-guard', 'health-check'
              )
            ORDER BY id DESC
            LIMIT 120
        ) AS t
        GROUP BY source
        ORDER BY c DESC
        """
    ).fetchall()
    if not rows:
        return "信息流很安静，我先保持低负荷监听。"

    total = sum(int(r["c"] or 0) for r in rows)
    top_source = str(rows[0]["source"] or "-")
    top_count = int(rows[0]["c"] or 0)
    ratio = (top_count / max(1, total)) * 100.0

    guard_count = int(
        conn.execute(
            """
            SELECT COUNT(1) AS c
            FROM (
                SELECT event_type
                FROM azi_events
                ORDER BY id DESC
                LIMIT 80
            ) AS t
            WHERE event_type='guard'
            """
        ).fetchone()["c"]
        or 0
    )

    if "web" in top_source:
        tone = "外部网页信号占主导，我会优先做事实压缩再入链路。"
    elif "file" in top_source or "vscode" in top_source:
        tone = "代码与文件流更强，我会先稳住上下文一致性。"
    elif "social" in top_source:
        tone = "对话输入密度上升，我会把可执行建议放在前面。"
    elif "device" in top_source:
        tone = "设备采集流量偏高，我会先做边界和风险筛查。"
    else:
        tone = "多源输入比较均衡，我会维持快慢路径协同。"

    risk_hint = "警戒信号偏高，先收敛再扩展。" if guard_count >= 6 else "风险闸门目前可控。"
    return (
        f"最近120条输入里，`{top_source}` 占比约 {ratio:.0f}%（{top_count}/{total}）。"
        f"{tone} {risk_hint}"
    )


def _stability_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    st = _ensure_stability_state(state)
    cycle = _to_int(state.get("cycle", 0), default=0)
    cooldown_raw = dict(st.get("route_cooldown_until", {}) or {})
    active_cooldowns = {
        str(k): _to_int(v, default=0)
        for k, v in cooldown_raw.items()
        if _to_int(v, default=0) > cycle
    }
    return {
        "mode": str(st.get("mode", "normal")),
        "panic_count": _to_int(st.get("panic_count", 0), default=0),
        "degraded_cycles": _to_int(st.get("degraded_cycles", 0), default=0),
        "brain_budget": {
            "requested": _to_int(st.get("requested_brain_events", 12), default=12),
            "effective": _to_int(st.get("effective_brain_events", 12), default=12),
        },
        "worker_budget": {
            "requested": _to_int(st.get("requested_worker_events", 6), default=6),
            "effective": _to_int(st.get("effective_worker_events", 6), default=6),
        },
        "route": {
            "last_group": str(st.get("last_route_group", "-")),
            "last_override": str(st.get("last_route_override", "")),
            "last_error": str(st.get("last_route_error", "")),
            "consecutive_fallbacks": _to_int(st.get("consecutive_fallbacks", 0), default=0),
            "active_cooldowns": active_cooldowns,
        },
        "last_budget_reason": str(st.get("last_budget_reason", "normal")),
        "last_updated": str(st.get("last_updated", "-")),
    }


def _orchestration_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    orch = _ensure_orchestration_state(state)
    groups = dict(orch.get("group_metrics", {}) or {})
    models = dict(orch.get("model_metrics", {}) or {})
    task_routes = dict(orch.get("task_route_stats", {}) or {})

    sorted_groups = sorted(
        [
            (
                str(k),
                float(dict(v or {}).get("success_rate", 0.0) or 0.0),
                int(dict(v or {}).get("total", 0) or 0),
                float(dict(v or {}).get("latency_ms_ema", 0.0) or 0.0),
            )
            for k, v in groups.items()
        ],
        key=lambda x: (x[1], x[2], -x[3]),
        reverse=True,
    )
    top_groups = [
        {
            "group": g,
            "success_rate": round(sr, 4),
            "total": total,
            "latency_ms_ema": round(lat, 2),
        }
        for g, sr, total, lat in sorted_groups[:5]
    ]

    sorted_models = sorted(
        [
            (
                str(k),
                float(dict(v or {}).get("success_rate", 0.0) or 0.0),
                int(dict(v or {}).get("total", 0) or 0),
            )
            for k, v in models.items()
        ],
        key=lambda x: (x[1], x[2]),
        reverse=True,
    )
    top_models = [{"model_key": k, "success_rate": round(sr, 4), "total": total} for k, sr, total in sorted_models[:6]]

    return {
        "last_task_type": str(orch.get("last_task_type", "-")),
        "last_route_group": str(orch.get("last_route_group", "-")),
        "last_route_reason": str(orch.get("last_route_reason", "-")),
        "last_provider": str(orch.get("last_provider", "-")),
        "last_model": str(orch.get("last_model", "-")),
        "last_error": str(orch.get("last_error", "")),
        "last_latency_ms": _to_int(orch.get("last_latency_ms", 0), default=0),
        "last_cost_usd": round(_safe_float(orch.get("last_cost_usd", 0.0), default=0.0), 6),
        "top_groups": top_groups,
        "top_models": top_models,
        "task_route_stats": task_routes,
        "updated_at": str(orch.get("updated_at", "-")),
    }


def _work_memory_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    wm = _ensure_work_memory_state(state)
    prefs = dict(wm.get("task_preferences", {}) or {})
    task_stats = dict(wm.get("task_route_stats", {}) or {})

    top_preferences: list[dict[str, Any]] = []
    for task_type, groups in prefs.items():
        group_list = [str(x).strip() for x in list(groups or []) if str(x).strip()]
        if not group_list:
            continue
        top_preferences.append({"task_type": str(task_type), "preferred_groups": group_list[:4]})

    task_totals: dict[str, int] = {}
    for task_type, row in task_stats.items():
        if not isinstance(row, dict):
            continue
        total = sum(max(0, _to_int(dict(m or {}).get("total", 0), default=0)) for m in row.values())
        if total > 0:
            task_totals[str(task_type)] = int(total)

    return {
        "strength": str(wm.get("strength", "balanced")),
        "updated_at": str(wm.get("updated_at", "-")),
        "top_preferences": top_preferences[:10],
        "task_totals": task_totals,
        "recent_successes": list(wm.get("recent_successes", []) or [])[-8:],
    }


def build_snapshot_payload(conn: sqlite3.Connection, state: dict[str, Any]) -> dict[str, Any]:
    state_version = _get_state_version(conn)
    decisions = list_recent_decisions(conn, limit=5)
    latest = decisions[0] if decisions else None
    deep_dream = _build_deep_dream_snapshot(conn)
    dispatch = _latest_dispatch_snapshot(conn)

    if latest is None:
        decision_text = "action=- | source=- | model=-\nreason=-\nnext=-\nprocessing=-\nreflection=-"
    else:
        decision_text = (
            f"action={latest['action']} | source=azi_rebuild | model=rule+10d\n"
            f"reason={str(latest['reason'])[:220]}\n"
            f"next={str(latest['summary'])[:220]}\n"
            f"processing=event#{latest['event_id']}\n"
            f"reflection={str(latest['summary'])[:160]}"
        )

    trajectory: list[str] = []
    for row in reversed(decisions):
        trajectory.append(
            f"[{str(row['ts'])[-8:]}] action={row['action']} | {str(row['summary'])[:100]}"
        )

    protocol = {
        "tasks": _recent_protocol_lines(conn, "task", limit=4),
        "evidences": _recent_protocol_lines(conn, "evidence", limit=4),
        "proposals": _recent_protocol_lines(conn, "proposal", limit=4),
    }

    external = {
        "Autoweb": _latest_by_type(conn, "web_probe"),
        "File Feed": _latest_by_type(conn, "file_feed"),
        "Social": _latest_by_type(conn, "social"),
        "API Bridge": _latest_by_type(conn, "api_bridge"),
        "Fact Lane": _latest_by_type(conn, "fact"),
        "Risk Gate": _latest_by_type(conn, "risk"),
        "Guard": _latest_by_type(conn, "guard"),
        "Deep Worker": _latest_by_type(conn, "deep_request"),
        "Deep Release": _latest_by_type(conn, "deep_release"),
        "Dream Worker": _latest_by_type(conn, "dream_request"),
        "Dream": _latest_by_type(conn, "dream"),
        "Dream Release": _latest_by_type(conn, "dream_release"),
    }

    narrative = state.get("last_reason", "-")
    post = latest["summary"] if latest is not None else "-"
    raw = "-"
    narrative_bundle = (
        f"[Narrative]\n{str(narrative)[:500]}\n\n"
        f"[Post]\n{str(post)[:500]}\n\n"
        f"[Model Raw]\n{str(raw)[:500]}"
    )

    return {
        "updated_at": now_iso(),
        "state": {
            "cycle": state.get("cycle", "-"),
            "energy": state.get("energy", "-"),
            "stress": state.get("stress", "-"),
            "uncertainty": state.get("uncertainty", "-"),
            "integrity": state.get("integrity", "-"),
            "continuity": state.get("continuity", "-"),
            "mvcc_version": state_version,
            "permission_level": state.get("permission_level", "-"),
            "last_event_id": state.get("last_event_id", "-"),
        },
        "decision_text": decision_text,
        "trajectory": trajectory,
        "external": external,
        "protocol": protocol,
        "guardrails": {
            "state_version": state_version,
            "commit_windows": _recent_commit_window_lines(conn, limit=6),
            "eval_gates": _recent_eval_gate_lines(conn, limit=6),
        },
        "murmur": {
            "reflection": _compose_flow_reflection(conn),
            "latest": _recent_murmur_lines(conn, limit=6),
        },
        "skill_specialist": {"active": False, "domain": "-", "expert_module": "-"},
        "skill_split": {"summary": "rebuild-mode", "active_routes": []},
        "deep_dream": deep_dream,
        "dispatch": dispatch,
        "narrative_bundle": narrative_bundle,
        "stability": _stability_snapshot(state),
        "orchestration": _orchestration_snapshot(state),
        "work_memory": _work_memory_snapshot(state),
    }


def append_health_record(conn: sqlite3.Connection, service: str, status: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO azi_health(ts, service, status, detail) VALUES(?, ?, ?, ?)",
        (now_iso(), str(service), str(status), str(detail)),
    )
    conn.commit()


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if handle == 0:
                return False
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            if ok == 0:
                return False
            return int(code.value) == 259
        else:
            os.kill(int(pid), 0)
            return True
    except Exception:
        return False
