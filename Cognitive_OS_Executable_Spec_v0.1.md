# Cognitive OS Executable Spec v0.1

Status: Normative Draft  
Date: 2026-02-14  
Normative language: MUST, SHOULD, MAY

## 1. Scope

This spec defines mandatory runtime behavior for Cognitive OS v0.1:

- object contracts,
- risk policy,
- approval flow,
- execution trace,
- evaluation gate,
- reward update loop.

## 2. Runtime State Machine

Every request MUST flow through:

`RECEIVED -> PLANNED -> RISKED -> (APPROVAL_PENDING?) -> EXECUTED|BLOCKED -> TRACED -> EVALUATED -> REWARDED`

No direct `RECEIVED -> EXECUTED` transition is allowed.

## 3. Canonical Objects

All objects MUST include:

- `schema_version` (string)
- `id` (string)
- `ts` (ISO-8601 string)
- `source` (string)

### 3.1 Plan

Required fields:

- `goal` (string)
- `steps` (array of step objects)
- `assumptions` (array)
- `rollback_plan` (string)

Step object required fields:

- `step_id` (string)
- `action` (string)
- `tool` (string)
- `expected_output` (string)

### 3.2 RiskReport

Required fields:

- `risk_level` (`L0|L1|L2|L3`)
- `reasons` (array[string])
- `required_permission` (string)
- `requires_approval` (bool)
- `forbidden` (bool)

### 3.3 Approval

Required fields:

- `decision` (`approve|reject`)
- `approver` (string)
- `reason` (string)
- `scope` (array[string])

### 3.4 ExecTrace

Required fields:

- `trace_id` (string)
- `plan_id` (string)
- `risk_report_id` (string)
- `tool_calls` (array)
- `artifacts` (array)
- `status` (`success|failed|blocked|rolled_back`)

Tool call required fields:

- `tool` (string)
- `args_hash` (string)
- `started_ts` (string)
- `ended_ts` (string)
- `result_digest` (string)

### 3.5 EvalResult

Required fields:

- `suite` (string)
- `score` (number: 0..1)
- `pass` (bool)
- `regression` (bool)
- `findings` (array)

### 3.6 RewardUpdate

Required fields:

- `actor_id` (string)
- `rep_before` (number)
- `rep_after` (number)
- `delta` (number)
- `reason_codes` (array[string])

## 4. Risk Policy Matrix

### L0

- Examples: local draft formatting, read-only summarization.
- Approval: none.
- Execution: allowed.

### L1

- Examples: local file create/update in non-protected paths.
- Approval: optional single confirm.
- Execution: allowed with trace.

### L2

- Examples: external send, irreversible state mutation, sensitive data operations.
- Approval: mandatory single confirm (or dual mode if policy enabled).
- Execution: blocked without approval.

### L3

- Examples: destructive shell patterns, policy override, prohibited channels.
- Approval: not applicable.
- Execution: denied by default.

## 5. Default Safety Rules

Runtime MUST enforce:

1. No auto-send to external recipients by default.
2. No auto-delete/destructive shell by default.
3. Protected paths cannot be modified without policy exception.
4. Every L2 action MUST bind an `Approval` object before execution.
5. Every execution MUST emit `ExecTrace`.

## 6. Tool Governance

### 6.1 Allowlist

Only tools in configured allowlist MAY execute.

### 6.2 Least Privilege

Each tool call MUST declare minimal scope.

### 6.3 Sandbox

Execution SHOULD run in sandboxed mode whenever possible.

## 7. Evaluation Gate

Before publishing behavior changes:

1. Run required test suites.
2. Compare against regression set.
3. Fail closed if gate fails.

Minimum gate contract:

- `pass == true`
- `regression == false`
- `score >= gate_min_score`

## 8. Gold Calibration

Gold tasks MUST be mixed into evaluator flow.

Calibration requirements:

- Gold sampling ratio SHOULD be 5%-15%.
- Evaluator confidence without gold performance MUST NOT increase rep.
- Repeated gold mismatch MUST reduce evaluator influence.

## 9. Reward Engine Rules

Base formula (v0.1):

`rep_next = clamp(rep + alpha*correct - beta*incorrect - gamma*noise, 0, rep_cap)`

v0.1 defaults:

- `alpha = 1.0`
- `beta = 1.2`
- `gamma = 0.5`
- `rep_cap = 100`

Anti-abuse:

- duplicate voting cooldown,
- same-submission repeated voting suppression,
- anomalous burst penalty.

## 10. Event Persistence

All lifecycle transitions MUST emit append-only events.

Minimum event stream fields:

- `event_type`
- `entity_id`
- `prev_state`
- `next_state`
- `meta`

The system MUST support replay from events to reconstruct final state.

## 11. API Surface (v0.1 Minimal)

Required:

- `POST /plan`
- `POST /risk`
- `POST /approve`
- `POST /execute`
- `GET /trace/{id}`
- `POST /evaluate`
- `POST /reward/update`

Current panel/runtime APIs MAY be mapped to this contract incrementally.

## 12. Release Checklist (Hard Gate)

A release MUST be blocked if any item fails:

1. Schema version mismatch.
2. Risk matrix not loaded.
3. Approval flow bypass detected.
4. Missing execution trace.
5. Eval gate failed.
6. Regression suite failed.
7. Rollback path unavailable.

## 13. Implementation Roadmap

### Phase A (1-2 weeks)

- Freeze object schemas.
- Implement risk matrix as machine-readable policy.
- Emit complete `ExecTrace`.

### Phase B (2-4 weeks)

- Wire eval gate and regression blocking.
- Add gold calibration and rep updates.

### Phase C (4-6 weeks)

- Harden anti-abuse logic.
- Add approval queue UI and trace explorer.

## 14. Compliance Notes

- API keys MUST be injected via environment or secret manager.
- Secrets MUST NOT be stored in plain-text project docs or logs.
- Any exposed key MUST be rotated immediately.

