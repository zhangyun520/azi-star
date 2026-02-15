from __future__ import annotations

import json
import time
from typing import Literal

from pydantic import BaseModel, Field


SCHEMA_VERSION = "cos.v0.1"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def make_contract_id(prefix: str, event_id: int) -> str:
    ts_ms = int(time.time() * 1000)
    return f"{str(prefix)}-{int(event_id)}-{ts_ms}"


class ContractBase(BaseModel):
    schema_version: str = SCHEMA_VERSION
    id: str
    ts: str = Field(default_factory=now_iso)
    source: str = "runtime"


class PlanStep(BaseModel):
    step_id: str
    action: str
    tool: str
    expected_output: str


class Plan(ContractBase):
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    rollback_plan: str = "fallback_to_previous_state"


class RiskReport(ContractBase):
    risk_level: Literal["L0", "L1", "L2", "L3"] = "L1"
    reasons: list[str] = Field(default_factory=list)
    required_permission: str = "none"
    requires_approval: bool = False
    forbidden: bool = False


class Approval(ContractBase):
    decision: Literal["approve", "reject"] = "reject"
    approver: str = "policy"
    reason: str = ""
    scope: list[str] = Field(default_factory=list)


class ToolCallTrace(BaseModel):
    tool: str
    args_hash: str
    started_ts: str
    ended_ts: str
    result_digest: str


class ExecTrace(ContractBase):
    trace_id: str
    plan_id: str
    risk_report_id: str
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    status: Literal["success", "failed", "blocked", "rolled_back"] = "success"


class EvalResult(ContractBase):
    suite: str
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    pass_flag: bool = Field(default=False, alias="pass")
    regression: bool = False
    findings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class RewardUpdate(ContractBase):
    actor_id: str
    rep_before: float = 0.0
    rep_after: float = 0.0
    delta: float = 0.0
    reason_codes: list[str] = Field(default_factory=list)


class DispatchItem(BaseModel):
    model_config = {"protected_namespaces": ()}

    worker: Literal["shallow", "deep", "coder", "mcp", "api"] = "shallow"
    model_group: str = "shallow_chain"
    tool: str = ""
    input: str = ""
    expected_output: str = ""
    timeout_sec: int = Field(default=45, ge=5, le=900)
    reversible: bool = True


class DispatchPlan(ContractBase):
    intent: str = ""
    task_type: Literal["shallow", "deep", "dream", "coding", "ops"] = "shallow"
    risk_level: Literal["L0", "L1", "L2", "L3"] = "L1"
    dispatch_plan: list[DispatchItem] = Field(default_factory=list)
    recommended_skills: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    rollback_plan: str = "fallback_to_previous_state + reopen_at_7d"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    issue_detected: bool = True
    issue_reason: str = ""
    hub_prompt: str = ""


def contract_to_row(kind: str, obj: BaseModel) -> tuple[str, str]:
    return str(kind), json.dumps(obj.model_dump(mode="json", by_alias=True), ensure_ascii=False)
