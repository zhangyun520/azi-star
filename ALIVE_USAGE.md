# Alive-ish MVP Usage

## 1) Run simulation

```bash
python alive_ai_mvp.py --steps 30 --seed 13 --scenario noisy --learner bandit --log-prefix alive_weighted_run
```

## 2) Tune reward weights

```bash
python alive_ai_mvp.py --steps 30 --seed 13 --scenario noisy --learner bandit \
  --reward-budget-w 1.0 \
  --reward-error-w 2.8 \
  --reward-uncertainty-w 2.2 \
  --reward-success-bonus 1.0 \
  --reward-failure-penalty 1.4 \
  --reward-rollback-penalty 0.8 \
  --log-prefix alive_weighted_run
```

## 3) Compare scenarios

```bash
python alive_ai_mvp.py --steps 20 --seed 11 --compare --learner bandit --log-prefix alive_compare_weighted
```

## 4) Unified plotting

### Trajectory

```bash
python alive_plot.py trajectory --input alive_weighted_run.csv --scenario noisy --output alive_weighted_run.png
```

### Compare

```bash
python alive_plot.py compare --input alive_compare_weighted.csv --output alive_compare_weighted.png
```

## 5) Backward-compatible wrappers

```bash
python plot_logs.py --input alive_weighted_run.csv --scenario noisy --output alive_weighted_run_wrapper.png
python plot_compare.py --input alive_compare_weighted.csv --output alive_compare_wrapper.png
```

## 6) Reward sweep (grid search)

```bash
python sweep_rewards.py --steps 40 --seed 13 --scenario noisy --learner bandit --out-prefix reward_sweep
```

Default 3x3 grid:
- `reward_error_w`: `1.6,2.4,3.2`
- `reward_uncertainty_w`: `1.0,1.8,2.6`

Outputs:
- `reward_sweep.csv`
- `reward_sweep.json`

## 7) One-command runner (PowerShell)

```powershell
.\run.ps1 -Task help
.\run.ps1 -Task weighted
.\run.ps1 -Task compare
.\run.ps1 -Task plot-trajectory
.\run.ps1 -Task plot-compare
.\run.ps1 -Task sweep
.\run.ps1 -Task all
```

## 8) Resident mode (desktop double-click)

Desktop launchers:
- `d:\Users\Desktop\Start_Resident_Model.bat`
- `d:\Users\Desktop\Stop_Resident_Model.bat`

Core control script:
- `resident_control.ps1`

Manual controls:

```powershell
powershell -ExecutionPolicy Bypass -File .\resident_control.ps1 -Action start
powershell -ExecutionPolicy Bypass -File .\resident_control.ps1 -Action status
powershell -ExecutionPolicy Bypass -File .\resident_control.ps1 -Action stop
powershell -ExecutionPolicy Bypass -File .\resident_control.ps1 -Action run-once
```

Resident outputs:
- `resident_output\latest_single.csv/json/png`
- `resident_output\latest_compare.csv/json/png`
- `resident_output\latest_summary.json`
- `resident_output\archive\...` (timestamped history)

Resident auto-open mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\resident_control.ps1 -Action start-open
powershell -ExecutionPolicy Bypass -File .\resident_control.ps1 -Action run-once -OpenLatest
```

Alert thresholds (resident_live.py):

```powershell
python resident_live.py --once --output-dir resident_output --scenario noisy --learner bandit --alert-budget-min 80 --alert-stress-max 0.2 --alert-success-min 0.85
```

Alert files:
- `resident_output\ALERT.txt`
- `resident_output\latest_alert.json`
- `resident_output\alert_history.log`

## 9) 10D memory + web perception (phase 1)

### Start/stop memory server

```powershell
powershell -ExecutionPolicy Bypass -File .\memory_control.ps1 -Action start
powershell -ExecutionPolicy Bypass -File .\memory_control.ps1 -Action status
powershell -ExecutionPolicy Bypass -File .\memory_control.ps1 -Action stop
```

### Ingest one event manually

```powershell
python memory_ingest_cli.py --source manual --url "https://example.com" --title "observer and consensus" --content "curvature gauge geodesic lyapunov observer natural transformation consensus 10D" --tags "10d,observer,consensus" --valence 0.2 --arousal 0.5 --uncertainty 0.4 --control 0.6
```

### Chat over memory

```powershell
python memory_chat.py --show-recent --show-dims --query "What is my current 10D focus?"
```

### Quick demo (one command)

```powershell
.\run.ps1 -Task memory-demo
```

### Browser snippet ingestion

1. Start memory server.
2. Open `browser_event_snippet.js`.
3. Paste into DevTools Console on the current webpage.
4. It will POST page context to `http://127.0.0.1:8790/event`.

### Data files

- `ten_d_memory.db`
- `memory_server.pid`

### Desktop launchers

- `d:\Users\Desktop\Start_10D_Memory_Server.bat`
- `d:\Users\Desktop\Stop_10D_Memory_Server.bat`

## 10) Desktop opinion window

Open directly from PowerShell:

```powershell
.\run.ps1 -Task opinion-window
```

Or double-click desktop launcher:
- `d:\Users\Desktop\Open_10D_Opinion_Window.bat`

Window capabilities:
- Auto-express current opinion from recent 10D memory
- Manual refresh (`Refresh Opinion`)
- Ask memory questions (`Ask Memory`)
- Export current snapshot (`Export Snapshot`)

Opinion window upgrades:
- TTS: click `Speak Now` or enable `Auto TTS`
- Timeline: right-side list keeps recent opinion snapshots (`opinion_history.jsonl`)
- Click a timeline item to replay that opinion in the main panel
- Self loop: click `Write Back` in opinion window to persist current opinion as a new `self-opinion` memory event.
Self-feeling layer added in opinion window:
- editable Self Profile: name/mission/boundary/style
- continuity index shown live
- each refresh records a reflection in table `self_reflections`
- write-back guard now checks cooldown + continuity threshold

## 11) LLM automatic enrichment (Ollama/API)

Config files:
- `llm_config.json` (model router)
- `llm_state.json` (processing cursor, auto-generated)
- `llm_control.ps1` (start/stop/status/run-once)

Quick start:
```powershell
.\run.ps1 -Task llm-start
.\run.ps1 -Task llm-status
.\run.ps1 -Task llm-once
```

Stop:
```powershell
.\run.ps1 -Task llm-stop
```

Hot-plug multi-provider routing:
- Configure provider instances in `llm_config.json` -> `providers`
- Configure chains in `llm_config.json` -> `provider_groups`
- Bind chains to brain routes with:
  - `brain.fast_provider_group`
  - `brain.deep_provider_group`
  - `brain.coder_provider_group`

Example:
```json
{
  "providers": {
    "openai_main": {"provider":"api","endpoint":"https://api.openai.com/v1","model":"gpt-4.1-mini","key_env":"OPENAI_API_KEY"},
    "zhipu_glm": {"provider":"zhipu","endpoint":"https://open.bigmodel.cn/api/paas/v4","model":"glm-4-flash","key_env":"ZHIPU_API_KEY"},
    "ollama_qwen": {"provider":"ollama","host":"http://127.0.0.1:11434","model":"qwen3:8b"}
  },
  "provider_groups": {
    "fast_chain": ["openai_main","zhipu_glm","ollama_qwen"]
  },
  "brain": {
    "fast_provider_group": "fast_chain"
  }
}
```

Behavior:
- Router tries providers in chain order.
- On failure, auto-fallback to next provider.
- You can also pass ad-hoc chains (comma string): `"provider": "openai_main,zhipu_glm,ollama_qwen"`.

## 12) Brain-like continuous loop

Start / status / stop:
```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task brain-start
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task brain-status
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task brain-stop
```

Run one cycle:
```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task brain-once
```

State files:
- `brain_state.json`
- `resident_output\brain_drift_alert.txt`

## 13) Authorized personal-device content capture

Policy file:
- `device_capture_policy.json`

## 14) Replay dashboard: Excel offline + market quote API

### A. No external API: local Excel mode

Default local file:
- `replay_data\local_market.xlsx`

Run with Excel source:

```powershell
python replay_mvp.py --data-source excel --excel-file replay_data/local_market.xlsx
```

Excel format:
- `symbols` sheet (required): `code,name,market,last,anchor_low,structure_score,monthly_turnover_recent,monthly_turnover_left_peak,ma55,ma120,ma55_prev,ma120_prev,history`
- `history` is comma-separated close series (for sparkline/chart)
- `charts` sheet (optional): `name,series` (comma-separated values)

Template files:
- `replay_data\local_market.xlsx`
- `replay_data\local_market_template.csv`

### B. With market API: quote interface

HTTP endpoint:

```text
GET /api/market/quote?symbol=300308&market=A-share&source=auto
```

Options:
- `source=auto` (default): try `itick`, then `akshare`, then `eastmoney`
- `source=itick`
- `source=akshare`
- `source=eastmoney`

AKShare startup mode:

```powershell
python replay_mvp.py --data-source akshare
powershell -ExecutionPolicy Bypass -File .\open_replay_dashboard.ps1 -DataSource akshare
```

Current AKShare bindings in replay:
- Quote API (`/api/market/quote?source=akshare`): `stock_bid_ask_em` (A), `stock_hk_daily` (HK), `stock_us_daily` (US)
- Replay task `akshare`: updates `symbols` prices and syncs `limit_ladder`, `anomaly_pool`, `overnight_news`
- Data blocks: `stock_zt_pool_em` (涨停池), `stock_changes_em` (异动池), `stock_info_global_em` (资讯)
- Probe script: `python akshare_probe.py --date 20260213`

Server:
```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task device-start
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task device-status
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task device-stop
```

API:
- `POST http://127.0.0.1:8791/capture`
- `GET  http://127.0.0.1:8791/health`
- `GET  http://127.0.0.1:8791/policy` (tokens hidden)

Body example:
```json
{
  "device_id": "my-phone",
  "url": "https://example.com/video",
  "title": "sample title",
  "content": "raw page/app text ...",
  "tags": ["mobile", "video"],
  "feeling": {"valence": 0.1, "arousal": 0.5, "uncertainty": 0.3, "control": 0.6},
  "meta": {"app": "browser"}
}
```

Auth header:
- `Authorization: Bearer <device token>`

Notes:
- Only devices in policy are accepted.
- Content is redacted before storing.
- Audit log: `resident_output\device_capture_audit.log`

## 14) HF training hook (attention entropy regularization)

New modules:
- `attention_entropy.py` (entropy stats + floor regularizer)
- `hf_entropy_hook.py` (patch HF `Trainer.compute_loss`)

Quick integration:

```python
from transformers import Trainer
from hf_entropy_hook import EntropyHookConfig, EntropyStatsCallback, enable_entropy_hook_on_trainer

trainer = Trainer(...)
cfg = EntropyHookConfig(
    enabled=True,
    lambda_weight=0.02,
    target_high=0.72,
    target_low=0.38,
)
enable_entropy_hook_on_trainer(trainer, cfg)
trainer.add_callback(EntropyStatsCallback())
trainer.train()
```

Logs include:
- `attn_entropy_loss`
- `attn_entropy_norm_mean`
- `attn_entropy_norm_p10`
