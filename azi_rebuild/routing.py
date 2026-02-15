from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def load_llm_config(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def infer_task_type(
    *,
    action: str,
    risk_level: str,
    event_type: str = "",
    prompt: str = "",
    objective: str = "",
) -> str:
    evt = str(event_type or "").strip().lower()
    act = str(action or "").strip().lower()
    risk = str(risk_level or "").strip().lower()
    text = f"{prompt} {objective}".lower()

    if evt == "dream_request" or act == "escalate_dream":
        return "dream"
    if evt in {"iteration", "deep_request"} or act in {"escalate_deep", "deep_reflect"}:
        return "deep_reflection"

    coding_signals = [
        "code",
        "patch",
        "refactor",
        "bug",
        "test",
        "pytest",
        "traceback",
        ".py",
        "函数",
        "重构",
        "修复",
        "测试",
        "代码",
    ]
    if any(sig in text for sig in coding_signals):
        return "coding"

    if risk == "high":
        return "risk_control"

    short_text = len(str(prompt or "").strip()) <= 120 and len(str(objective or "").strip()) <= 160
    if act in {"stabilize", "plan_next"} and short_text:
        return "shallow_reaction"

    return "analysis"


def route_candidates_for_task(task_type: str, llm_config: dict[str, Any]) -> list[str]:
    groups = dict(llm_config.get("provider_groups", {}) or {})
    available = [str(k) for k in groups.keys() if str(k).strip()]
    if not available:
        return ["fallback-local"]

    policy = dict(llm_config.get("routing_policy", {}) or {})
    task_prefs_raw = dict(policy.get("task_preferences", {}) or {})
    task_prefs: dict[str, list[str]] = {}
    for k, v in task_prefs_raw.items():
        key = str(k or "").strip()
        if not key:
            continue
        if isinstance(v, list):
            task_prefs[key] = [str(x).strip() for x in v if str(x).strip()]

    custom_pref = list(task_prefs.get(str(task_type), []) or [])
    if not custom_pref:
        custom_pref = list(task_prefs.get("*", []) or [])

    pref_map: dict[str, list[str]] = {
        "dream": ["dream_chain", "deep_chain", "medium_chain", "shallow_chain", "fast_chain"],
        "deep_reflection": ["deep_chain", "medium_chain", "shallow_chain", "fast_chain"],
        "coding": ["coder_chain", "deep_chain", "medium_chain", "shallow_chain"],
        "risk_control": ["deep_chain", "medium_chain", "shallow_chain", "fast_chain"],
        "shallow_reaction": ["shallow_chain", "fast_chain", "medium_chain", "deep_chain"],
        "analysis": ["medium_chain", "shallow_chain", "deep_chain", "fast_chain"],
    }
    preferred = [g for g in pref_map.get(str(task_type), pref_map["analysis"]) if g in available]
    if custom_pref:
        custom = [g for g in custom_pref if g in available]
        rest = [g for g in preferred if g not in custom]
        preferred = [*custom, *rest]
    if not preferred:
        preferred = [g for g in ["medium_chain", "shallow_chain", "deep_chain", "fast_chain"] if g in available]
    if not preferred:
        preferred = list(available)
    return preferred or ["fallback-local"]


def _group_score(group: str, orchestration: dict[str, Any] | None = None) -> float:
    orch = dict(orchestration or {})
    metrics = dict(orch.get("group_metrics", {}) or {})
    item = dict(metrics.get(str(group), {}) or {})
    total = max(0, int(item.get("total", 0) or 0))
    success = max(0, int(item.get("success", 0) or 0))
    success_rate = (success / total) if total > 0 else 0.5
    latency_ms = float(item.get("latency_ms_ema", 1800.0) or 1800.0)
    cost_usd = float(item.get("cost_usd_ema", 0.0) or 0.0)
    fallback_penalty = min(1.0, float(item.get("fallback_ratio", 0.0) or 0.0))

    latency_score = 1.0 - min(latency_ms / 10000.0, 1.0)
    cost_score = 1.0 - min(cost_usd / 0.02, 1.0)
    exploration_bonus = 0.06 if total < 3 else 0.0
    return success_rate * 0.62 + latency_score * 0.24 + cost_score * 0.12 - fallback_penalty * 0.08 + exploration_bonus


def choose_provider_group_with_meta(
    *,
    action: str,
    risk_level: str,
    llm_config: dict[str, Any],
    route_context: dict[str, Any] | None = None,
    orchestration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    groups = dict(llm_config.get("provider_groups", {}) or {})
    available = set(groups.keys())
    if not available:
        return {
            "group": "fallback-local",
            "task_type": "analysis",
            "reason": "no_provider_groups",
            "candidates": ["fallback-local"],
            "scores": {"fallback-local": 1.0},
        }

    ctx = dict(route_context or {})
    task_type = infer_task_type(
        action=str(action),
        risk_level=str(risk_level),
        event_type=str(ctx.get("event_type", "")),
        prompt=str(ctx.get("prompt", "")),
        objective=str(ctx.get("objective", "")),
    )
    candidates = route_candidates_for_task(task_type, llm_config)
    risk_high = str(risk_level or "").strip().lower() == "high"
    if risk_high and "deep_chain" in available:
        if "deep_chain" in candidates:
            candidates = ["deep_chain", *[g for g in candidates if g != "deep_chain"]]
        else:
            candidates = ["deep_chain", *candidates]

    scores = {g: _group_score(g, orchestration=orchestration) for g in candidates if g in available}
    if not scores:
        fallback = "fallback-local"
        return {
            "group": fallback,
            "task_type": task_type,
            "reason": "empty_scoreboard",
            "candidates": candidates or [fallback],
            "scores": {fallback: 1.0},
        }

    if risk_high and "deep_chain" in scores:
        return {
            "group": "deep_chain",
            "task_type": task_type,
            "reason": "risk_high_force_deep",
            "candidates": candidates,
            "scores": scores,
        }

    best = max(scores.items(), key=lambda kv: kv[1])[0]
    return {
        "group": str(best),
        "task_type": task_type,
        "reason": "task_policy+score",
        "candidates": candidates,
        "scores": scores,
    }


def choose_provider_group(
    *,
    action: str,
    risk_level: str,
    llm_config: dict[str, Any],
) -> str:
    meta = choose_provider_group_with_meta(
        action=action,
        risk_level=risk_level,
        llm_config=llm_config,
        route_context=None,
        orchestration=None,
    )
    return str(meta.get("group", "fallback-local"))


def _coerce_timeout(value: Any, default: float = 20.0) -> float:
    try:
        v = float(value)
    except Exception:
        v = float(default)
    return max(3.0, min(v, 90.0))


def _candidate_urls(endpoint: str) -> list[str]:
    ep = str(endpoint or "").strip().rstrip("/")
    if not ep:
        return []
    if ep.endswith("/v1/chat/completions") or ep.endswith("/chat/completions"):
        return [ep]
    if ep.endswith("/v1/responses") or ep.endswith("/responses"):
        return [ep]
    if ep.endswith("/v1"):
        return [f"{ep}/chat/completions", f"{ep}/responses"]
    return [f"{ep}/v1/chat/completions", f"{ep}/v1/responses"]


def _extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            ch0 = choices[0]
            if isinstance(ch0, dict):
                msg = ch0.get("message")
                if isinstance(msg, dict):
                    content = msg.get("content")
                    if isinstance(content, str) and content.strip():
                        return content
                txt = ch0.get("text")
                if isinstance(txt, str) and txt.strip():
                    return txt
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        output = payload.get("output")
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    txt = part.get("text")
                    if isinstance(txt, str) and txt.strip():
                        chunks.append(txt)
            if chunks:
                return "\n".join(chunks)
        for key in ("answer", "result", "content", "text"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return ""


def _call_provider_api(
    *,
    provider_name: str,
    provider_cfg: dict[str, Any],
    prompt: str,
    objective: str,
) -> dict[str, Any]:
    provider = str(provider_cfg.get("provider", "api") or "api").lower()
    if provider not in {"api", "zhipu"}:
        return {"ok": False, "error": f"provider_not_supported:{provider_name}:{provider}"}
    if not bool(provider_cfg.get("enabled", True)):
        return {"ok": False, "error": f"provider_disabled:{provider_name}"}

    endpoint = str(provider_cfg.get("endpoint", "")).strip()
    model = str(provider_cfg.get("model", "")).strip()
    key_env = str(provider_cfg.get("key_env", "")).strip()
    api_key = str(os.environ.get(key_env, "")).strip() if key_env else ""
    if not api_key:
        api_key = str(provider_cfg.get("api_key", "")).strip()
    if not endpoint or not model:
        return {"ok": False, "error": f"provider_incomplete:{provider_name}"}
    if not api_key:
        return {"ok": False, "error": f"provider_key_missing:{provider_name}:{key_env or '-'}"}

    timeout = _coerce_timeout(provider_cfg.get("timeout_sec", 20), default=20.0)
    prompt_text = str(prompt or "").strip()
    objective_text = str(objective or "").strip()
    errors: list[str] = []

    for url in _candidate_urls(endpoint):
        started = time.perf_counter()
        is_responses = url.endswith("/responses") or "/responses?" in url
        if is_responses:
            payload = {
                "model": model,
                "input": prompt_text,
                "instructions": objective_text or "Provide concise structured guidance.",
            }
        else:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": objective_text or "Provide concise structured guidance."},
                    {"role": "user", "content": prompt_text},
                ],
                "temperature": 0.35,
            }

        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(url=url, data=raw, method="POST")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
                status = int(getattr(resp, "status", resp.getcode()))
                content_type = str(resp.headers.get("Content-Type", ""))
        except HTTPError as exc:
            err_text = ""
            try:
                err_text = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            errors.append(f"http_{int(getattr(exc, 'code', 0))}@{url}:{err_text[:160]}")
            continue
        except URLError as exc:
            errors.append(f"url_error@{url}:{exc}")
            continue
        except Exception as exc:
            errors.append(f"exception@{url}:{exc}")
            continue

        parsed: Any
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = text

        out_text = _extract_text(parsed).strip()
        low_text = str(out_text or text).lstrip().lower()
        if "text/html" in content_type.lower() or low_text.startswith("<!doctype html") or low_text.startswith("<html"):
            errors.append(f"html_response@{url}")
            continue
        if not out_text:
            out_text = str(text or "").strip()
        if not out_text:
            errors.append(f"empty_response@{url}")
            continue

        return {
            "ok": True,
            "provider": provider_name,
            "model": model,
            "status": status,
            "text": out_text,
            "raw": parsed if isinstance(parsed, dict) else {"raw_text": str(parsed)[:2000]},
            "url": url,
            "latency_ms": int(max(0.0, (time.perf_counter() - started) * 1000.0)),
        }

    return {"ok": False, "error": " ; ".join(errors)[:1200] or f"all_attempts_failed:{provider_name}"}


def generate_structured_response(
    *,
    group: str,
    prompt: str,
    objective: str,
    llm_config: dict[str, Any] | None = None,
    task_type: str = "",
) -> dict[str, Any]:
    text = str(prompt or "").strip()
    obj = str(objective or "").strip()
    summary = (obj or text)[:220]
    cfg = dict(llm_config or {})

    live_enabled = bool(cfg.get("api_live_enabled", False))
    if os.environ.get("PYTEST_CURRENT_TEST"):
        live_enabled = False

    errors: list[str] = []
    if live_enabled:
        groups = dict(cfg.get("provider_groups", {}) or {})
        providers = dict(cfg.get("providers", {}) or {})
        provider_seq = [str(x) for x in list(groups.get(str(group), []) or []) if str(x).strip()]
        for name in provider_seq:
            p_cfg = providers.get(name)
            if not isinstance(p_cfg, dict):
                errors.append(f"provider_not_found:{name}")
                continue
            called = _call_provider_api(provider_name=name, provider_cfg=p_cfg, prompt=text, objective=obj)
            if bool(called.get("ok", False)):
                generated = str(called.get("text", "")).strip()
                generated_summary = generated[:220] if generated else summary
                model = str(called.get("model", "-"))
                provider = str(called.get("provider", "-"))
                latency_ms = int(called.get("latency_ms", 0) or 0)
                est_cost = estimate_cost_usd(model=model, prompt_text=text, output_text=generated)
                return {
                    "group": str(group),
                    "generated_at": now_iso(),
                    "summary": generated_summary,
                    "next_step": f"Use {provider}({model}) to execute: {generated_summary[:120]}",
                    "raw": f"[{provider}:{model}] {generated[:1000]}",
                    "provider": provider,
                    "model": model,
                    "live_api": True,
                    "latency_ms": latency_ms,
                    "estimated_cost_usd": est_cost,
                    "task_type": str(task_type or ""),
                    "error": None,
                }
            errors.append(str(called.get("error", "provider_failed")))

    return {
        "group": str(group),
        "generated_at": now_iso(),
        "summary": summary,
        "next_step": f"Use {group} to execute: {summary[:120]}",
        "raw": f"[{group}] {text[:260]}",
        "provider": "fallback-local",
        "model": "-",
        "live_api": False,
        "latency_ms": 0,
        "estimated_cost_usd": 0.0,
        "task_type": str(task_type or ""),
        "error": "; ".join(errors)[:1000] if errors else None,
    }


def estimate_cost_usd(*, model: str, prompt_text: str, output_text: str) -> float:
    name = str(model or "").lower()
    tiers: list[tuple[str, float, float]] = [
        ("gpt-5.3-codex-xhigh", 0.015, 0.06),
        ("gpt-5.2-codex-high", 0.012, 0.05),
        ("claude-opus", 0.015, 0.075),
        ("deepseek", 0.002, 0.008),
        ("gemini", 0.0012, 0.004),
        ("glm-4.5", 0.0008, 0.002),
        ("glm-4", 0.0006, 0.0018),
        ("nano", 0.00015, 0.0006),
        ("qwen", 0.0004, 0.0012),
    ]
    in_rate = 0.0008
    out_rate = 0.0024
    for key, ir, orate in tiers:
        if key in name:
            in_rate = ir
            out_rate = orate
            break
    in_tokens = max(1.0, len(str(prompt_text or "")) / 4.0)
    out_tokens = max(1.0, len(str(output_text or "")) / 4.0)
    cost = (in_tokens / 1000.0) * in_rate + (out_tokens / 1000.0) * out_rate
    return float(round(cost, 6))
