# MCP-to-Model Design v0.1

Date: 2026-02-15  
Scope: connect external MCP servers into Azi runtime through Web Panel APIs, with GitHub MCP as the first production path.

## 1. Design Goal

Build one stable path:

1. MCP tool call succeeds.
2. Result is injected into runtime events.
3. Brain loop can consume it in the next cycle.
4. The whole path is one command for daily use.

## 2. Existing Baseline (already in repo)

- `brain_web_panel.py` exposes:
  - `POST /api/mcp/list-tools`
  - `POST /api/mcp/call-tool`
  - `GET /api/mcp/connectors`
  - `POST /api/mcp/connectors/save|delete|sync-presets`
- Connector store: `mcp_connectors.json`
- GitHub demo runner: `mcp_github_demo.ps1`
- Task entry: `run.ps1 -Task mcp-github-demo`

## 3. Runtime Topology

1. User command:
   - `run.ps1 -Task mcp-github-demo`
2. Script calls Panel API:
   - list tools
   - pick repository search tool
   - call tool with `inject=true`
3. Panel writes MCP result into runtime event stream (`mcp_bridge` + injected text).
4. `brain_loop.py` reads new events from DB and reacts in normal cognition flow.

## 4. Connector Contract

For each MCP connector:

- `id`: stable machine id (e.g. `github-mcp`)
- `command` + `args`: executable server command
- `env`: only env placeholders, e.g. `${GITHUB_PERSONAL_ACCESS_TOKEN}`
- `timeout_sec`: hard timeout for init and requests

Security rule:

- Secrets must live in OS environment variables; do not hardcode API keys in JSON files.

## 5. Risk Controls

Hard controls for v0.1:

1. Missing token => fail fast before MCP start.
2. MCP call timeout => return explicit error, no silent retry storm.
3. Injection size cap (future patch) => truncate oversized output before event insert.
4. `run_once=true` default for MCP-triggered auto run.

## 6. Daily Operations

## 6.1 One-time setup

```powershell
[Environment]::SetEnvironmentVariable("GITHUB_PERSONAL_ACCESS_TOKEN","<YOUR_PAT>","User")
```

## 6.2 Start stack

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-start-lite
```

## 6.3 One-click MCP to model

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task mcp-github-demo
```

Optional one-off token:

```powershell
powershell -ExecutionPolicy Bypass -File .\mcp_github_demo.ps1 -GitHubToken "<PAT>" -Query "openclaw mcp" -PerPage 5
```

## 7. Acceptance Checklist (Done when all true)

- `GET /api/snapshot` is reachable.
- `POST /api/mcp/list-tools` returns at least 1 tool.
- `POST /api/mcp/call-tool` returns `ok=true`.
- Response includes `injected=true`.
- New MCP event appears in runtime state/history view.

## 8. Next Step (v0.2)

1. Add `mcp-doctor` command to auto check token + connector + list-tools.
2. Add output truncation/summarization before injection.
3. Add connector-level policy tags (`read_only`, `external_write`) and default deny for write-class tools.
