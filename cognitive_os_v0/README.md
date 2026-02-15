# cognitive_os_v0

Minimal local-first Cognitive OS v0.1.

## Install

```powershell
cd cognitive_os_v0
python -m pip install -r requirements.txt
```

## Run

```powershell
python main.py --goal "Send a feature launch email to client"
```

Optional:

```powershell
python main.py --goal "Write meeting summary to local file" --auto-approve
```

## v0.1 Ops Commands

```powershell
# Gold hit-rate stats (prints table)
python stats_report.py

# Write stats JSON snapshot
python stats_report.py --write-json

# Replay latest 20 regression cases (plan-only, no tool execution)
python replay_regression.py --limit 20

# Replay and execute dummy tools
python replay_regression.py --limit 20 --execute --write-json
```

## v0.1 Scope (implemented)

- Single-shot structured output: intent + risk + draft + plan.
- Hard policy sandbox with allowlist and forced risk override.
- Human confirmation for L1/L2/L3 operations.
- Draft editing before execution.
- Gold calibration (`data/gold_tasks.json`) to check risk/tool/confirm quality.
- Append-only execution trace (`data/execution_trace.jsonl`).
- Regression capture (`data/regression_set.jsonl`) for blocked/failed/rejected/edited runs.
- Reflection memory loop (`data/reflections.jsonl`).

## Safety Notes

- `dummy_send_email` writes draft only to `data/outbox_drafts.jsonl` (never sends).
- File operations are restricted to `data/sandbox_files/`.
- Unknown tools are blocked by policy.

## Data Files

- `data/reflections.jsonl`: user-level reflection events.
- `data/execution_trace.jsonl`: step-level trace events.
- `data/regression_set.jsonl`: failure/edit regression samples.
- `data/gold_tasks.json`: local gold calibration tasks.
- `data/outbox_drafts.jsonl`: email drafts only (no external send).
