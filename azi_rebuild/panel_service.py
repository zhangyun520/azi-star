from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from azi_rebuild.panel_connectors import (
    DEFAULT_MCP_CONNECTORS,
    MCPStdioClient,
    _all_mcp_preset_connectors,
    _extract_response_text,
    _join_mcp_content,
    _normalize_connector_payload,
    _normalize_mcp_connector_payload,
    _read_json,
    _resolve_placeholders,
    _write_json,
)
from azi_rebuild.runtime import connect_runtime_db, enqueue_event


class PanelConnectorService:
    def __init__(self, base_dir: Path, db_path: Path, state_path: Path) -> None:
        self.base_dir = base_dir
        self.db_path = db_path
        self.state_path = state_path

    def _connector_file(self) -> Path:
        return self.base_dir / "api_connectors.json"

    def _connector_store(self) -> dict[str, Any]:
        raw = _read_json(self._connector_file(), {"connectors": []})
        items = raw.get("connectors", [])
        if not isinstance(items, list):
            items = []
        return {"connectors": [x for x in items if isinstance(x, dict)]}

    def _save_connector_store(self, store: dict[str, Any]) -> None:
        _write_json(self._connector_file(), {"connectors": list(store.get("connectors", []) or [])})

    def list_connectors(self) -> dict[str, Any]:
        return self._connector_store()

    def save_connector(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = _normalize_connector_payload(payload)
        if not item.get("name"):
            return {"ok": False, "message": "连接器名称必填"}
        if not item.get("endpoint"):
            return {"ok": False, "message": "连接器 Endpoint 必填"}

        store = self._connector_store()
        items = list(store.get("connectors", []) or [])
        out: list[dict[str, Any]] = []
        replaced = False
        for row in items:
            if str(row.get("id", "")) == str(item.get("id", "")):
                out.append(item)
                replaced = True
            else:
                out.append(row)
        if not replaced:
            out.append(item)
        store["connectors"] = out
        self._save_connector_store(store)
        return {"ok": True, "id": item["id"], "saved": True}

    def delete_connector(self, connector_id: str) -> dict[str, Any]:
        cid = str(connector_id or "").strip()
        if not cid:
            return {"ok": False, "message": "连接器 ID 必填"}
        store = self._connector_store()
        items = list(store.get("connectors", []) or [])
        keep = [row for row in items if str(row.get("id", "")) != cid]
        removed = len(items) - len(keep)
        store["connectors"] = keep
        self._save_connector_store(store)
        return {"ok": True, "removed": removed}

    def _mcp_connector_file(self) -> Path:
        return self.base_dir / "mcp_connectors.json"

    def _mcp_connector_store(self) -> dict[str, Any]:
        f = self._mcp_connector_file()
        if not f.exists():
            _write_json(f, DEFAULT_MCP_CONNECTORS)
        raw = _read_json(f, {"connectors": []})
        items = raw.get("connectors", [])
        if not isinstance(items, list):
            items = []
        valid = [x for x in items if isinstance(x, dict)]
        changed = False
        if not valid:
            valid = []
            changed = True
        existing_ids = {str(x.get("id", "")) for x in valid}
        for d in _all_mcp_preset_connectors():
            did = str(d.get("id", ""))
            if did and did not in existing_ids:
                valid.append(dict(d))
                existing_ids.add(did)
                changed = True
        if changed:
            _write_json(f, {"connectors": valid})
        return {"connectors": valid}

    def _save_mcp_connector_store(self, store: dict[str, Any]) -> None:
        _write_json(self._mcp_connector_file(), {"connectors": list(store.get("connectors", []) or [])})

    def list_mcp_connectors(self) -> dict[str, Any]:
        return self._mcp_connector_store()

    def sync_mcp_presets(self) -> dict[str, Any]:
        store = self._mcp_connector_store()
        items = list(store.get("connectors", []) or [])
        existing_ids = {str(x.get("id", "")) for x in items if isinstance(x, dict)}
        added = 0
        for d in _all_mcp_preset_connectors():
            did = str(d.get("id", ""))
            if did and did not in existing_ids:
                items.append(dict(d))
                existing_ids.add(did)
                added += 1
        if added > 0:
            store["connectors"] = items
            self._save_mcp_connector_store(store)
        return {"ok": True, "added": added, "total": len(items)}

    def save_mcp_connector(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = _normalize_mcp_connector_payload(payload)
        if not item.get("name"):
            return {"ok": False, "message": "MCP 连接器名称必填"}
        if not item.get("command"):
            return {"ok": False, "message": "MCP 命令必填"}

        store = self._mcp_connector_store()
        items = list(store.get("connectors", []) or [])
        out: list[dict[str, Any]] = []
        replaced = False
        for row in items:
            if str(row.get("id", "")) == str(item.get("id", "")):
                out.append(item)
                replaced = True
            else:
                out.append(row)
        if not replaced:
            out.append(item)
        store["connectors"] = out
        self._save_mcp_connector_store(store)
        return {"ok": True, "id": item["id"], "saved": True}

    def delete_mcp_connector(self, connector_id: str) -> dict[str, Any]:
        cid = str(connector_id or "").strip()
        if not cid:
            return {"ok": False, "message": "MCP 连接器 ID 必填"}
        store = self._mcp_connector_store()
        items = list(store.get("connectors", []) or [])
        keep = [row for row in items if str(row.get("id", "")) != cid]
        removed = len(items) - len(keep)
        store["connectors"] = keep
        self._save_mcp_connector_store(store)
        return {"ok": True, "removed": removed}

    def _resolve_mcp_connector(self, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        connector_id = str(payload.get("connector_id", "")).strip()
        base_cfg: dict[str, Any] = {}
        if connector_id:
            store = self._mcp_connector_store()
            for row in list(store.get("connectors", []) or []):
                if str(row.get("id", "")) == connector_id:
                    base_cfg = dict(row)
                    break
            if not base_cfg:
                return None, f"未找到 MCP 连接器: {connector_id}"

        override = dict(payload.get("connector", {}) or {})
        merged = dict(base_cfg)
        for k, v in override.items():
            key = str(k)
            if key in {"id", "name", "command", "cwd"}:
                if str(v or "").strip():
                    merged[key] = v
                continue
            if key in {"args", "env"}:
                if isinstance(v, list) or isinstance(v, dict):
                    merged[key] = v
                elif isinstance(v, str) and v.strip():
                    merged[key] = v
                continue
            if key == "timeout_sec":
                merged[key] = v
                continue
            merged[key] = v
        if not merged:
            merged = dict(payload)
        cfg = _normalize_mcp_connector_payload(merged)
        if not cfg.get("command"):
            return None, "MCP 命令必填"
        return cfg, ""

    def _runtime_mcp_connector(self, cfg: dict[str, Any], query: str) -> dict[str, Any]:
        runtime_cfg = dict(cfg)
        resolved_command = str(_resolve_placeholders(cfg.get("command", ""), query))
        if os.name == "nt":
            low = resolved_command.lower().strip()
            if low == "npx":
                resolved_command = "npx.cmd"
            elif low == "npm":
                resolved_command = "npm.cmd"
        runtime_cfg["command"] = resolved_command
        runtime_cfg["args"] = _resolve_placeholders(list(cfg.get("args", []) or []), query)
        runtime_cfg["env"] = _resolve_placeholders(dict(cfg.get("env", {}) or {}), query)
        runtime_cfg["cwd"] = str(_resolve_placeholders(cfg.get("cwd", ""), query))
        env = runtime_cfg.get("env", {})
        if not isinstance(env, dict):
            env = {}
        runtime_cfg["env"] = {str(k): str(v) for k, v in env.items() if str(k).strip()}
        args = runtime_cfg.get("args", [])
        if not isinstance(args, list):
            args = []
        runtime_cfg["args"] = [str(x) for x in args if str(x).strip()]
        return runtime_cfg

    def _candidate_mcp_run_cfgs(self, run_cfg: dict[str, Any]) -> list[dict[str, Any]]:
        base = dict(run_cfg)
        base_args = [str(x) for x in list(base.get("args", []) or []) if str(x).strip()]
        pkg_hint = " ".join(base_args).lower()

        variants: list[list[str]] = [base_args]
        if "--stdio" not in base_args and "@modelcontextprotocol/" not in pkg_hint:
            variants.append([*base_args, "--stdio"])

        out: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for args in variants:
            key = tuple(args)
            if key in seen:
                continue
            seen.add(key)
            c = dict(base)
            c["args"] = list(args)
            out.append(c)
        return out

    def list_mcp_tools(self, payload: dict[str, Any]) -> dict[str, Any]:
        cfg, err = self._resolve_mcp_connector(payload)
        if cfg is None:
            return {"ok": False, "message": err}
        query = str(payload.get("query", "")).strip()
        base_cfg = self._runtime_mcp_connector(cfg, query)
        init: dict[str, Any] = {}
        tools: list[Any] = []
        run_cfg = dict(base_cfg)
        errors: list[str] = []
        for candidate in self._candidate_mcp_run_cfgs(base_cfg):
            try:
                with MCPStdioClient(
                    command=str(candidate.get("command", "")),
                    args=list(candidate.get("args", []) or []),
                    env=dict(candidate.get("env", {}) or {}),
                    cwd=str(candidate.get("cwd", "")),
                    timeout_sec=min(15.0, float(candidate.get("timeout_sec", 45.0))),
                ) as cli:
                    init = cli.initialize()
                    listed = cli.list_tools()
                    tools = list(listed.get("tools", []) or [])
                    run_cfg = dict(candidate)
                    errors = []
                    break
            except Exception as exc:
                errors.append(str(exc)[:260])
        if errors:
            return {"ok": False, "message": "列出 MCP 工具失败: " + " | ".join(errors[:3])}
        return {
            "ok": True,
            "message": "MCP 工具列表已加载",
            "connector": {"id": cfg.get("id"), "name": cfg.get("name")},
            "initialize": init,
            "tool_count": len(tools),
            "tools": tools,
        }

    def call_mcp_tool(self, payload: dict[str, Any]) -> dict[str, Any]:
        cfg, err = self._resolve_mcp_connector(payload)
        if cfg is None:
            return {"ok": False, "message": err}

        tool_name = str(payload.get("tool_name", "")).strip()
        if not tool_name:
            return {"ok": False, "message": "工具名（tool_name）必填"}

        query = str(payload.get("query", "")).strip()
        run_once = bool(payload.get("run_once", False))
        inject = bool(payload.get("inject", True))

        tool_args = payload.get("tool_args", {})
        if not isinstance(tool_args, dict):
            tool_args = {}
        tool_args = _resolve_placeholders(tool_args, query)
        if not isinstance(tool_args, dict):
            tool_args = {}

        base_cfg = self._runtime_mcp_connector(cfg, query)
        run_cfg = dict(base_cfg)
        called: dict[str, Any] = {}
        init: dict[str, Any] = {}
        errors: list[str] = []
        for candidate in self._candidate_mcp_run_cfgs(base_cfg):
            try:
                with MCPStdioClient(
                    command=str(candidate.get("command", "")),
                    args=list(candidate.get("args", []) or []),
                    env=dict(candidate.get("env", {}) or {}),
                    cwd=str(candidate.get("cwd", "")),
                    timeout_sec=min(15.0, float(candidate.get("timeout_sec", 45.0))),
                ) as cli:
                    init = cli.initialize()
                    called = cli.call_tool(tool_name, tool_args)
                    run_cfg = dict(candidate)
                    errors = []
                    break
            except Exception as exc:
                errors.append(str(exc)[:260])
        if errors:
            return {"ok": False, "message": "MCP 调用失败: " + " | ".join(errors[:3])}

        extracted = _join_mcp_content(called).strip()
        preview = extracted[:1800] if extracted else json.dumps(called, ensure_ascii=False)[:1800]
        source_name = str(cfg.get("name", "")).strip() or str(cfg.get("id", "")).strip() or "mcp"
        source = f"mcp-bridge:{source_name}"[:120]

        if inject:
            conn = self._conn()
            try:
                enqueue_event(
                    conn,
                    source=source,
                    event_type="mcp_bridge",
                    content=f"tool={tool_name} connector={source_name}",
                    meta={
                        "connector": cfg,
                        "query": query[:500],
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "response_preview": preview[:1200],
                    },
                )
                enqueue_event(
                    conn,
                    source=source,
                    event_type="input",
                    content=f"[{source_name}:{tool_name}] {preview}"[:4000],
                    meta={
                        "from": "mcp_bridge",
                        "tool_name": tool_name,
                        "query": query[:500],
                        "connector": {
                            "id": cfg.get("id"),
                            "name": cfg.get("name"),
                            "command": run_cfg.get("command"),
                        },
                    },
                )
            finally:
                conn.close()

            if run_once:
                self._spawn_once(
                    [
                        "brain_loop.py",
                        "--db",
                        str(self.db_path),
                        "--state",
                        str(self.state_path),
                        "--once",
                        "--max-events",
                        "30",
                    ]
                )

        return {
            "ok": True,
            "message": "MCP 工具已调用" + ("，并已注入" if inject else ""),
            "connector": {"id": cfg.get("id"), "name": cfg.get("name")},
            "tool_name": tool_name,
            "initialize": init,
            "result": called,
            "extracted": preview[:1000],
            "injected": inject,
            "run_once": run_once,
            "source": source,
        }

    def _call_remote(self, *, method: str, endpoint: str, headers: dict[str, str], body: Any) -> dict[str, Any]:
        raw_body = b""
        send_body = method in {"POST", "PUT", "PATCH", "DELETE"}
        if send_body:
            if isinstance(body, (dict, list)):
                raw_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
                headers = {**headers}
                if "Content-Type" not in headers and "content-type" not in headers:
                    headers["Content-Type"] = "application/json"
            elif isinstance(body, str):
                raw_body = body.encode("utf-8")
            elif body is None:
                raw_body = b""
            else:
                raw_body = str(body).encode("utf-8")

        req = Request(
            url=str(endpoint),
            data=(raw_body if send_body else None),
            method=str(method or "POST").upper(),
        )
        for k, v in dict(headers or {}).items():
            req.add_header(str(k), str(v))
        try:
            with urlopen(req, timeout=45) as resp:
                status = int(getattr(resp, "status", resp.getcode()))
                text = resp.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            text = ""
            try:
                text = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                text = str(exc)
            return {
                "ok": False,
                "status": int(getattr(exc, "code", 500)),
                "text": text[:5000],
                "error": str(exc),
            }
        except URLError as exc:
            return {"ok": False, "status": 0, "text": "", "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "status": 0, "text": "", "error": str(exc)}

        parsed: Any
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = text
        return {"ok": True, "status": status, "text": text[:5000], "json": parsed}

    def call_connector(self, payload: dict[str, Any]) -> dict[str, Any]:
        connector_id = str(payload.get("connector_id", "")).strip()
        run_once = bool(payload.get("run_once", False))
        query = str(payload.get("query", "")).strip()

        base_cfg: dict[str, Any] = {}
        if connector_id:
            store = self._connector_store()
            for row in list(store.get("connectors", []) or []):
                if str(row.get("id", "")) == connector_id:
                    base_cfg = dict(row)
                    break
            if not base_cfg:
                return {"ok": False, "message": f"未找到连接器: {connector_id}"}

        override = dict(payload.get("connector", {}) or {})
        merged = dict(base_cfg)
        for k, v in override.items():
            key = str(k)
            if key in {"id", "name", "endpoint", "method", "extract_path"}:
                if str(v or "").strip():
                    merged[key] = v
                continue
            if key in {"headers", "body_template"}:
                if isinstance(v, dict):
                    if v or key not in merged:
                        merged[key] = v
                elif isinstance(v, list):
                    merged[key] = v
                elif isinstance(v, str):
                    if v.strip():
                        merged[key] = v
                continue
            merged[key] = v
        if not merged:
            merged = dict(payload)
        cfg = _normalize_connector_payload(merged)

        if not cfg.get("endpoint"):
            return {"ok": False, "message": "Endpoint 必填"}
        if not query:
            return {"ok": False, "message": "查询内容必填"}

        endpoint = str(_resolve_placeholders(cfg.get("endpoint", ""), query))
        headers = _resolve_placeholders(dict(cfg.get("headers", {}) or {}), query)
        body_template = cfg.get("body_template", {})
        body = _resolve_placeholders(body_template, query)

        remote = self._call_remote(
            method=str(cfg.get("method", "POST")),
            endpoint=endpoint,
            headers=dict(headers or {}),
            body=body,
        )
        if not bool(remote.get("ok", False)):
            return {
                "ok": False,
                "message": str(remote.get("error", "远程调用失败")),
                "status": int(remote.get("status", 0)),
                "response_preview": str(remote.get("text", ""))[:600],
            }

        response_json = remote.get("json")
        extracted = _extract_response_text(response_json, extract_path=str(cfg.get("extract_path", ""))).strip()
        if not extracted:
            extracted = str(remote.get("text", "")).strip()[:1600]
        source_name = str(cfg.get("name", "")).strip() or str(cfg.get("id", "")).strip() or "api"
        source = f"api-bridge:{source_name}"[:120]
        content = f"[{source_name}] {extracted}".strip()

        conn = self._conn()
        try:
            enqueue_event(
                conn,
                source=source,
                event_type="api_bridge",
                content=f"status={int(remote.get('status', 0))} endpoint={endpoint[:180]}",
                meta={
                    "connector": cfg,
                    "query": query[:500],
                    "response_preview": str(remote.get("text", ""))[:1200],
                },
            )
            enqueue_event(
                conn,
                source=source,
                event_type="input",
                content=content[:4000],
                meta={
                    "from": "api_bridge",
                    "query": query[:500],
                    "connector": {
                        "id": cfg.get("id"),
                        "name": cfg.get("name"),
                        "endpoint": endpoint[:240],
                        "method": cfg.get("method"),
                    },
                    "response_preview": str(remote.get("text", ""))[:1200],
                },
            )
        finally:
            conn.close()

        if run_once:
            self._spawn_once(
                [
                    "brain_loop.py",
                    "--db",
                    str(self.db_path),
                    "--state",
                    str(self.state_path),
                    "--once",
                    "--max-events",
                    "30",
                ]
            )

        return {
            "ok": True,
            "message": "API 连接器已调用并注入",
            "status": int(remote.get("status", 0)),
            "source": source,
            "extracted": extracted[:1000],
            "response_preview": str(remote.get("text", ""))[:1000],
        }

    def _conn(self):
        return connect_runtime_db(str(self.db_path))

    def _spawn_once(self, args: list[str]) -> None:
        subprocess.Popen(
            [sys.executable, *args],
            cwd=str(self.base_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

