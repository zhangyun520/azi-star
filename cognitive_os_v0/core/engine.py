from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .memory import build_memory_context
from .schemas import ActionPlan, RiskAssessment, ToolCall


@dataclass
class EngineConfig:
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    key_env: str = "OPENAI_API_KEY"
    timeout_sec: float = 45.0


def _load_system_prompt(base_dir: Path) -> str:
    p = base_dir / "prompts" / "system.md"
    if not p.exists():
        return (
            "You are Cognitive OS planner. "
            "Return strict JSON with fields: intent_analysis, risk{level,reasoning}, "
            "draft_content, plan[{tool_name,parameters}], requires_confirmation."
        )
    return p.read_text(encoding="utf-8", errors="ignore")


def _api_call(cfg: EngineConfig, *, system_prompt: str, user_goal: str, memory_ctx: str) -> str:
    key = str(os.environ.get(cfg.key_env, "")).strip()
    if not key:
        raise RuntimeError(f"missing env key: {cfg.key_env}")

    url = cfg.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Goal:\n"
                    f"{user_goal}\n\n"
                    "Recent reflections:\n"
                    f"{memory_ctx}\n\n"
                    "Return JSON only."
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.25,
    }
    req = Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
    )
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=float(cfg.timeout_sec)) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        msg = ""
        try:
            msg = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            msg = str(exc)
        raise RuntimeError(f"http_error:{getattr(exc, 'code', 0)}:{msg[:220]}") from exc
    except URLError as exc:
        raise RuntimeError(f"url_error:{exc}") from exc

    try:
        obj = json.loads(text)
    except Exception as exc:
        raise RuntimeError(f"non_json_response:{text[:220]}") from exc
    try:
        content = obj["choices"][0]["message"]["content"]
        return str(content or "")
    except Exception as exc:
        raise RuntimeError(f"missing_choice_content:{str(obj)[:220]}") from exc


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def _fallback_plan(user_goal: str) -> ActionPlan:
    goal = str(user_goal or "").strip()
    low = goal.lower()

    if _contains_any(low, ["email", "mail"]) or _contains_any(goal, ["邮件", "通知"]):
        return ActionPlan(
            intent_analysis="User wants outbound communication draft with confirmation.",
            risk=RiskAssessment(level="L2", reasoning="External communication can cause mis-send risk."),
            draft_content=(
                "Subject: Update Notice\n\n"
                f"Hello,\n\nThis is a draft update regarding: {goal}\n"
                "Please review and confirm before sending.\n"
            ),
            plan=[
                ToolCall(
                    tool_name="dummy_send_email",
                    parameters={
                        "to": "recipient@example.com",
                        "subject": "Update Notice",
                        "body": f"Draft message about: {goal}",
                    },
                )
            ],
            requires_confirmation=True,
        )

    if _contains_any(low, ["save", "write", "file"]) or _contains_any(goal, ["保存", "写入", "文件"]):
        return ActionPlan(
            intent_analysis="User requests local write operation.",
            risk=RiskAssessment(level="L1", reasoning="Local write should require confirmation."),
            draft_content=None,
            plan=[
                ToolCall(
                    tool_name="dummy_write_file",
                    parameters={"path": "notes/output.txt", "content": goal},
                )
            ],
            requires_confirmation=True,
        )

    return ActionPlan(
        intent_analysis="Read-only or text-only transformation request.",
        risk=RiskAssessment(level="L0", reasoning="No external side effect in default route."),
        draft_content=f"Summary draft: {goal}",
        plan=[],
        requires_confirmation=False,
    )


def generate_action_plan(
    *,
    base_dir: Path,
    user_goal: str,
    recent_reflections: list[dict[str, Any]],
    config: EngineConfig | None = None,
) -> tuple[ActionPlan, dict[str, Any]]:
    cfg = config or EngineConfig()
    system_prompt = _load_system_prompt(base_dir)
    memory_ctx = build_memory_context(recent_reflections)

    try:
        content = _api_call(cfg, system_prompt=system_prompt, user_goal=user_goal, memory_ctx=memory_ctx)
        payload = json.loads(content)
        plan = ActionPlan.model_validate(payload)
        return plan, {"mode": "api", "model": cfg.model, "error": None}
    except Exception as exc:
        plan = _fallback_plan(user_goal)
        return plan, {"mode": "fallback", "model": cfg.model, "error": str(exc)[:300]}
