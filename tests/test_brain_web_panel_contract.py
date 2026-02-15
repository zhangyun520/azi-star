from __future__ import annotations

from pathlib import Path

from brain_web_panel import BrainWebApp
from azi_rebuild.runtime import connect_runtime_db


def test_web_api_contract_methods_keep_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "azi_rebuild.db"
    state_path = tmp_path / "azi_state.json"
    app = BrainWebApp(base_dir=tmp_path, db_path=db_path, state_path=state_path)

    # avoid spawning subprocesses during unit test
    app._spawn_once = lambda args: None  # type: ignore[method-assign]

    snap = app.snapshot()
    assert "updated_at" in snap
    assert "state" in snap
    assert "decision_text" in snap
    assert "trajectory" in snap
    assert "external" in snap
    assert "protocol" in snap
    assert "dispatch" in snap
    assert "guardrails" in snap
    assert "murmur" in snap
    assert "skill_specialist" in snap
    assert "skill_split" in snap
    assert "skills_router" in snap
    assert "orchestration" in snap
    assert "work_memory" in snap
    assert "narrative_bundle" in snap

    inj = app.inject("测试注入", run_once=True)
    assert bool(inj.get("ok", False))

    itr = app.iteration("测试迭代", trigger_update=True)
    assert bool(itr.get("ok", False))

    deep = app.force_deep()
    assert bool(deep.get("ok", False))

    dream = app.force_dream()
    assert bool(dream.get("ok", False))

    rp0 = app.get_routing_policy()
    assert bool(rp0.get("ok", False))
    assert "routing_policy" in rp0

    rp_saved = app.save_routing_policy(
        {
            "routing_policy": {
                "task_preferences": {
                    "coding": ["coder_chain", "deep_chain"],
                    "dream": ["deep_chain"],
                },
                "task_skill_packs": {
                    "dream": ["algorithmic-art", "imagegen"],
                },
                "work_memory_strength": "aggressive",
            }
        }
    )
    assert bool(rp_saved.get("ok", False))
    rp1 = app.get_routing_policy()
    assert bool(rp1.get("ok", False))
    policy = dict(rp1.get("routing_policy", {}) or {})
    prefs = dict(policy.get("task_preferences", {}) or {})
    packs = dict(policy.get("task_skill_packs", {}) or {})
    assert "coding" in prefs
    assert "dream" in packs
    assert str(policy.get("work_memory_strength", "")) == "aggressive"

    sp0 = app.get_skills_policy()
    assert bool(sp0.get("ok", False))
    assert "skills_policy" in sp0
    sp_saved = app.save_skills_policy(
        {
            "skills_policy": {
                "enabled_tiers": {"core": True, "experimental": False, "high_risk": False},
                "max_active": 24,
                "allowlist": {"core": ["playwright"], "experimental": [], "high_risk": []},
                "denylist": ["yeet"],
            }
        }
    )
    assert bool(sp_saved.get("ok", False))
    sp1 = app.get_skills_policy()
    assert bool(sp1.get("ok", False))
    saved_policy = dict(sp1.get("skills_policy", {}) or {})
    assert int(saved_policy.get("max_active", 0) or 0) == 24

    listed = app.list_connectors()
    assert "connectors" in listed

    saved = app.save_connector(
        {
            "name": "mock-llm",
            "endpoint": "https://example.local/v1/chat/completions",
            "method": "POST",
            "headers": {"Authorization": "Bearer ${MOCK_KEY}"},
            "body_template": {"messages": [{"role": "user", "content": "{{input}}"}]},
            "extract_path": "choices.0.message.content",
        }
    )
    assert bool(saved.get("ok", False))
    cid = str(saved.get("id", ""))
    assert bool(cid)

    app._call_remote = lambda **kwargs: {  # type: ignore[method-assign]
        "ok": True,
        "status": 200,
        "text": "{\"choices\":[{\"message\":{\"content\":\"bridge reply\"}}]}",
        "json": {"choices": [{"message": {"content": "bridge reply"}}]},
    }

    called = app.call_connector(
        {
            "connector_id": cid,
            "query": "请输出一句话",
            "run_once": True,
        }
    )
    assert bool(called.get("ok", False))
    assert "bridge reply" in str(called.get("extracted", ""))

    conn = connect_runtime_db(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT source, event_type, content
            FROM azi_events
            WHERE source LIKE 'api-bridge:%'
            ORDER BY id DESC
            LIMIT 2
            """
        ).fetchall()
        assert len(row) >= 1
    finally:
        conn.close()

    deleted = app.delete_connector(cid)
    assert bool(deleted.get("ok", False))
