from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return dict(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
        if isinstance(data, dict):
            out = dict(default)
            out.update(data)
            return out
    except Exception:
        pass
    return dict(default)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _slug(text: str) -> str:
    raw = str(text or "").strip().lower()
    cleaned = "".join(ch if ("a" <= ch <= "z" or "0" <= ch <= "9") else "-" for ch in raw)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "connector"


def _normalize_connector_payload(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    endpoint = str(payload.get("endpoint", "")).strip()
    method = str(payload.get("method", "POST")).strip().upper()
    extract_path = str(payload.get("extract_path", "")).strip()

    headers = payload.get("headers", {})
    if not isinstance(headers, dict):
        headers = {}
    headers = {str(k): str(v) for k, v in headers.items() if str(k).strip()}

    body_template = payload.get("body_template")
    if body_template is None:
        body_template = {}
    if isinstance(body_template, str):
        try:
            body_template = json.loads(body_template)
        except Exception:
            body_template = {"text": body_template}

    cid = str(payload.get("id", "")).strip() or _slug(name or endpoint)
    return {
        "id": cid[:80],
        "name": name[:120],
        "endpoint": endpoint[:2000],
        "method": method if method in {"GET", "POST", "PUT", "PATCH", "DELETE"} else "POST",
        "headers": headers,
        "body_template": body_template,
        "extract_path": extract_path[:240],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _resolve_placeholders(value: Any, query: str) -> Any:
    if isinstance(value, str):
        txt = value.replace("{{input}}", str(query or ""))

        def repl(match: re.Match[str]) -> str:
            key = str(match.group(1) or "").strip()
            if not key:
                return ""
            return str(os.environ.get(key, ""))

        return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", repl, txt)

    if isinstance(value, list):
        return [_resolve_placeholders(x, query) for x in value]
    if isinstance(value, dict):
        return {str(k): _resolve_placeholders(v, query) for k, v in value.items()}
    return value


def _extract_by_path(payload: Any, path: str) -> Any:
    cur = payload
    for token in [p for p in str(path or "").split(".") if p]:
        if isinstance(cur, list):
            if not token.isdigit():
                return None
            idx = int(token)
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
            continue
        if isinstance(cur, dict):
            if token not in cur:
                return None
            cur = cur[token]
            continue
        return None
    return cur


def _extract_response_text(payload: Any, extract_path: str = "") -> str:
    if str(extract_path or "").strip():
        val = _extract_by_path(payload, extract_path)
        if val is None:
            return ""
        if isinstance(val, str):
            return val
        return json.dumps(val, ensure_ascii=False)

    candidates = [
        "choices.0.message.content",
        "choices.0.text",
        "output_text",
        "answer",
        "result",
        "data.0.text",
        "candidates.0.content.parts.0.text",
    ]
    for p in candidates:
        val = _extract_by_path(payload, p)
        if isinstance(val, str) and val.strip():
            return val
        if isinstance(val, (int, float)):
            return str(val)
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False)


def _mcp_npx_command() -> str:
    return "npx.cmd" if os.name == "nt" else "npx"


def _build_npx_mcp_connector(
    *,
    connector_id: str,
    name: str,
    package: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    timeout_sec: float = 45.0,
    tags: list[str] | None = None,
    requires_env: list[str] | None = None,
    notes: str = "",
    source: str = "awesome-mcp-servers/README-zh.md",
) -> dict[str, Any]:
    return {
        "id": str(connector_id).strip(),
        "name": str(name).strip(),
        "command": _mcp_npx_command(),
        "args": ["-y", str(package).strip(), *[str(x) for x in list(args or []) if str(x).strip()]],
        "env": {str(k): str(v) for k, v in dict(env or {}).items() if str(k).strip()},
        "cwd": "",
        "timeout_sec": float(timeout_sec),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tags": [str(x).strip().lower() for x in list(tags or []) if str(x).strip()],
        "requires_env": [str(x).strip() for x in list(requires_env or []) if str(x).strip()],
        "source": str(source).strip(),
        "notes": str(notes).strip(),
    }


DEFAULT_MCP_CONNECTORS: dict[str, list[dict[str, Any]]] = {
    "connectors": [
        {
            "id": "github-mcp",
            "name": "github-mcp-docker",
            "command": "docker",
            "args": [
                "run",
                "-i",
                "--rm",
                "-e",
                "GITHUB_PERSONAL_ACCESS_TOKEN",
                "ghcr.io/github/github-mcp-server",
            ],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"},
            "cwd": "",
            "timeout_sec": 45,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tags": ["official", "github", "docker", "cloud"],
            "requires_env": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
            "source": "github.com/github/github-mcp-server",
            "notes": "Docker runtime required.",
        },
        _build_npx_mcp_connector(
            connector_id="github-mcp-npx",
            name="github-mcp-npx",
            package="@modelcontextprotocol/server-github",
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"},
            tags=["official", "github", "cloud"],
            requires_env=["GITHUB_PERSONAL_ACCESS_TOKEN"],
        ),
    ]
}


AWESOME_MCP_CONNECTORS: dict[str, list[dict[str, Any]]] = {
    "connectors": [
        _build_npx_mcp_connector(
            connector_id="awesome-everything",
            name="awesome: everything",
            package="@modelcontextprotocol/server-everything",
            tags=["awesome", "official", "local"],
            notes="万能测试服务器，便于快速联调 MCP 协议流。",
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-sequential-thinking",
            name="awesome: sequential thinking",
            package="@modelcontextprotocol/server-sequential-thinking",
            tags=["awesome", "reasoning"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-filesystem",
            name="awesome: filesystem",
            package="@modelcontextprotocol/server-filesystem",
            args=["."],
            tags=["awesome", "official", "local", "filesystem"],
            notes="默认仅开放当前工作目录，必要时改为指定路径白名单。",
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-memory",
            name="awesome: memory",
            package="@modelcontextprotocol/server-memory",
            tags=["awesome", "official", "memory", "local"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-puppeteer",
            name="awesome: puppeteer",
            package="@modelcontextprotocol/server-puppeteer",
            tags=["awesome", "official", "browser"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-playwright",
            name="awesome: playwright",
            package="@playwright/mcp",
            tags=["awesome", "browser"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-fetch",
            name="awesome: fetch",
            package="@kazuph/mcp-fetch",
            tags=["awesome", "web", "fetch"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-brave-search",
            name="awesome: brave search",
            package="@modelcontextprotocol/server-brave-search",
            env={"BRAVE_API_KEY": "${BRAVE_API_KEY}"},
            tags=["awesome", "official", "search", "cloud"],
            requires_env=["BRAVE_API_KEY"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-google-maps",
            name="awesome: google maps",
            package="@modelcontextprotocol/server-google-maps",
            env={"GOOGLE_MAPS_API_KEY": "${GOOGLE_MAPS_API_KEY}"},
            tags=["awesome", "official", "maps", "cloud"],
            requires_env=["GOOGLE_MAPS_API_KEY"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-gitlab",
            name="awesome: gitlab",
            package="@modelcontextprotocol/server-gitlab",
            env={
                "GITLAB_PERSONAL_ACCESS_TOKEN": "${GITLAB_PERSONAL_ACCESS_TOKEN}",
                "GITLAB_API_URL": "${GITLAB_API_URL}",
            },
            tags=["awesome", "official", "gitlab", "cloud"],
            requires_env=["GITLAB_PERSONAL_ACCESS_TOKEN"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-slack",
            name="awesome: slack",
            package="@modelcontextprotocol/server-slack",
            env={"SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}"},
            tags=["awesome", "official", "slack", "cloud"],
            requires_env=["SLACK_BOT_TOKEN"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-sentry",
            name="awesome: sentry",
            package="@sentry/mcp-server",
            env={
                "SENTRY_AUTH_TOKEN": "${SENTRY_AUTH_TOKEN}",
                "SENTRY_ORG_SLUG": "${SENTRY_ORG_SLUG}",
            },
            tags=["awesome", "monitoring", "cloud"],
            requires_env=["SENTRY_AUTH_TOKEN"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-postgres",
            name="awesome: postgres",
            package="@modelcontextprotocol/server-postgres",
            env={"DATABASE_URL": "${DATABASE_URL}"},
            tags=["awesome", "official", "db", "cloud"],
            requires_env=["DATABASE_URL"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-sqlite",
            name="awesome: sqlite",
            package="mcp-sqlite-tools",
            env={"SQLITE_DB_PATH": "${SQLITE_DB_PATH}"},
            tags=["awesome", "db", "local"],
            requires_env=["SQLITE_DB_PATH"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-linear",
            name="awesome: linear",
            package="@tacticlaunch/mcp-linear",
            env={"LINEAR_API_KEY": "${LINEAR_API_KEY}"},
            tags=["awesome", "pm", "cloud"],
            requires_env=["LINEAR_API_KEY"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-ragie",
            name="awesome: ragie",
            package="@ragieai/mcp-server",
            env={"RAGIE_API_KEY": "${RAGIE_API_KEY}"},
            tags=["awesome", "rag", "cloud"],
            requires_env=["RAGIE_API_KEY"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-chart",
            name="awesome: chart",
            package="@antv/mcp-server-chart",
            tags=["awesome", "visualization"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-youtube-transcript",
            name="awesome: youtube transcript",
            package="@kimtaeyoon83/mcp-server-youtube-transcript",
            tags=["awesome", "media"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-supabase",
            name="awesome: supabase",
            package="@joshuarileydev/supabase-mcp-server",
            env={
                "SUPABASE_URL": "${SUPABASE_URL}",
                "SUPABASE_SERVICE_ROLE_KEY": "${SUPABASE_SERVICE_ROLE_KEY}",
            },
            tags=["awesome", "db", "cloud"],
            requires_env=["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-firebase",
            name="awesome: firebase",
            package="@gannonh/firebase-mcp",
            env={"GOOGLE_APPLICATION_CREDENTIALS": "${GOOGLE_APPLICATION_CREDENTIALS}"},
            tags=["awesome", "db", "cloud"],
            requires_env=["GOOGLE_APPLICATION_CREDENTIALS"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-openapi",
            name="awesome: openapi",
            package="openapi-mcp-server",
            tags=["awesome", "api"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-swagger",
            name="awesome: swagger",
            package="mcp-swagger-server",
            tags=["awesome", "api"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-google-drive",
            name="awesome: google drive",
            package="mcp-google-drive",
            env={
                "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
                "GOOGLE_CLIENT_SECRET": "${GOOGLE_CLIENT_SECRET}",
                "GOOGLE_REFRESH_TOKEN": "${GOOGLE_REFRESH_TOKEN}",
            },
            tags=["awesome", "drive", "cloud"],
            requires_env=["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-google-workspace",
            name="awesome: google workspace",
            package="mcp-server-google-workspace",
            env={
                "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
                "GOOGLE_CLIENT_SECRET": "${GOOGLE_CLIENT_SECRET}",
                "GOOGLE_REFRESH_TOKEN": "${GOOGLE_REFRESH_TOKEN}",
            },
            tags=["awesome", "gmail", "calendar", "drive", "cloud"],
            requires_env=["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-ragdocs",
            name="awesome: ragdocs",
            package="@hannesrudolph/mcp-ragdocs",
            tags=["awesome", "rag", "knowledge"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-public-ui",
            name="awesome: public ui",
            package="@public-ui/mcp",
            tags=["awesome", "ui"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-codemirror",
            name="awesome: codemirror",
            package="@marimo-team/codemirror-mcp",
            tags=["awesome", "editor", "local"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-multiverse",
            name="awesome: multiverse",
            package="@lamemind/mcp-server-multiverse",
            tags=["awesome", "middleware"],
        ),
        _build_npx_mcp_connector(
            connector_id="awesome-time",
            name="awesome: time",
            package="time-mcp",
            tags=["awesome", "utility", "local"],
        ),
    ]
}


def _all_mcp_preset_connectors() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in list(DEFAULT_MCP_CONNECTORS.get("connectors", []) or []):
        if isinstance(row, dict):
            out.append(dict(row))
    for row in list(AWESOME_MCP_CONNECTORS.get("connectors", []) or []):
        if isinstance(row, dict):
            out.append(dict(row))
    return out


def _normalize_mcp_connector_payload(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    command = str(payload.get("command", "")).strip()
    cwd = str(payload.get("cwd", "")).strip()
    timeout_raw = payload.get("timeout_sec", 45)
    try:
        timeout_sec = float(timeout_raw)
    except Exception:
        timeout_sec = 45.0
    timeout_sec = max(5.0, min(timeout_sec, 300.0))

    args = payload.get("args", [])
    if isinstance(args, str):
        s = args.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                args = parsed if isinstance(parsed, list) else [s]
            except Exception:
                args = [s]
        elif s:
            args = [s]
        else:
            args = []
    if not isinstance(args, list):
        args = []
    args = [str(x) for x in args if str(x).strip()]

    env = payload.get("env", {})
    if not isinstance(env, dict):
        env = {}
    env = {str(k): str(v) for k, v in env.items() if str(k).strip()}

    tags_raw = payload.get("tags", [])
    if isinstance(tags_raw, str):
        tags_raw = [x.strip() for x in tags_raw.split(",")]
    if not isinstance(tags_raw, list):
        tags_raw = []
    tags = [str(x).strip().lower()[:40] for x in tags_raw if str(x).strip()]

    requires_env_raw = payload.get("requires_env", [])
    if isinstance(requires_env_raw, str):
        requires_env_raw = [x.strip() for x in requires_env_raw.split(",")]
    if not isinstance(requires_env_raw, list):
        requires_env_raw = []
    requires_env = [str(x).strip()[:80] for x in requires_env_raw if str(x).strip()]

    source = str(payload.get("source", "")).strip()
    notes = str(payload.get("notes", "")).strip()

    cid = str(payload.get("id", "")).strip() or _slug(name or command)
    return {
        "id": cid[:80],
        "name": name[:120],
        "command": command[:500],
        "args": args,
        "env": env,
        "cwd": cwd[:1000],
        "timeout_sec": timeout_sec,
        "tags": tags[:16],
        "requires_env": requires_env[:24],
        "source": source[:240],
        "notes": notes[:500],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _join_mcp_content(result: Any) -> str:
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    txt = item.get("text")
                    if txt is not None:
                        chunks.append(str(txt))
            if chunks:
                return "\n".join(chunks)
        if "text" in result:
            return str(result.get("text") or "")
    return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)


class MCPStdioClient:
    def __init__(
        self,
        *,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
        cwd: str = "",
        timeout_sec: float = 45.0,
    ) -> None:
        self.command = str(command or "").strip()
        self.args = [str(x) for x in list(args or [])]
        self.env = dict(env or {})
        self.cwd = str(cwd or "").strip()
        self.timeout_sec = float(timeout_sec or 45.0)
        self.proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._msg_q: queue.Queue[dict[str, Any]] = queue.Queue()
        self._write_lock = threading.Lock()
        self._next_id = 1
        self._stderr_buf: list[str] = []

    def __enter__(self) -> "MCPStdioClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if not self.command:
            raise RuntimeError("mcp command is empty")
        env = os.environ.copy()
        for k, v in self.env.items():
            env[str(k)] = str(v)
        try:
            self.proc = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=(self.cwd or None),
                env=env,
            )
        except Exception as exc:
            raise RuntimeError(f"mcp start failed: {exc}") from exc

        self._reader = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._stderr_loop, daemon=True)
        self._stderr_reader.start()

    def close(self) -> None:
        proc = self.proc
        self.proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _stderr_loop(self) -> None:
        proc = self.proc
        if proc is None or proc.stderr is None:
            return
        try:
            while True:
                line = proc.stderr.readline()
                if not line:
                    break
                txt = line.decode("utf-8", errors="ignore").strip()
                if txt:
                    self._stderr_buf.append(txt[:400])
                    if len(self._stderr_buf) > 30:
                        self._stderr_buf = self._stderr_buf[-30:]
        except Exception:
            return

    def _reader_loop(self) -> None:
        proc = self.proc
        if proc is None or proc.stdout is None:
            self._msg_q.put({"__error__": "mcp stdout unavailable"})
            return
        try:
            while True:
                msg = self._read_message(proc.stdout)
                self._msg_q.put(msg)
        except EOFError:
            self._msg_q.put({"__error__": "mcp stream closed"})
        except Exception as exc:
            self._msg_q.put({"__error__": f"mcp read failed: {exc}"})

    def _read_message(self, stream: Any) -> dict[str, Any]:
        headers: dict[str, str] = {}
        while True:
            line = stream.readline()
            if not line:
                raise EOFError("no header line")
            if line in (b"\r\n", b"\n"):
                break
            text = line.decode("ascii", errors="ignore").strip()
            if ":" not in text:
                continue
            k, v = text.split(":", 1)
            headers[str(k).strip().lower()] = str(v).strip()
        length = int(headers.get("content-length", "0") or "0")
        if length <= 0:
            raise RuntimeError("invalid content-length")
        body = stream.read(length)
        if not body:
            raise EOFError("no body")
        try:
            return json.loads(body.decode("utf-8", errors="ignore"))
        except Exception as exc:
            raise RuntimeError(f"invalid json payload: {exc}") from exc

    def _send(self, payload: dict[str, Any]) -> None:
        proc = self.proc
        if proc is None or proc.stdin is None:
            raise RuntimeError("mcp stdin unavailable")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
        with self._write_lock:
            proc.stdin.write(header)
            proc.stdin.write(data)
            proc.stdin.flush()

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        rid = self._next_id
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": rid,
                "method": str(method),
                "params": dict(params or {}),
            }
        )
        deadline = time.time() + float(self.timeout_sec)
        while time.time() < deadline:
            remaining = max(0.05, deadline - time.time())
            try:
                msg = self._msg_q.get(timeout=remaining)
            except queue.Empty:
                continue
            if "__error__" in msg:
                err_tail = " | ".join(self._stderr_buf[-3:]) if self._stderr_buf else ""
                raise RuntimeError(f"{msg.get('__error__')}{(' | stderr: ' + err_tail) if err_tail else ''}")
            if int(msg.get("id", -1)) != rid:
                continue
            if "error" in msg:
                err = msg.get("error")
                raise RuntimeError(f"mcp error: {json.dumps(err, ensure_ascii=False)[:500]}")
            result = msg.get("result")
            return result if isinstance(result, dict) else {"value": result}
        err_tail = " | ".join(self._stderr_buf[-3:]) if self._stderr_buf else ""
        raise TimeoutError(f"mcp request timeout: {method}{(' | stderr: ' + err_tail) if err_tail else ''}")

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send(
            {
                "jsonrpc": "2.0",
                "method": str(method),
                "params": dict(params or {}),
            }
        )

    def initialize(self) -> dict[str, Any]:
        result = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "azi-web-panel", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})
        return result

    def list_tools(self) -> dict[str, Any]:
        return self._request("tools/list", {})

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "tools/call",
            {"name": str(name or "").strip(), "arguments": dict(arguments or {})},
        )


__all__ = [
    "DEFAULT_MCP_CONNECTORS",
    "MCPStdioClient",
    "_all_mcp_preset_connectors",
    "_extract_response_text",
    "_join_mcp_content",
    "_normalize_connector_payload",
    "_normalize_mcp_connector_payload",
    "_read_json",
    "_resolve_placeholders",
    "_write_json",
]
