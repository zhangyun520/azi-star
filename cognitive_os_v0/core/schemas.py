from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    tool_name: str = Field(description="Tool name, e.g. dummy_send_email")
    parameters: Dict[str, Any] = Field(description="Tool input parameters")


class RiskAssessment(BaseModel):
    level: Literal["L0", "L1", "L2", "L3"] = Field(
        description="L0 read-only, L1 local mild write, L2 external or irreversible, L3 forbidden"
    )
    reasoning: str = Field(description="Risk reason and worst-case impact")


class ActionPlan(BaseModel):
    """Single-shot structured output contract for Cognitive OS v0."""

    intent_analysis: str = Field(description="One-paragraph intent and hidden boundary analysis")
    risk: RiskAssessment = Field(description="Risk assessment produced with the plan")
    draft_content: Optional[str] = Field(
        default=None,
        description="Draft text shown to user when task includes writing or communication",
    )
    plan: List[ToolCall] = Field(description="Concrete tool call sequence")
    requires_confirmation: bool = Field(
        description="Must be true for any action above pure read-only flow"
    )


class ReflectionEvent(BaseModel):
    ts: str
    run_id: str = ""
    user_goal: str
    outcome: Literal["approved", "rejected", "blocked", "failed"]
    risk_level: Literal["L0", "L1", "L2", "L3"]
    model_plan: dict[str, Any] = Field(default_factory=dict)
    final_plan: dict[str, Any] = Field(default_factory=dict)
    edit_diff: str = ""
    notes: str = ""
    gold_result: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"protected_namespaces": ()}
