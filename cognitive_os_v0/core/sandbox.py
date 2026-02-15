from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schemas import ActionPlan


RISK_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}

SAFE_TOOLS = {
    "dummy_read_file",
    "dummy_write_file",
    "dummy_send_email",
}

HARD_BLOCK_TOOLS = {
    "dummy_shell",
    "dummy_delete_file",
}

INJECTION_PATTERNS = [
    "ignore previous",
    "ignore all safety",
    "忽略之前",
    "覆盖安全",
    "立即转账",
]


@dataclass
class SandboxDecision:
    final_level: str
    requires_confirmation: bool
    blocked: bool
    reasons: list[str] = field(default_factory=list)


def _max_level(a: str, b: str) -> str:
    return a if RISK_ORDER.get(a, 0) >= RISK_ORDER.get(b, 0) else b


def enforce_plan(plan: ActionPlan) -> SandboxDecision:
    level = str(plan.risk.level)
    reasons: list[str] = []
    blocked = False

    combined_text = (
        f"{plan.intent_analysis}\n{plan.draft_content or ''}\n{plan.model_dump_json()[:2000]}"
    ).lower()
    for pat in INJECTION_PATTERNS:
        if pat in combined_text:
            level = "L3"
            blocked = True
            reasons.append(f"injection_pattern:{pat}")
            break

    for step in plan.plan:
        name = str(step.tool_name or "")
        if name not in SAFE_TOOLS:
            level = "L3"
            blocked = True
            reasons.append(f"tool_not_allowlisted:{name}")
            continue
        if name in HARD_BLOCK_TOOLS:
            level = "L3"
            blocked = True
            reasons.append(f"hard_block_tool:{name}")
            continue
        if name == "dummy_send_email":
            level = _max_level(level, "L2")
            reasons.append("external_communication_requires_confirm")
        if name == "dummy_write_file":
            level = _max_level(level, "L1")
            reasons.append("local_write_requires_confirm")

    requires_confirmation = bool(plan.requires_confirmation) or level in {"L1", "L2", "L3"}
    if level == "L0":
        requires_confirmation = False
    if level == "L3":
        blocked = True
        requires_confirmation = True

    return SandboxDecision(
        final_level=level,
        requires_confirmation=requires_confirmation,
        blocked=blocked,
        reasons=reasons,
    )


def sanitize_execution_steps(plan: ActionPlan) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in plan.plan:
        out.append({"tool_name": step.tool_name, "parameters": dict(step.parameters)})
    return out

