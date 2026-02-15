from __future__ import annotations

import json
import time
from typing import Any, Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class Task(BaseModel):
    task_id: str
    created_at: str = Field(default_factory=now_iso)
    source_event_id: int
    title: str
    objective: str
    priority: Literal["low", "mid", "high"] = "mid"
    constraints: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    evidence_id: str
    kind: Literal["fact", "memory", "observation", "trace"] = "observation"
    content: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = "unknown"
    ref_event_id: int | None = None


class EvidencePack(BaseModel):
    pack_id: str
    created_at: str = Field(default_factory=now_iso)
    source_task_id: str
    items: list[EvidenceItem] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)


class Proposal(BaseModel):
    proposal_id: str
    created_at: str = Field(default_factory=now_iso)
    source_task_id: str
    action: str
    rationale: str
    risk_level: Literal["low", "mid", "high"] = "mid"
    rollback_plan: str = "fallback to previous stable state"
    requires_approval: bool = False
    status: Literal["draft", "approved", "rejected", "executed"] = "draft"


def make_task(event_id: int, content: str, source: str, priority: str = "mid") -> Task:
    task_id = f"task-{event_id}"
    title = str(content or "").strip().splitlines()[0][:72] or f"event-{event_id}"
    objective = str(content or "").strip()[:400]
    constraints = ["keep_state_consistent", "prefer_reversible_changes", "emit_actionable_output"]
    tags = [str(source or "unknown"), "runtime"]
    pr = priority if priority in {"low", "mid", "high"} else "mid"
    return Task(
        task_id=task_id,
        source_event_id=int(event_id),
        title=title,
        objective=objective,
        priority=pr,
        constraints=constraints,
        tags=tags,
    )


def make_evidence_pack(
    *,
    source_task_id: str,
    facts: list[dict[str, Any]],
    vectors: list[dict[str, Any]],
    observation: str,
    event_id: int,
) -> EvidencePack:
    items: list[EvidenceItem] = []
    for i, fact in enumerate(facts[:6], start=1):
        items.append(
            EvidenceItem(
                evidence_id=f"{source_task_id}-fact-{i}",
                kind="fact",
                content=str(fact.get("claim_text", ""))[:400],
                confidence=_clamp01(float(fact.get("confidence", 0.55))),
                source=str(fact.get("source", "fact-memory")),
                ref_event_id=int(fact.get("last_seen_event_id", 0) or 0) or None,
            )
        )
    for i, vec in enumerate(vectors[:6], start=1):
        items.append(
            EvidenceItem(
                evidence_id=f"{source_task_id}-mem-{i}",
                kind="memory",
                content=str(vec.get("content", ""))[:400],
                confidence=_clamp01(float(vec.get("score", 0.45))),
                source=str(vec.get("source", "vector-memory")),
                ref_event_id=int(vec.get("event_id", 0) or 0) or None,
            )
        )
    if observation:
        items.append(
            EvidenceItem(
                evidence_id=f"{source_task_id}-obs-1",
                kind="observation",
                content=str(observation)[:400],
                confidence=0.5,
                source="event",
                ref_event_id=int(event_id),
            )
        )

    return EvidencePack(
        pack_id=f"pack-{source_task_id}",
        source_task_id=source_task_id,
        items=items,
        retrieval={
            "fact_hits": len(facts),
            "memory_hits": len(vectors),
        },
    )


def make_proposal(
    *,
    source_task_id: str,
    action: str,
    rationale: str,
    risk_level: str,
    requires_approval: bool,
    rollback_plan: str,
) -> Proposal:
    rl = risk_level if risk_level in {"low", "mid", "high"} else "mid"
    return Proposal(
        proposal_id=f"proposal-{source_task_id}",
        source_task_id=source_task_id,
        action=str(action),
        rationale=str(rationale)[:600],
        risk_level=rl,  # type: ignore[arg-type]
        requires_approval=bool(requires_approval),
        rollback_plan=str(rollback_plan)[:400],
        status="draft",
    )


def protocol_to_row(kind: Literal["task", "evidence", "proposal"], obj: BaseModel) -> tuple[str, str]:
    return kind, json.dumps(obj.model_dump(mode="json"), ensure_ascii=False)
