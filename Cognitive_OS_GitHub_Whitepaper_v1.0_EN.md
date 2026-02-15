# Azi Cognitive OS (阿紫) GitHub Whitepaper v1.0 (EN)

> Date: 2026-02-15  
> Status: Implemented Core + Scalable Roadmap  
> Positioning: Evaluable, evolvable, safe-by-default AI orchestration infrastructure

## 1. Executive Summary

Azi Cognitive OS is not "just another assistant."  
It is a judgment-and-execution operating layer that makes AI workflows controllable under real-world constraints.

Central hub identity:

- Name: `Azi` (`阿紫`)
- Role: cognitive dispatch center (not direct executor)

Core loop:

`Input Events -> Risk Classification -> Dispatch Plan -> Execute/Replay -> Trace -> Memory Update -> Metrics`

Current implementation already includes:

- Fast/slow dual-path runtime.
- Structured dispatch contract with explicit rollback path.
- Hard safety gates and approval boundaries.
- Fact/conflict/vector memory with trust and causal links.
- Web panel + API bridge + MCP bridge.
- One-click stack startup for local operation.

---

## 2. System Framework (Implemented)

## 2.1 Layered Architecture

```text
Interaction Layer (Web Panel / CLI / run.ps1)
    ->
Cognitive Orchestration Layer (brain loop)
    ->
Deep Execution Layer (deep + dream worker)
    ->
Memory & Governance Layer
    ->
Connector Layer (API + MCP)
```

## 2.2 Two Complementary Cores

This repository currently keeps two compatible cores:

- `azi_rebuild`: persistent multi-process orchestration runtime (main path).
- `cognitive_os_v0`: minimal safety-first loop for strict validation and replay.

Engineering rationale: keep advanced runtime evolving, while keeping a minimal verifiable baseline.

## 2.3 Thought Experiment Scope

Besides product goals, Azi also supports a research thought experiment:

- whether consciousness-like behavior can emerge from constrained cognitive loops,
- whether that emergence can persist under long-running information pressure,
- whether stability/continuity can be tracked through measurable indicators.

This remains an engineering hypothesis, not a claim of proven subjective consciousness.

---

## 3. Feature Matrix (What Exists Now)

## 3.1 Runtime and Orchestration

- `run.ps1` provides `stack-start`, `stack-start-lite`, `stack-stop`, `stack-status`, `stack-restart`.
- Full stack can launch:
  - brain loop
  - deep worker
  - health checker
  - web probe / file feed / vscode observer / social bridge / shallow thinker / device capture
  - web panel at `http://127.0.0.1:8798`

## 3.2 Dispatch-Centric Cognitive Hub

Dispatch output is formalized as a contract (`DispatchPlan`) including:

- `intent`
- `task_type` (`shallow/deep/dream/coding/ops`)
- `risk_level` (`L0-L3`)
- `dispatch_plan` (worker/model/tool/input/expected_output/timeout/reversible)
- `recommended_skills`
- `success_criteria`
- `rollback_plan`

Issue-detection logic is integrated to distinguish actionable tasks from non-executable chatter.

## 3.3 Deep Reflection and Dream Replay

- Triggered by events or manually from panel:
  - `deep_request`
  - `dream_request`
- Dream replay compresses historical fragments into actionable insight.
- Deep path includes safe publish chain:
  - `sandbox -> eval -> canary -> rollback`

## 3.4 Memory Substrate

SQLite-backed memory structures:

- `azi_fact_memory`
- `azi_fact_conflicts`
- `azi_memory_vectors`
- `azi_source_trust`
- `azi_causal_edges`

Implemented behaviors:

- Fact-first + vector-hybrid retrieval.
- Lifecycle tiering (hot/warm/cold/archive, short/mid/long/crystal).
- Conflict-aware confidence and trust updates.

## 3.5 Governance and Safety

- Risk gate (`L0-L3`).
- Approval override for high-risk actions.
- Immutable guard (protected path checks).
- Emergence guard (loop-like behavior warning).
- Eval gate for deep publish (fail closed).
- End-to-end traceability and replayable state transitions.

## 3.6 Web Panel and External Integration

Web panel currently supports:

- Live snapshot (state, trajectory, protocol flow, guardrails, murmur, deep/dream, dispatch).
- Force deep / force dream actions.
- API connector CRUD + call + event injection.
- MCP connector CRUD + list-tools + call-tool + event injection.
- Awesome MCP preset sync.
- Routing policy and skills policy editor.
- CRS top status lamp (green/yellow/red) + trend line.

## 3.7 Model Routing and Skill Packs

- Provider groups: `shallow_chain`, `medium_chain`, `deep_chain`, `dream_chain`, `coder_chain`.
- Task-type routing with success/latency/cost scoring.
- Work-memory biased routing from historical outcomes.
- Dedicated dream skill-pack integrated into routing policy.

## 3.8 Minimal v0 Loop (`cognitive_os_v0`)

Implemented minimal contract and local loop:

- Single structured output: `intent + risk + draft + plan`.
- Hard policy sandbox.
- Human confirmation.
- Editable draft before execution.
- Reflection log: `reflections.jsonl`.
- Execution audit: `execution_trace.jsonl`.
- Gold calibration: `gold_tasks.json`.
- Regression set: `regression_set.jsonl`.
- Ops commands:
  - `python stats_report.py`
  - `python replay_regression.py --limit 20`

---

## 4. Current Quantitative Snapshot

From `resident_output/consciousness_report.json` (2026-02-15):

- `CRS = 0.752` (`reflective-candidate`)
- `MCS = 0.792`
- `SCR = 0.9928`
- `GAR = 1.0`
- `RLY = 0.4592`

Interpretation: controllability, safety compliance, and memory coherence are strong; next bottleneck is reflective yield density and MCP activity utilization.

---

## 5. Outlook and Roadmap

## 5.1 Near-Term Engineering Priorities

1. Improve actionable issue recognition accuracy.
2. Increase dispatch hit rate by task-model-tool matching.
3. Promote deep/dream outcomes into reusable skill drafts.
4. Strengthen MCP policy classes (`read_only`, `external_write`) and audit depth.
5. Tie regression replay tighter to release gate decisions.

## 5.2 Long-Term Platform Direction

1. From a single orchestrator to composable cognitive infrastructure.
2. From manual model selection to automatic workload-model-tool co-optimization.
3. From logging memory to policy-level transferable experience.

---

## 6. Boundaries and Non-Goals

This system does not claim:

- unconstrained autonomous execution,
- bypassing approval for high-risk actions,
- philosophical proof of subjective consciousness.

It does claim an engineering target: stable, auditable, explainable, and improving cognitive control.

---

## 7. Suggested GitHub Doc Order

1. `README.md`
2. `Cognitive_OS_GitHub_Whitepaper_v1.0.md`
3. `Cognitive_OS_GitHub_Whitepaper_v1.0_EN.md`
4. `Cognitive_OS_Executable_Spec_v0.1.md`
5. `Consciousness_Spec_v0.1.md`
6. `REBUILD_USAGE.md`

Cross-links:

- Chinese whitepaper: `Cognitive_OS_GitHub_Whitepaper_v1.0.md`
- English whitepaper: `Cognitive_OS_GitHub_Whitepaper_v1.0_EN.md`

Recommended startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-start
```

Minimal verification:

```powershell
python .\consciousness_report.py --db .\azi_rebuild.db
python .\cognitive_os_v0\stats_report.py
python .\cognitive_os_v0\replay_regression.py --limit 20
```

---

## 8. Conclusion

The project has already moved beyond "LLM script glue" into an operational cognitive infrastructure prototype.

The next phase is not feature expansion for its own sake.  
It is continuous gain on:

- issue recognition precision,
- dispatch success density,
- safe reflective learning yield.
