from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import consciousness_report as consciousness_metrics


def _count_table(conn: Any, table_name: str) -> int:
    try:
        row = conn.execute(f"SELECT COUNT(1) AS c FROM {table_name}").fetchone()
        if row is None:
            return 0
        return int(row["c"] or 0)
    except Exception:
        return 0


def _tier_counts(conn: Any, table_name: str) -> dict[str, int]:
    out = {"hot": 0, "warm": 0, "cold": 0, "archive": 0}
    try:
        rows = conn.execute(
            f"""
            SELECT tier, COUNT(1) AS c
            FROM {table_name}
            GROUP BY tier
            """
        ).fetchall()
    except Exception:
        return out
    for row in rows:
        tier = str(row["tier"] or "").strip().lower()
        if tier in out:
            out[tier] = int(row["c"] or 0)
    return out


def collect_memory_status(conn: Any) -> dict[str, Any]:
    return {
        "facts": _count_table(conn, "azi_fact_memory"),
        "conflicts": _count_table(conn, "azi_fact_conflicts"),
        "vectors": _count_table(conn, "azi_memory_vectors"),
        "source_trust": _count_table(conn, "azi_source_trust"),
        "causal_edges": _count_table(conn, "azi_causal_edges"),
        "fact_tiers": _tier_counts(conn, "azi_fact_memory"),
        "vector_tiers": _tier_counts(conn, "azi_memory_vectors"),
    }


def _safe_line_count(path: Path, *, max_bytes: int = 16 * 1024 * 1024) -> int:
    try:
        if not path.exists() or not path.is_file():
            return 0
        size = int(path.stat().st_size)
        if size <= 0:
            return 0
        if size > int(max_bytes):
            return -1
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _safe_json_list_len(path: Path) -> int:
    try:
        if not path.exists() or not path.is_file():
            return 0
        raw = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
        if isinstance(raw, list):
            return len(raw)
    except Exception:
        pass
    return 0


def _safe_json_read(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(default or {})
    try:
        if not path.exists() or not path.is_file():
            return base
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
        if isinstance(data, dict):
            base.update(data)
    except Exception:
        pass
    return base


def _file_has_tokens(path: Path, tokens: list[str]) -> bool:
    try:
        if not path.exists() or not path.is_file():
            return False
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return all(str(tok) in text for tok in tokens)


def collect_cognitive_v0_status(base_dir: Path) -> dict[str, Any]:
    v0 = base_dir / "cognitive_os_v0"
    schemas = v0 / "core" / "schemas.py"
    main_py = v0 / "main.py"
    data = v0 / "data"

    reflections = data / "reflections.jsonl"
    exec_trace = data / "execution_trace.jsonl"
    gold_tasks = data / "gold_tasks.json"
    regression = data / "regression_set.jsonl"
    stats_json = data / "stats.json"
    replay_report = data / "replay_report.json"

    structured_ok = _file_has_tokens(
        schemas,
        ["intent_analysis", "risk", "draft_content", "plan", "requires_confirmation"],
    )
    sandbox_ok = _file_has_tokens(
        main_py,
        ["enforce_plan", "Prompt.ask", "edit_diff", "requires_confirmation"],
    )

    stats_payload = _safe_json_read(stats_json, {})
    replay_payload = _safe_json_read(replay_report, {})

    return {
        "structured_output": {"enabled": structured_ok, "file": str(schemas.relative_to(base_dir))},
        "sandbox_confirm_edit": {"enabled": sandbox_ok, "file": str(main_py.relative_to(base_dir))},
        "reflections": {"file": str(reflections.relative_to(base_dir)), "records": _safe_line_count(reflections)},
        "execution_trace": {"file": str(exec_trace.relative_to(base_dir)), "records": _safe_line_count(exec_trace)},
        "gold_tasks": {"file": str(gold_tasks.relative_to(base_dir)), "count": _safe_json_list_len(gold_tasks)},
        "regression_set": {"file": str(regression.relative_to(base_dir)), "records": _safe_line_count(regression)},
        "stats": {
            "file": str(stats_json.relative_to(base_dir)),
            "gold_hit_rate": stats_payload.get("gold_hit_rate", "-"),
            "total_runs": stats_payload.get("total_runs", "-"),
        },
        "replay_report": {
            "file": str(replay_report.relative_to(base_dir)),
            "total": replay_payload.get("total", "-"),
            "resolved": replay_payload.get("resolved", "-"),
        },
        "commands": {
            "stats": "python stats_report.py",
            "replay": "python replay_regression.py --limit 20",
        },
    }


def collect_consciousness_status(conn: Any, db_path: Path) -> dict[str, Any]:
    try:
        return consciousness_metrics.make_report(conn, db_path)
    except Exception as exc:
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "db_path": str(db_path),
            "metrics": {},
            "CRS": 0.0,
            "band": "error",
            "evidence": {},
            "error": str(exc)[:240],
        }


_SKILL_POLICY_FILE = "skill_router_policy.json"
_SKILL_TIERS = ("core", "experimental", "high_risk")


def _dedup_lower(items: list[Any], *, limit: int = 300) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in list(items or []):
        key = str(raw or "").strip().lower()
        if not key or key in seen:
            continue
        out.append(key)
        seen.add(key)
        if len(out) >= int(limit):
            break
    return out


def _default_skill_policy() -> dict[str, Any]:
    return {
        "enabled_tiers": {"core": True, "experimental": False, "high_risk": False},
        "max_active": 48,
        "allowlist": {"core": [], "experimental": [], "high_risk": []},
        "denylist": [],
    }


def normalize_skill_router_policy(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    base = _default_skill_policy()

    enabled_raw = raw.get("enabled_tiers", {})
    enabled = dict(base["enabled_tiers"])
    if isinstance(enabled_raw, dict):
        for tier in _SKILL_TIERS:
            if tier in enabled_raw:
                enabled[tier] = bool(enabled_raw.get(tier))

    max_active_raw = raw.get("max_active", base["max_active"])
    try:
        max_active = int(max_active_raw)
    except Exception:
        max_active = int(base["max_active"])
    max_active = max(6, min(max_active, 500))

    allow_raw = raw.get("allowlist", {})
    allow = dict(base["allowlist"])
    if isinstance(allow_raw, dict):
        for tier in _SKILL_TIERS:
            tier_vals = allow_raw.get(tier, [])
            if isinstance(tier_vals, str):
                tier_items = [x.strip() for x in tier_vals.split(",") if x.strip()]
            elif isinstance(tier_vals, list):
                tier_items = list(tier_vals)
            else:
                tier_items = []
            allow[tier] = _dedup_lower(tier_items, limit=240)

    deny_raw = raw.get("denylist", [])
    if isinstance(deny_raw, str):
        deny_items = [x.strip() for x in deny_raw.split(",") if x.strip()]
    elif isinstance(deny_raw, list):
        deny_items = list(deny_raw)
    else:
        deny_items = []
    deny = _dedup_lower(deny_items, limit=480)

    return {
        "enabled_tiers": enabled,
        "max_active": max_active,
        "allowlist": allow,
        "denylist": deny,
    }


def _skills_root() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return codex_home / "skills"


def _list_installed_skills() -> list[str]:
    root = _skills_root()
    if not root.exists() or not root.is_dir():
        return []
    names = [p.name for p in root.iterdir() if p.is_dir() and p.name != ".system"]
    return sorted(_dedup_lower(names, limit=3000))


def _classify_skill_tier(name: str) -> str:
    n = str(name or "").strip().lower()
    high_risk_tokens = (
        "deploy",
        "security",
        "secops",
        "secrets",
        "credential",
        "aws",
        "cloudflare",
        "netlify",
        "vercel",
        "render",
        "sentry",
        "regulatory",
        "gdpr",
        "fda",
        "iso",
        "mdr",
        "tenant-manager",
    )
    experimental_tokens = (
        "art",
        "music",
        "gif",
        "logo",
        "waffles",
        "bluesky",
        "spotify",
        "sora",
        "imagegen",
        "theme",
        "canvas",
        "algorithmic",
        "generative",
    )
    if any(tok in n for tok in high_risk_tokens):
        return "high_risk"
    if any(tok in n for tok in experimental_tokens):
        return "experimental"
    return "core"


def _apply_skill_policy(policy: dict[str, Any], installed: list[str]) -> dict[str, Any]:
    p = normalize_skill_router_policy(policy)
    enabled = dict(p.get("enabled_tiers", {}))
    allow = dict(p.get("allowlist", {}))
    deny = set(_dedup_lower(list(p.get("denylist", []) or []), limit=600))
    max_active = int(p.get("max_active", 48) or 48)

    tier_counts = {"core": 0, "experimental": 0, "high_risk": 0}
    active_by_tier: dict[str, list[str]] = {"core": [], "experimental": [], "high_risk": []}
    active: list[str] = []
    muted: list[str] = []

    for name in installed:
        tier = _classify_skill_tier(name)
        tier_counts[tier] = int(tier_counts.get(tier, 0)) + 1
        if name in deny:
            muted.append(name)
            continue
        if not bool(enabled.get(tier, False)):
            muted.append(name)
            continue
        tier_allow = _dedup_lower(list(allow.get(tier, []) or []), limit=320)
        if tier_allow and name not in set(tier_allow):
            muted.append(name)
            continue
        active_by_tier[tier].append(name)
        active.append(name)

    active = active[:max_active]
    active_set = set(active)
    active_by_tier = {
        tier: [x for x in list(active_by_tier.get(tier, [])) if x in active_set]
        for tier in _SKILL_TIERS
    }

    return {
        "policy": p,
        "installed_total": len(installed),
        "tier_counts": tier_counts,
        "active_total": len(active),
        "active_skills": active,
        "active_by_tier": active_by_tier,
        "muted_total": max(0, len(installed) - len(active)),
    }


def _skill_policy_path(base_dir: Path) -> Path:
    return Path(base_dir) / _SKILL_POLICY_FILE


def load_skill_router_policy(base_dir: Path) -> dict[str, Any]:
    path = _skill_policy_path(base_dir)
    if not path.exists() or not path.is_file():
        return normalize_skill_router_policy({})
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
    except Exception:
        return normalize_skill_router_policy({})
    if not isinstance(data, dict):
        return normalize_skill_router_policy({})
    return normalize_skill_router_policy(data)


def save_skill_router_policy(base_dir: Path, payload: dict[str, Any] | None) -> dict[str, Any]:
    policy = normalize_skill_router_policy(payload if isinstance(payload, dict) else {})
    path = _skill_policy_path(base_dir)
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    return policy


def collect_skills_router_status(base_dir: Path) -> dict[str, Any]:
    installed = _list_installed_skills()
    policy = load_skill_router_policy(base_dir)
    applied = _apply_skill_policy(policy, installed)
    return {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "policy_file": str(_skill_policy_path(base_dir).relative_to(base_dir)),
        "installed_total": int(applied.get("installed_total", 0)),
        "active_total": int(applied.get("active_total", 0)),
        "muted_total": int(applied.get("muted_total", 0)),
        "tier_counts": dict(applied.get("tier_counts", {}) or {}),
        "active_by_tier": dict(applied.get("active_by_tier", {}) or {}),
        "active_skills": list(applied.get("active_skills", []) or []),
        "policy": dict(applied.get("policy", {}) or {}),
    }


__all__ = [
    "collect_memory_status",
    "collect_cognitive_v0_status",
    "collect_consciousness_status",
    "collect_skills_router_status",
    "load_skill_router_policy",
    "save_skill_router_policy",
    "normalize_skill_router_policy",
]
