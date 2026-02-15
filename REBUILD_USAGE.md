# Azi Rebuild (Clean Core)

This rebuild replaces the previous complex runtime while keeping the same Web API contract:

- `GET /api/snapshot`
- `GET /api/connectors`
- `POST /api/inject`
- `POST /api/iteration`
- `POST /api/force-deep`
- `POST /api/force-dream`
- `POST /api/connectors/save`
- `POST /api/connectors/delete`
- `POST /api/connector-call`

## Default files

- DB: `azi_rebuild.db`
- State: `azi_state.json`

## Legacy archive

- Archived at: `legacy/cleanup_2026-02-14/`
- Moved file list: `legacy/cleanup_2026-02-14/moved_files.txt`
- This cleanup is non-destructive (moved, not deleted).

## One-click start

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-start
```

`stack-start` includes:

- brain loop
- deep worker
- health checker
- web probe
- file feed
- vscode observer
- social bridge
- shallow thinker
- device capture server
- web panel (`http://127.0.0.1:8798`)

## Lite start

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-start-lite
```

Lite mode only starts brain/deep/health/web panel.

## Status / Stop

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-status
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-stop
```

## Single-run

```powershell
python brain_loop.py --db azi_rebuild.db --state azi_state.json --once
python deep_coder_worker.py --db azi_rebuild.db --state azi_state.json --once
python brain_loop.py --db azi_rebuild.db --state azi_state.json --once --force-dream
python deep_coder_worker.py --db azi_rebuild.db --state azi_state.json --once --force-dream
python health_check.py --db azi_rebuild.db --config health_check_config.json --once --auto-restart
python brain_web_panel.py --db azi_rebuild.db --state azi_state.json --host 127.0.0.1 --port 8798
```

## Task list

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task help
```

## API Bridge (Panel)

Web panel now supports direct external API bridge:

- save connector profile (`name / endpoint / method / headers / body_template / extract_path`)
- call external LLM or data API
- inject extracted response back to `azi_events` (`event_type=input`, source=`api-bridge:*`)

`body_template` supports:

- `{{input}}` -> runtime query text
- `${ENV_VAR}` -> environment variable substitution

## MCP Quick Path (GitHub)

Design doc: `MCP_TO_MODEL_DESIGN_v0.1.md`

```powershell
# 1) set token once
[Environment]::SetEnvironmentVariable("GITHUB_PERSONAL_ACCESS_TOKEN","<YOUR_PAT>","User")

# 2) start core stack
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-start-lite

# 3) run one-click MCP search + inject
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task mcp-github-demo
```

## Consciousness Metrics

```powershell
# terminal report
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task conscious-report

# write json report
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task conscious-report-json
```
