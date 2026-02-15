from __future__ import annotations

import argparse
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from azi_rebuild.panel_service import PanelConnectorService
from azi_rebuild.panel_status import (
    collect_cognitive_v0_status,
    collect_consciousness_status,
    collect_memory_status,
    collect_skills_router_status,
    load_skill_router_policy,
    save_skill_router_policy,
)
from azi_rebuild.runtime import (
    build_snapshot_payload,
    connect_runtime_db,
    enqueue_event,
    load_runtime_state,
    now_iso,
)


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>阿紫认知中枢面板</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Orbitron:wght@500;700&family=Rajdhani:wght@400;500;600&display=swap');
    :root {
      --bg0: #06030d;
      --bg1: #120a24;
      --bg2: #1c1140;
      --panel: rgba(24, 12, 47, 0.78);
      --panel2: rgba(35, 19, 68, 0.78);
      --text: #f4eeff;
      --muted: #c3afeb;
      --accent: #b65cff;
      --accent2: #71a3ff;
      --ok: #71f0c4;
      --warn: #ffd071;
      --err: #ff8ea5;
      --border: rgba(175, 118, 255, 0.44);
      --glow: 0 0 0 1px rgba(178, 112, 255, 0.18), 0 18px 45px rgba(78, 26, 142, 0.42);
    }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      font-family: "Rajdhani", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background:
        radial-gradient(1200px 620px at -10% -20%, rgba(184, 83, 255, 0.30) 0%, transparent 58%),
        radial-gradient(900px 620px at 108% 2%, rgba(96, 140, 255, 0.26) 0%, transparent 52%),
        radial-gradient(1300px 900px at 45% 120%, rgba(136, 58, 246, 0.22) 0%, transparent 72%),
        linear-gradient(145deg, var(--bg0) 0%, var(--bg1) 48%, var(--bg2) 100%);
      overflow-x: hidden;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.22;
      background-image:
        linear-gradient(rgba(201, 153, 255, 0.26) 1px, transparent 1px),
        linear-gradient(90deg, rgba(201, 153, 255, 0.22) 1px, transparent 1px);
      background-size: 36px 36px;
      mask-image: radial-gradient(circle at 50% 40%, black 12%, transparent 78%);
      z-index: 0;
    }
    body::after {
      content: "";
      position: fixed;
      inset: -30% -10%;
      pointer-events: none;
      background:
        radial-gradient(35% 45% at 18% 30%, rgba(196, 99, 255, 0.16), transparent 70%),
        radial-gradient(30% 40% at 82% 22%, rgba(123, 170, 255, 0.14), transparent 72%),
        radial-gradient(25% 35% at 65% 75%, rgba(233, 123, 255, 0.12), transparent 74%);
      filter: blur(20px);
      animation: nebulaDrift 16s ease-in-out infinite alternate;
      z-index: 0;
    }
    .wrap {
      position: relative;
      z-index: 1;
      max-width: 1440px;
      margin: 0 auto;
      padding: 18px 18px 24px;
    }
    .top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
      padding: 14px 16px;
      border-radius: 16px;
      border: 1px solid var(--border);
      background: linear-gradient(120deg, rgba(35, 19, 71, 0.72), rgba(21, 14, 49, 0.65));
      backdrop-filter: blur(8px);
      box-shadow: var(--glow);
      animation: riseIn .45s ease-out both;
    }
    .top-right {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      flex-wrap: wrap;
    }
    .title {
      font-family: "Orbitron", "Rajdhani", sans-serif;
      font-size: 24px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      text-shadow: 0 0 18px rgba(187, 108, 255, 0.5);
    }
    .sub {
      font-size: 13px;
      color: var(--muted);
      letter-spacing: .04em;
      margin-top: 3px;
    }
    .crs-box {
      min-width: 246px;
      border: 1px solid rgba(189, 145, 255, 0.42);
      background: linear-gradient(140deg, rgba(36, 20, 70, 0.78), rgba(24, 13, 48, 0.76));
      border-radius: 12px;
      padding: 8px 10px;
      box-shadow: 0 8px 20px rgba(88, 48, 150, 0.36);
    }
    .crs-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 12px;
      color: #efe6ff;
      letter-spacing: .04em;
      margin-bottom: 6px;
    }
    .lamp {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
      box-shadow: 0 0 12px rgba(255,255,255,0.35);
      background: #7d6c9e;
      margin-right: 6px;
    }
    .lamp.green {
      background: var(--ok);
      box-shadow: 0 0 10px rgba(113,240,196,0.9), 0 0 18px rgba(113,240,196,0.5);
    }
    .lamp.yellow {
      background: var(--warn);
      box-shadow: 0 0 10px rgba(255,208,113,0.9), 0 0 18px rgba(255,208,113,0.5);
    }
    .lamp.red {
      background: var(--err);
      box-shadow: 0 0 10px rgba(255,142,165,0.9), 0 0 18px rgba(255,142,165,0.5);
    }
    .crs-meta {
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
    }
    .crs-trend {
      width: 228px;
      height: 44px;
      border-radius: 8px;
      background: rgba(13, 8, 31, 0.6);
      border: 1px solid rgba(171, 132, 236, 0.26);
      overflow: hidden;
      position: relative;
    }
    .crs-trend svg {
      width: 100%;
      height: 100%;
      display: block;
    }
    .crs-trend-grid {
      stroke: rgba(176, 146, 232, 0.18);
      stroke-width: 1;
    }
    .crs-trend-line {
      fill: none;
      stroke: #caa2ff;
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .crs-trend-fill {
      fill: rgba(181, 99, 255, 0.18);
      stroke: none;
    }
    .orch-box {
      min-width: 246px;
      border: 1px solid rgba(122, 197, 255, 0.34);
      background: linear-gradient(140deg, rgba(18, 33, 68, 0.78), rgba(14, 24, 52, 0.76));
      border-radius: 12px;
      padding: 8px 10px;
      box-shadow: 0 8px 20px rgba(34, 73, 146, 0.34);
    }
    .orch-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 12px;
      color: #efe6ff;
      letter-spacing: .04em;
      margin-bottom: 6px;
    }
    .orch-meta {
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
    }
    .orch-trend {
      width: 228px;
      height: 44px;
      border-radius: 8px;
      background: rgba(9, 17, 34, 0.62);
      border: 1px solid rgba(113, 173, 252, 0.22);
      overflow: hidden;
      position: relative;
    }
    .orch-trend svg {
      width: 100%;
      height: 100%;
      display: block;
    }
    .orch-trend-grid {
      stroke: rgba(152, 193, 252, 0.16);
      stroke-width: 1;
    }
    .orch-trend-success {
      fill: none;
      stroke: #7df0c7;
      stroke-width: 2;
      stroke-linecap: round;
      stroke-linejoin: round;
    }
    .orch-trend-latency {
      fill: none;
      stroke: #78b7ff;
      stroke-width: 1.8;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-dasharray: 3 2;
      opacity: 0.95;
    }
    .btns { display: flex; gap: 8px; flex-wrap: wrap; }
    button {
      border: 1px solid rgba(199, 146, 255, 0.42);
      background: linear-gradient(135deg, rgba(177, 88, 255, 0.88), rgba(97, 142, 255, 0.88));
      color: #fff;
      border-radius: 11px;
      padding: 8px 12px;
      cursor: pointer;
      font-family: "Rajdhani", sans-serif;
      font-weight: 600;
      letter-spacing: .04em;
      transition: transform .18s ease, box-shadow .18s ease, filter .18s ease;
      box-shadow: 0 8px 22px rgba(92, 50, 158, 0.38);
    }
    button:hover { transform: translateY(-1px); filter: brightness(1.07); box-shadow: 0 10px 26px rgba(120, 60, 196, 0.46); }
    button:active { transform: translateY(0); }
    button.secondary {
      background: linear-gradient(135deg, rgba(55, 38, 102, 0.9), rgba(35, 30, 76, 0.9));
      border-color: rgba(160, 122, 230, 0.40);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 13px;
    }
    .card {
      position: relative;
      background: linear-gradient(170deg, var(--panel), var(--panel2));
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 12px;
      min-height: 120px;
      box-shadow: var(--glow);
      backdrop-filter: blur(8px);
      animation: riseIn .5s ease-out both;
    }
    .card::before {
      content: "";
      position: absolute;
      inset: 0 0 auto 0;
      height: 2px;
      border-radius: 16px 16px 0 0;
      background: linear-gradient(90deg, rgba(214, 131, 255, 0.0), rgba(214, 131, 255, 0.9), rgba(113, 163, 255, 0.88), rgba(214, 131, 255, 0.0));
    }
    .grid .card:nth-child(1) { animation-delay: .02s; }
    .grid .card:nth-child(2) { animation-delay: .05s; }
    .grid .card:nth-child(3) { animation-delay: .08s; }
    .grid .card:nth-child(4) { animation-delay: .11s; }
    .grid .card:nth-child(5) { animation-delay: .14s; }
    .grid .card:nth-child(6) { animation-delay: .17s; }
    .grid .card:nth-child(7) { animation-delay: .20s; }
    .grid .card:nth-child(8) { animation-delay: .23s; }
    .grid .card:nth-child(9) { animation-delay: .26s; }
    .grid .card:nth-child(10) { animation-delay: .29s; }
    .grid .card:nth-child(11) { animation-delay: .32s; }
    .card h3 {
      margin: 0 0 8px;
      font-family: "Orbitron", "Rajdhani", sans-serif;
      font-size: 14px;
      letter-spacing: .05em;
      color: #e6d8ff;
      text-transform: uppercase;
    }
    .kv {
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 4px 10px;
      font-size: 13px;
      font-variant-numeric: tabular-nums;
    }
    .k { color: var(--muted); }
    .mono {
      font-family: "JetBrains Mono", "Consolas", "Menlo", monospace;
      white-space: pre-wrap;
      line-height: 1.38;
      font-size: 12px;
      color: #f2e9ff;
    }
    input, select, textarea {
      width: 100%;
      min-height: 84px;
      border-radius: 11px;
      border: 1px solid rgba(176, 136, 240, 0.42);
      background: rgba(14, 10, 35, 0.72);
      color: var(--text);
      padding: 9px 10px;
      resize: vertical;
      font-family: "Rajdhani", "Microsoft YaHei", sans-serif;
      transition: border-color .16s ease, box-shadow .16s ease, background-color .16s ease;
    }
    input::placeholder, textarea::placeholder { color: rgba(206, 185, 244, 0.68); }
    input:focus, select:focus, textarea:focus {
      outline: none;
      border-color: rgba(202, 141, 255, 0.95);
      box-shadow: 0 0 0 3px rgba(192, 113, 255, 0.18);
      background: rgba(16, 11, 40, 0.84);
    }
    input, select { min-height: 36px; resize: none; }
    .row { display: flex; gap: 8px; align-items: center; margin-top: 8px; flex-wrap: wrap; }
    .pill {
      display: inline-block;
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 11px;
      margin-right: 6px;
      letter-spacing: .05em;
    }
    .ok { background: rgba(113,240,196,.16); color: var(--ok); border: 1px solid rgba(113,240,196,.42); }
    .warn { background: rgba(255,208,113,.16); color: var(--warn); border: 1px solid rgba(255,208,113,.42); }
    .err { background: rgba(255,142,165,.16); color: var(--err); border: 1px solid rgba(255,142,165,.42); }
    .status {
      color: var(--muted);
      font-size: 12px;
      margin-top: 6px;
      min-height: 18px;
      letter-spacing: .03em;
    }
    @keyframes riseIn {
      from { opacity: 0; transform: translateY(8px) scale(0.985); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes nebulaDrift {
      from { transform: translate3d(0, 0, 0); }
      to { transform: translate3d(1.8%, -1.3%, 0); }
    }
    @media (max-width: 980px) {
      .wrap { padding: 12px; }
      .top { flex-direction: column; align-items: flex-start; }
      .top-right { width: 100%; justify-content: flex-start; }
      .crs-box { width: 100%; min-width: 0; }
      .crs-trend { width: 100%; }
      .orch-box { width: 100%; min-width: 0; }
      .orch-trend { width: 100%; }
      .btns { width: 100%; }
      .btns button { flex: 1 1 auto; }
      .title { font-size: 21px; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <div class="title">阿紫量子监视台</div>
      <div class="sub" id="updatedAt">加载中...</div>
    </div>
    <div class="top-right">
      <div class="crs-box">
        <div class="crs-row">
          <div><span id="crsLamp" class="lamp"></span><span id="crsText">CRS -</span></div>
          <div id="crsDelta" class="crs-meta">趋势: -</div>
        </div>
        <div class="crs-trend">
          <svg id="crsTrendSvg" viewBox="0 0 228 44" preserveAspectRatio="none">
            <line class="crs-trend-grid" x1="0" y1="22" x2="228" y2="22"></line>
            <path id="crsTrendFill" class="crs-trend-fill" d=""></path>
            <path id="crsTrendPath" class="crs-trend-line" d=""></path>
          </svg>
        </div>
      </div>
      <div class="orch-box">
        <div class="orch-row">
          <div id="orchText">编排 成功率=-</div>
          <div id="orchMeta" class="orch-meta">时延: -</div>
        </div>
        <div class="orch-trend">
          <svg id="orchTrendSvg" viewBox="0 0 228 44" preserveAspectRatio="none">
            <line class="orch-trend-grid" x1="0" y1="22" x2="228" y2="22"></line>
            <path id="orchTrendSuccessPath" class="orch-trend-success" d=""></path>
            <path id="orchTrendLatencyPath" class="orch-trend-latency" d=""></path>
          </svg>
        </div>
      </div>
      <div class="btns">
        <button id="refreshBtn">刷新</button>
        <button id="deepBtn">强制深思</button>
        <button class="secondary" id="dreamBtn">强制梦境回放</button>
      </div>
    </div>
  </div>

  <div class="grid">
    <section class="card">
      <h3>状态</h3>
      <div class="kv" id="stateKv"></div>
      <div class="row">
        <span class="pill ok" id="alivePill">运行中</span>
        <span class="pill warn" id="routePill">路由:-</span>
      </div>
    </section>

    <section class="card">
      <h3>决策</h3>
      <div class="mono" id="decisionText">-</div>
    </section>

    <section class="card">
      <h3>迭代对话</h3>
      <textarea id="iterText" placeholder="输入迭代请求"></textarea>
      <div class="row">
        <button id="iterSendBtn">发送</button>
        <button class="secondary" id="iterUpdateBtn">发送并更新</button>
      </div>
      <div class="status" id="iterStatus">就绪</div>
    </section>

    <section class="card">
      <h3>手动任务注入</h3>
      <textarea id="injectText" placeholder="手动注入问题/任务"></textarea>
      <div class="row">
        <button id="injectBtn">注入</button>
        <button class="secondary" id="injectRunBtn">注入并单次运行</button>
      </div>
      <div class="status" id="injectStatus">就绪</div>
    </section>

    <section class="card">
      <h3>API 桥接</h3>
      <div class="row">
        <select id="apiConnectorSel"></select>
        <button class="secondary" id="apiLoadBtn">加载</button>
        <button class="secondary" id="apiDeleteBtn">删除</button>
      </div>
      <div class="row">
        <input id="apiName" placeholder="连接器名称" />
      </div>
      <div class="row">
        <input id="apiEndpoint" placeholder="接口地址（支持 {{input}} 与 ${ENV_VAR}）" />
      </div>
      <div class="row">
        <select id="apiMethod">
          <option>POST</option>
          <option>GET</option>
          <option>PUT</option>
          <option>PATCH</option>
        </select>
        <input id="apiExtractPath" placeholder="提取路径（如 choices.0.message.content）" />
      </div>
      <textarea id="apiHeaders" placeholder='请求头 JSON，例如 {"Authorization":"Bearer ${OPENAI_API_KEY}","Content-Type":"application/json"}'></textarea>
      <textarea id="apiBody" placeholder='请求体 JSON 模板，例如 {"model":"gpt-4o-mini","messages":[{"role":"user","content":"{{input}}"}]}'></textarea>
      <textarea id="apiQuery" placeholder="要发送给外部 API 的输入"></textarea>
      <div class="row">
        <button id="apiCallBtn">调用并注入</button>
        <button class="secondary" id="apiCallRunBtn">调用注入并运行</button>
        <button class="secondary" id="apiSaveBtn">保存连接器</button>
      </div>
      <div class="status" id="apiStatus">就绪</div>
      <div class="mono" id="apiPreview">-</div>
    </section>

    <section class="card">
      <h3>MCP 桥接</h3>
      <div class="row">
        <select id="mcpConnectorSel"></select>
        <button class="secondary" id="mcpLoadBtn">加载</button>
        <button class="secondary" id="mcpDeleteBtn">删除</button>
      </div>
      <div class="row">
        <input id="mcpName" placeholder="MCP 连接器名称" />
      </div>
      <div class="row">
        <input id="mcpCommand" placeholder="命令，例如 docker 或 npx" />
      </div>
      <textarea id="mcpArgs" placeholder='参数 JSON 数组，例如 ["run","-i","--rm","-e","GITHUB_PERSONAL_ACCESS_TOKEN","ghcr.io/github/github-mcp-server"]'></textarea>
      <textarea id="mcpEnv" placeholder='环境变量 JSON，例如 {"GITHUB_PERSONAL_ACCESS_TOKEN":"${GITHUB_PERSONAL_ACCESS_TOKEN}"}'></textarea>
      <div class="row">
        <input id="mcpCwd" placeholder="可选 CWD" />
        <input id="mcpTimeout" placeholder="timeout 秒（默认 45）" />
      </div>
      <div class="row">
        <input id="mcpToolName" placeholder="工具名（tool_name），例如 search_repositories" />
      </div>
      <textarea id="mcpToolArgs" placeholder='工具参数 JSON，例如 {"query":"{{input}}","perPage":5}'></textarea>
      <textarea id="mcpQuery" placeholder="查询词（会替换 {{input}}）"></textarea>
      <div class="row">
        <button id="mcpListToolsBtn">列出工具</button>
        <button class="secondary" id="mcpCallInjectBtn">调用注入并运行</button>
        <button class="secondary" id="mcpCallOnlyBtn">仅调用</button>
        <button class="secondary" id="mcpSaveBtn">保存 MCP</button>
        <button class="secondary" id="mcpSyncPresetsBtn">同步 Awesome 预设</button>
      </div>
      <div class="status" id="mcpStatus">就绪</div>
      <div class="mono" id="mcpPreview">-</div>
    </section>

    <section class="card">
      <h3>协议流</h3>
      <div class="mono" id="protocolText">-</div>
    </section>

    <section class="card">
      <h3>任务调度单</h3>
      <div class="mono" id="dispatchText">-</div>
    </section>

    <section class="card">
      <h3>外部摘要</h3>
      <div class="mono" id="externalText">-</div>
    </section>

    <section class="card">
      <h3>深度工作流</h3>
      <div class="mono" id="deepWorkerText">-</div>
    </section>

    <section class="card">
      <h3>梦境回放流</h3>
      <div class="mono" id="dreamWorkerText">-</div>
    </section>

    <section class="card">
      <h3>记忆系统</h3>
      <div class="mono" id="memoryText">-</div>
    </section>

    <section class="card">
      <h3>认知 OS v0.1</h3>
      <div class="mono" id="cogV0Text">-</div>
    </section>

    <section class="card">
      <h3>模型编排内核</h3>
      <div class="mono" id="orchestrationText">-</div>
    </section>

    <section class="card">
      <h3>技能分层路由</h3>
      <div class="mono" id="skillsRouterText">-</div>
    </section>

    <section class="card">
      <h3>路由策略热更新</h3>
      <div class="row">
        <label for="memoryStrengthSel">记忆强度</label>
        <select id="memoryStrengthSel">
          <option value="conservative">保守</option>
          <option value="balanced">均衡</option>
          <option value="aggressive">激进</option>
        </select>
      </div>
      <textarea id="routingPolicyText" placeholder='{"task_preferences":{"coding":["coder_chain","deep_chain"],"dream":["dream_chain","deep_chain"],"*":["medium_chain","shallow_chain"]},"task_skill_packs":{"dream":["algorithmic-art","generative-art","canvas-design","theme-factory","imagegen","sora"]},"work_memory_strength":"balanced"}'></textarea>
      <div class="row">
        <button id="routingPolicyLoadBtn">读取策略</button>
        <button class="secondary" id="routingPolicySaveBtn">保存策略</button>
      </div>
      <div class="status" id="routingPolicyStatus">就绪</div>
    </section>

    <section class="card">
      <h3>技能白名单分层</h3>
      <textarea id="skillsPolicyText" placeholder='{"enabled_tiers":{"core":true,"experimental":false,"high_risk":false},"max_active":48,"allowlist":{"core":[],"experimental":[],"high_risk":[]},"denylist":[]}'></textarea>
      <div class="row">
        <button id="skillsPolicyLoadBtn">读取技能策略</button>
        <button class="secondary" id="skillsPolicySaveBtn">保存技能策略</button>
      </div>
      <div class="status" id="skillsPolicyStatus">就绪</div>
    </section>

    <section class="card">
      <h3>意识指标</h3>
      <div class="mono" id="consciousText">-</div>
    </section>

    <section class="card">
      <h3>MVCC / 评测门禁</h3>
      <div class="mono" id="guardrailText">-</div>
    </section>

    <section class="card">
      <h3>阿紫碎碎念</h3>
      <div class="mono" id="murmurText">-</div>
    </section>

    <section class="card">
      <h3>思维轨迹</h3>
      <div class="mono" id="trajText">-</div>
    </section>

    <section class="card">
      <h3>叙事 / 后处理 / 原始输出</h3>
      <div class="mono" id="narrativeText">-</div>
    </section>
  </div>
</div>

<script>
async function api(path, options={}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || ('HTTP ' + res.status));
  }
  return await res.json();
}

function setText(id, txt) {
  document.getElementById(id).textContent = txt ?? '-';
}

const crsHistory = [];
const orchSuccessHistory = [];
const orchLatencyHistory = [];

function _clamp01(v) {
  const x = Number(v);
  if (Number.isNaN(x)) { return 0; }
  if (x < 0) { return 0; }
  if (x > 1) { return 1; }
  return x;
}

function _pushCrs(crsValue) {
  const y = _clamp01(crsValue);
  crsHistory.push({t: Date.now(), y});
  if (crsHistory.length > 48) {
    crsHistory.shift();
  }
}

function _crsLampState(crsValue) {
  const v = _clamp01(crsValue);
  if (v >= 0.80) { return {cls: 'green', label: '稳定强'}; }
  if (v >= 0.60) { return {cls: 'yellow', label: '观察中'}; }
  return {cls: 'red', label: '风险高'};
}

function renderCrsHeader(crsValue) {
  const lamp = document.getElementById('crsLamp');
  const text = document.getElementById('crsText');
  const delta = document.getElementById('crsDelta');
  if (!lamp || !text || !delta) { return; }
  if (crsValue === null || crsValue === undefined || Number.isNaN(Number(crsValue))) {
    lamp.className = 'lamp';
    text.textContent = 'CRS -';
    delta.textContent = '趋势: -';
    return;
  }

  const v = _clamp01(crsValue);
  const state = _crsLampState(v);
  lamp.className = `lamp ${state.cls}`;
  text.textContent = `CRS ${v.toFixed(3)} | ${state.label}`;

  if (crsHistory.length >= 2) {
    const d = crsHistory[crsHistory.length - 1].y - crsHistory[0].y;
    const sign = d > 0 ? '+' : '';
    delta.textContent = `趋势: ${sign}${d.toFixed(3)}`;
  } else {
    delta.textContent = '趋势: -';
  }
}

function renderCrsTrend() {
  const pathEl = document.getElementById('crsTrendPath');
  const fillEl = document.getElementById('crsTrendFill');
  if (!pathEl || !fillEl) { return; }

  const w = 228;
  const h = 44;
  const pad = 3;
  const n = crsHistory.length;
  if (n <= 0) {
    pathEl.setAttribute('d', '');
    fillEl.setAttribute('d', '');
    return;
  }

  const points = crsHistory.map((p, i) => {
    const x = (n === 1) ? (w / 2) : (i * (w - 2 * pad) / (n - 1) + pad);
    const y = pad + (1 - _clamp01(p.y)) * (h - 2 * pad);
    return {x, y};
  });

  let line = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
  for (let i = 1; i < points.length; i++) {
    line += ` L ${points[i].x.toFixed(2)} ${points[i].y.toFixed(2)}`;
  }
  pathEl.setAttribute('d', line);

  const last = points[points.length - 1];
  const first = points[0];
  const baseY = h - 1;
  const fill = `${line} L ${last.x.toFixed(2)} ${baseY} L ${first.x.toFixed(2)} ${baseY} Z`;
  fillEl.setAttribute('d', fill);
}

function _clampRange(v, lo, hi) {
  const x = Number(v);
  if (Number.isNaN(x)) { return lo; }
  if (x < lo) { return lo; }
  if (x > hi) { return hi; }
  return x;
}

function _pushOrchestration(orch) {
  const o = orch || {};
  const top = Array.isArray(o.top_groups) && o.top_groups.length > 0 ? (o.top_groups[0] || {}) : {};
  const sr = _clamp01(top.success_rate ?? 0);
  const latency = _clampRange(o.last_latency_ms ?? 0, 0, 12000);
  orchSuccessHistory.push({t: Date.now(), y: sr});
  orchLatencyHistory.push({t: Date.now(), y: latency});
  if (orchSuccessHistory.length > 48) { orchSuccessHistory.shift(); }
  if (orchLatencyHistory.length > 48) { orchLatencyHistory.shift(); }
}

function renderOrchestrationHeader(orch) {
  const textEl = document.getElementById('orchText');
  const metaEl = document.getElementById('orchMeta');
  if (!textEl || !metaEl) { return; }
  const o = orch || {};
  const top = Array.isArray(o.top_groups) && o.top_groups.length > 0 ? (o.top_groups[0] || {}) : {};
  const group = o.last_route_group || top.group || '-';
  const sr = Number(top.success_rate);
  const lastLatency = Number(o.last_latency_ms);
  const succ = Number.isNaN(sr) ? '-' : `${(sr * 100).toFixed(1)}%`;
  const lat = Number.isNaN(lastLatency) ? '-' : `${Math.round(lastLatency)}ms`;
  textEl.textContent = `编排 ${group} 成功率=${succ}`;

  if (orchSuccessHistory.length >= 2) {
    const d = orchSuccessHistory[orchSuccessHistory.length - 1].y - orchSuccessHistory[0].y;
    const sign = d > 0 ? '+' : '';
    metaEl.textContent = `时延: ${lat} | 趋势: ${sign}${(d * 100).toFixed(1)}%`;
  } else {
    metaEl.textContent = `时延: ${lat} | 趋势: -`;
  }
}

function renderOrchestrationTrend() {
  const succPath = document.getElementById('orchTrendSuccessPath');
  const latPath = document.getElementById('orchTrendLatencyPath');
  if (!succPath || !latPath) { return; }
  const w = 228;
  const h = 44;
  const pad = 3;

  const drawPath = (arr, normFn) => {
    const n = arr.length;
    if (n <= 0) { return ''; }
    const points = arr.map((p, i) => {
      const x = (n === 1) ? (w / 2) : (i * (w - 2 * pad) / (n - 1) + pad);
      const yv = _clamp01(normFn(p.y));
      const y = pad + (1 - yv) * (h - 2 * pad);
      return {x, y};
    });
    let d = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
    for (let i = 1; i < points.length; i++) {
      d += ` L ${points[i].x.toFixed(2)} ${points[i].y.toFixed(2)}`;
    }
    return d;
  };

  const succD = drawPath(orchSuccessHistory, (v) => v);
  const latD = drawPath(orchLatencyHistory, (v) => 1 - Math.min(Number(v) / 5000, 1));
  succPath.setAttribute('d', succD);
  latPath.setAttribute('d', latD);
}

function kvHtml(state) {
  const rows = [
    ['周期', state.cycle], ['能量', state.energy], ['压力', state.stress], ['不确定性', state.uncertainty],
    ['完整性', state.integrity], ['连续性', state.continuity], ['MVCC', state.mvcc_version], ['权限级别', state.permission_level], ['最近事件ID', state.last_event_id]
  ];
  return rows.map(([k,v]) => `<div class="k">${k}</div><div>${v ?? '-'}</div>`).join('');
}

function fmtProtocol(p) {
  const lines = [];
  lines.push('[任务]');
  (p.tasks || []).forEach(x => lines.push(`- ${x}`));
  lines.push('\\n[证据]');
  (p.evidences || []).forEach(x => lines.push(`- ${x}`));
  lines.push('\\n[提案]');
  (p.proposals || []).forEach(x => lines.push(`- ${x}`));
  return lines.join('\\n');
}

function fmtDispatch(d) {
  const x = d || {};
  const lines = [];
  lines.push(`[识别] ${x.issue_detected ? '需要干活' : '暂不执行'} | 原因=${x.issue_reason || '-'}`);
  lines.push(`[意图] ${x.intent || '-'}`);
  lines.push(`[任务类型] ${x.task_type || '-'} | 风险=${x.risk_level || '-'} | 置信=${x.confidence ?? '-'}`);
  lines.push('\\n[调度任务单]');
  (x.dispatch_plan || []).forEach((t, idx) => {
    lines.push(`- #${idx + 1} worker=${t.worker || '-'} group=${t.model_group || '-'} tool=${t.tool || '-'}`);
    lines.push(`  input=${t.input || '-'} | expected=${t.expected_output || '-'} | timeout=${t.timeout_sec || 0}s | reversible=${!!t.reversible}`);
  });
  if ((x.dispatch_plan || []).length === 0) {
    lines.push('- 无');
  }
  lines.push('\\n[Dream 专用技能包]');
  (x.recommended_skills || []).forEach(s => lines.push(`- ${s}`));
  if ((x.recommended_skills || []).length === 0) {
    lines.push('- 无');
  }
  lines.push('\\n[成功标准]');
  (x.success_criteria || []).forEach(s => lines.push(`- ${s}`));
  lines.push(`\\n[回滚] ${x.rollback_plan || '-'}`);
  return lines.join('\\n');
}

function fmtSkillsRouter(s) {
  const x = s || {};
  const p = x.policy || {};
  const tiers = (p.enabled_tiers || {});
  const lines = [];
  lines.push('[总览]');
  lines.push(`已安装=${x.installed_total ?? 0} | 激活=${x.active_total ?? 0} | 静音=${x.muted_total ?? 0}`);
  lines.push(`启用层: core=${!!tiers.core} experimental=${!!tiers.experimental} high_risk=${!!tiers.high_risk}`);
  lines.push(`最大激活数: ${p.max_active ?? '-'}`);
  const tc = x.tier_counts || {};
  lines.push(`分层计数: core=${tc.core ?? 0} experimental=${tc.experimental ?? 0} high_risk=${tc.high_risk ?? 0}`);
  lines.push('\\n[激活样本]');
  (x.active_skills || []).slice(0, 20).forEach(k => lines.push(`- ${k}`));
  if ((x.active_skills || []).length === 0) {
    lines.push('- 无');
  }
  return lines.join('\\n');
}

function fmtExternal(e) {
  const alias = {
    'Autoweb': '自动网页',
    'File Feed': '文件投喂',
    'Social': '社交桥',
    'API Bridge': 'API 桥接',
    'Fact Lane': '事实通道',
    'Risk Gate': '风险闸门',
    'Guard': '守护器',
    'Deep Worker': '深度工作器',
    'Deep Release': '深度发布',
    'Dream Worker': '梦境工作器',
    'Dream': '梦境输出',
    'Dream Release': '梦境发布',
  };
  const lines = [];
  for (const k of Object.keys(e || {})) {
    lines.push(`${alias[k] || k}: ${e[k]}`);
  }
  return lines.join('\\n');
}

function fmtGuardrails(g) {
  const lines = [];
  lines.push(`[状态版本] ${g.state_version ?? '-'}`);
  lines.push('\\n[提交窗口]');
  (g.commit_windows || []).forEach(x => lines.push(`- ${x}`));
  lines.push('\\n[评测门禁]');
  (g.eval_gates || []).forEach(x => lines.push(`- ${x}`));
  return lines.join('\\n');
}

function fmtMurmur(m) {
  const lines = [];
  lines.push('[感想]');
  lines.push(m.reflection || '-');
  lines.push('\\n[最近]');
  (m.latest || []).forEach(x => lines.push(`- ${x}`));
  return lines.join('\\n');
}

function fmtMemorySystem(m) {
  const mem = m || {};
  const factTiers = mem.fact_tiers || {};
  const vectorTiers = mem.vector_tiers || {};
  const lines = [];
  lines.push('[统计]');
  lines.push(`事实条目=${mem.facts ?? 0}`);
  lines.push(`冲突条目=${mem.conflicts ?? 0}`);
  lines.push(`向量条目=${mem.vectors ?? 0}`);
  lines.push(`来源可信度条目=${mem.source_trust ?? 0}`);
  lines.push(`因果边条目=${mem.causal_edges ?? 0}`);
  lines.push('\\n[事实分层]');
  lines.push(`- 热: ${factTiers.hot ?? 0}`);
  lines.push(`- 温: ${factTiers.warm ?? 0}`);
  lines.push(`- 冷: ${factTiers.cold ?? 0}`);
  lines.push(`- 归档: ${factTiers.archive ?? 0}`);
  lines.push('\\n[向量分层]');
  lines.push(`- 热: ${vectorTiers.hot ?? 0}`);
  lines.push(`- 温: ${vectorTiers.warm ?? 0}`);
  lines.push(`- 冷: ${vectorTiers.cold ?? 0}`);
  lines.push(`- 归档: ${vectorTiers.archive ?? 0}`);
  return lines.join('\\n');
}

function _fmtCount(v) {
  if (v === -1) { return '超大'; }
  if (v === null || v === undefined || v === '') { return '-'; }
  return String(v);
}

function _yesNo(v) {
  return v ? '已启用' : '缺失';
}

function fmtCognitiveV0(v) {
  const x = v || {};
  const lines = [];
  lines.push('[核心能力]');
  lines.push(`单次结构化输出(intent+risk+draft+plan): ${_yesNo((x.structured_output || {}).enabled)} @ ${(x.structured_output || {}).file || '-'}`);
  lines.push(`沙盒+人工确认+草稿可编辑: ${_yesNo((x.sandbox_confirm_edit || {}).enabled)} @ ${(x.sandbox_confirm_edit || {}).file || '-'}`);
  lines.push('\\n[数据文件]');
  lines.push(`reflections.jsonl: ${_fmtCount((x.reflections || {}).records)}`);
  lines.push(`execution_trace.jsonl: ${_fmtCount((x.execution_trace || {}).records)}`);
  lines.push(`gold_tasks.json: ${_fmtCount((x.gold_tasks || {}).count)}`);
  lines.push(`regression_set.jsonl: ${_fmtCount((x.regression_set || {}).records)}`);
  lines.push('\\n[指标]');
  lines.push(`金标命中率: ${(x.stats || {}).gold_hit_rate ?? '-'}`);
  lines.push(`总运行次数: ${(x.stats || {}).total_runs ?? '-'}`);
  lines.push(`回归已解决: ${(x.replay_report || {}).resolved ?? '-'} / ${(x.replay_report || {}).total ?? '-'}`);
  lines.push('\\n[命令]');
  lines.push(`- ${(x.commands || {}).stats || 'python stats_report.py'}`);
  lines.push(`- ${(x.commands || {}).replay || 'python replay_regression.py --limit 20'}`);
  return lines.join('\\n');
}

function fmtOrchestration(o, wm) {
  const x = o || {};
  const memory = wm || {};
  const strengthMap = {conservative: '保守', balanced: '均衡', aggressive: '激进'};
  const lines = [];
  lines.push('[最近路由]');
  lines.push(`任务类型: ${x.last_task_type ?? '-'}`);
  lines.push(`路由组: ${x.last_route_group ?? '-'}`);
  lines.push(`路由原因: ${x.last_route_reason ?? '-'}`);
  lines.push(`Provider/Model: ${(x.last_provider ?? '-')}/${(x.last_model ?? '-')}`);
  lines.push(`时延(ms): ${x.last_latency_ms ?? '-'}`);
  lines.push(`估算成本(USD): ${x.last_cost_usd ?? '-'}`);
  if (x.last_error) {
    lines.push(`最近错误: ${x.last_error}`);
  }
  lines.push('\\n[Top 路由组]');
  (x.top_groups || []).forEach(g => {
    lines.push(`- ${g.group}: 成功率=${g.success_rate} 总次数=${g.total} 时延EMA=${g.latency_ms_ema}ms`);
  });
  lines.push('\\n[Top 模型]');
  (x.top_models || []).forEach(m => {
    lines.push(`- ${m.model_key}: 成功率=${m.success_rate} 总次数=${m.total}`);
  });
  lines.push('\\n[任务->路由统计]');
  const trs = x.task_route_stats || {};
  Object.keys(trs).forEach(k => {
    const row = trs[k] || {};
    const parts = Object.keys(row).map(g => `${g}:${row[g]}`);
    lines.push(`- ${k}: ${parts.join(', ') || '-'}`);
  });
  lines.push('\\n[工作记忆偏好]');
  lines.push(`记忆强度: ${strengthMap[memory.strength] || memory.strength || '均衡'}`);
  (memory.top_preferences || []).forEach(p => {
    const groups = (p.preferred_groups || []).join(' > ') || '-';
    lines.push(`- ${p.task_type || '-'}: ${groups}`);
  });
  if ((memory.top_preferences || []).length === 0) {
    lines.push('- 暂无稳定偏好（持续执行后自动形成）');
  }
  return lines.join('\\n');
}

function fmtConsciousness(c) {
  const x = c || {};
  const m = x.metrics || {};
  const e = x.evidence || {};
  const bandMap = {
    'proto-agent': '原型代理',
    'stable-workflow': '稳定工作流',
    'reflective-candidate': '反思自治候选',
    'high-confidence-proxy': '高置信工程代理',
    'error': '错误',
  };
  const lines = [];
  lines.push(`[等级] ${bandMap[x.band] || x.band || '-'}`);
  lines.push(`[CRS] ${x.CRS ?? '-'}`);
  lines.push('\\n[分项指标]');
  ['SCI', 'MCS', 'GAR', 'SCR', 'RLY', 'MRI'].forEach(k => {
    lines.push(`- ${k}: ${m[k] ?? '-'}`);
  });
  lines.push('\\n[证据]');
  lines.push(`- 决策数: ${((e.GAR || {}).decisions ?? '-')}`);
  lines.push(`- 有证据决策数: ${((e.GAR || {}).grounded ?? '-')}`);
  lines.push(`- 事实/冲突: ${((e.MCS || {}).facts ?? '-')}/${((e.MCS || {}).conflicts ?? '-')}`);
  lines.push(`- 深思完成率: ${((e.RLY || {}).deep_completion ?? '-')}`);
  lines.push(`- 梦境完成率: ${((e.RLY || {}).dream_completion ?? '-')}`);
  lines.push(`- MCP 调用/注入: ${((e.MRI || {}).calls ?? '-')}/${((e.MRI || {}).injected ?? '-')}`);
  return lines.join('\\n');
}

function _metaShort(meta) {
  const m = meta || {};
  const parts = [];
  const keys = ['provider', 'model', 'live_api', 'mode', 'commit_status', 'status', 'parent_event_id'];
  keys.forEach(k => {
    if (Object.prototype.hasOwnProperty.call(m, k) && m[k] !== null && String(m[k]) !== '') {
      parts.push(`${k}=${m[k]}`);
    }
  });
  if (m.commit_window && m.commit_window.status) {
    parts.push(`mvcc=${m.commit_window.status}`);
  }
  return parts.join(' | ');
}

function _fmtEventItem(title, item) {
  if (!item) { return `${title}: -`; }
  const ts = item.ts ? String(item.ts).slice(-8) : '-';
  const etype = item.event_type || '-';
  const content = String(item.content || '-');
  const lines = [`${title}: [${ts}] ${etype} ${content}`];
  const meta = _metaShort(item.meta || {});
  if (meta) {
    lines.push(`  元数据: ${meta}`);
  }
  return lines.join('\\n');
}

function _fmtDecisionItem(item) {
  if (!item) { return '决策: -'; }
  const ts = item.ts ? String(item.ts).slice(-8) : '-';
  const action = item.action || '-';
  const summary = String(item.summary || '-');
  const lines = [`决策: [${ts}] 动作=${action} ${summary}`];
  const meta = _metaShort(item.meta || {});
  if (meta) {
    lines.push(`  元数据: ${meta}`);
  }
  return lines.join('\\n');
}

function _fmtEvalItem(item) {
  if (!item || !item.payload) { return '评测: -'; }
  const ts = item.ts ? String(item.ts).slice(-8) : '-';
  const p = item.payload || {};
  const scoreRaw = p.score;
  const score = (typeof scoreRaw === 'number') ? scoreRaw.toFixed(2) : (scoreRaw ?? '-');
  const passVal = (p.pass !== undefined) ? p.pass : p.pass_flag;
  return `评测: [${ts}] 套件=${p.suite ?? '-'} 分数=${score} 通过=${passVal ?? '-'} 回归=${p.regression ?? '-'}`;
}

function _fmtRewardItem(item) {
  if (!item || !item.payload) { return '奖励: -'; }
  const ts = item.ts ? String(item.ts).slice(-8) : '-';
  const p = item.payload || {};
  return `奖励: [${ts}] 角色=${p.actor_id ?? '-'} 声誉 ${p.rep_before ?? '-'} -> ${p.rep_after ?? '-'} (Δ=${p.delta ?? '-'})`;
}

function fmtDeepDream(block, label) {
  if (!block) { return '-'; }
  const zh = (label === 'deep') ? '深思' : '梦境';
  const lines = [];
  lines.push(`[${zh}]`);
  lines.push(_fmtEventItem('请求', block.request));
  lines.push(_fmtEventItem('输出', block.output));
  lines.push(_fmtEventItem('发布', block.release));
  if (label === 'deep') {
    lines.push(_fmtEventItem('阻断', block.blocked));
    lines.push(_fmtEventItem('追踪', block.trace));
  }
  lines.push(_fmtDecisionItem(block.decision));
  lines.push(_fmtEvalItem(block.eval));
  lines.push(_fmtRewardItem(block.reward));
  lines.push('\\n[最近]');
  const recent = Array.isArray(block.recent) ? block.recent : [];
  if (recent.length === 0) {
    lines.push('-');
  } else {
    recent.forEach(x => lines.push(`- ${x}`));
  }
  return lines.join('\\n');
}

function parseJsonText(txt, fallback) {
  const raw = (txt || '').trim();
  if (!raw) { return fallback; }
  try {
    return JSON.parse(raw);
  } catch (e) {
    throw new Error('JSON 解析失败: ' + e.message);
  }
}

let connectorCache = [];
let mcpConnectorCache = [];

async function loadRoutingPolicy() {
  try {
    const res = await api('/api/routing-policy');
    const p = (res && res.routing_policy) ? res.routing_policy : {task_preferences: {}};
    const strength = String(p.work_memory_strength || 'balanced');
    const sel = document.getElementById('memoryStrengthSel');
    if (sel) { sel.value = strength; }
    document.getElementById('routingPolicyText').value = JSON.stringify(p, null, 2);
    setText('routingPolicyStatus', `策略已加载 @ ${res.updated_at || '-'}`);
  } catch (e) {
    setText('routingPolicyStatus', '读取策略失败: ' + e.message);
  }
}

async function saveRoutingPolicy() {
  try {
    const txt = (document.getElementById('routingPolicyText').value || '').trim();
    if (!txt) {
      setText('routingPolicyStatus', '请先填写 JSON');
      return;
    }
    const routing_policy = parseJsonText(txt, {});
    const strengthSel = document.getElementById('memoryStrengthSel');
    const strength = String((strengthSel && strengthSel.value) ? strengthSel.value : 'balanced');
    routing_policy.work_memory_strength = strength;
    const res = await api('/api/routing-policy/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({routing_policy})
    });
    setText('routingPolicyStatus', `${res.message || '已保存'} @ ${res.updated_at || '-'}`);
    document.getElementById('routingPolicyText').value = JSON.stringify(res.routing_policy || routing_policy, null, 2);
  } catch (e) {
    setText('routingPolicyStatus', '保存策略失败: ' + e.message);
  }
}

async function loadSkillsPolicy() {
  try {
    const res = await api('/api/skills-policy');
    const p = (res && res.skills_policy) ? res.skills_policy : {};
    document.getElementById('skillsPolicyText').value = JSON.stringify(p, null, 2);
    setText('skillsPolicyStatus', `技能策略已加载 @ ${res.updated_at || '-'}`);
  } catch (e) {
    setText('skillsPolicyStatus', '读取技能策略失败: ' + e.message);
  }
}

async function saveSkillsPolicy() {
  try {
    const txt = (document.getElementById('skillsPolicyText').value || '').trim();
    if (!txt) {
      setText('skillsPolicyStatus', '请先填写 JSON');
      return;
    }
    const skills_policy = parseJsonText(txt, {});
    const res = await api('/api/skills-policy/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({skills_policy})
    });
    setText('skillsPolicyStatus', `${res.message || '已保存'} @ ${res.updated_at || '-'}`);
    document.getElementById('skillsPolicyText').value = JSON.stringify(res.skills_policy || skills_policy, null, 2);
    await refresh();
  } catch (e) {
    setText('skillsPolicyStatus', '保存技能策略失败: ' + e.message);
  }
}

function escHtml(s) {
  return String(s || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function connectorFromForm() {
  return {
    id: '',
    name: (document.getElementById('apiName').value || '').trim(),
    endpoint: (document.getElementById('apiEndpoint').value || '').trim(),
    method: (document.getElementById('apiMethod').value || 'POST').trim().toUpperCase(),
    extract_path: (document.getElementById('apiExtractPath').value || '').trim(),
    headers: parseJsonText(document.getElementById('apiHeaders').value, {}),
    body_template: parseJsonText(document.getElementById('apiBody').value, {}),
  };
}

function fillConnectorForm(c) {
  if (!c) { return; }
  document.getElementById('apiName').value = c.name || '';
  document.getElementById('apiEndpoint').value = c.endpoint || '';
  document.getElementById('apiMethod').value = (c.method || 'POST').toUpperCase();
  document.getElementById('apiExtractPath').value = c.extract_path || '';
  document.getElementById('apiHeaders').value = JSON.stringify(c.headers || {}, null, 2);
  document.getElementById('apiBody').value = JSON.stringify(c.body_template || {}, null, 2);
}

function selectedConnectorId() {
  return (document.getElementById('apiConnectorSel').value || '').trim();
}

function refreshConnectorSelector() {
  const sel = document.getElementById('apiConnectorSel');
  const current = sel.value || '';
  const opts = ['<option value="">(临时配置)</option>'];
  connectorCache.forEach(c => {
    const label = `${c.name || c.id || '-'} | ${(c.method || 'POST').toUpperCase()}`;
    opts.push(`<option value="${escHtml(c.id)}">${escHtml(label)}</option>`);
  });
  sel.innerHTML = opts.join('');
  if (current && connectorCache.some(c => c.id === current)) {
    sel.value = current;
  }
}

async function loadConnectors() {
  try {
    const res = await api('/api/connectors');
    connectorCache = Array.isArray(res.connectors) ? res.connectors : [];
    refreshConnectorSelector();
    setText('apiStatus', `连接器数量: ${connectorCache.length}`);
  } catch (e) {
    setText('apiStatus', '加载连接器失败: ' + e.message);
  }
}

async function saveConnector() {
  try {
    const connector = connectorFromForm();
    if (!connector.name || !connector.endpoint) {
      setText('apiStatus', 'name 和 endpoint 必填');
      return;
    }
    const res = await api('/api/connectors/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({connector})
    });
    setText('apiStatus', res.message || '连接器已保存');
    await loadConnectors();
    if (res.id) {
      document.getElementById('apiConnectorSel').value = res.id;
    }
  } catch (e) {
    setText('apiStatus', '保存失败: ' + e.message);
  }
}

function loadSelectedConnectorToForm() {
  const id = selectedConnectorId();
  if (!id) {
    setText('apiStatus', '当前为临时配置');
    return;
  }
  const found = connectorCache.find(x => x.id === id);
  if (!found) {
    setText('apiStatus', '未找到连接器');
    return;
  }
  fillConnectorForm(found);
  setText('apiStatus', `已加载: ${found.name || found.id}`);
}

async function deleteSelectedConnector() {
  const id = selectedConnectorId();
  if (!id) {
    setText('apiStatus', '请选择要删除的连接器');
    return;
  }
  try {
    const res = await api('/api/connectors/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({connector_id: id})
    });
    setText('apiStatus', `已删除: ${res.removed || 0}`);
    await loadConnectors();
  } catch (e) {
    setText('apiStatus', '删除失败: ' + e.message);
  }
}

async function callConnector(runOnce=false) {
  try {
    const query = (document.getElementById('apiQuery').value || '').trim();
    if (!query) {
      setText('apiStatus', '请输入 API 查询');
      return;
    }
    const id = selectedConnectorId();
    const body = {
      connector_id: id,
      connector: connectorFromForm(),
      query,
      run_once: !!runOnce
    };
    const res = await api('/api/connector-call', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    setText('apiStatus', res.message || '已调用并注入');
    setText('apiPreview', (res.extracted || res.response_preview || '-'));
    await refresh();
  } catch (e) {
    setText('apiStatus', 'API 调用失败: ' + e.message);
  }
}

function mcpConnectorFromForm() {
  return {
    id: '',
    name: (document.getElementById('mcpName').value || '').trim(),
    command: (document.getElementById('mcpCommand').value || '').trim(),
    args: parseJsonText(document.getElementById('mcpArgs').value, []),
    env: parseJsonText(document.getElementById('mcpEnv').value, {}),
    cwd: (document.getElementById('mcpCwd').value || '').trim(),
    timeout_sec: parseFloat((document.getElementById('mcpTimeout').value || '45').trim() || '45'),
  };
}

function fillMcpConnectorForm(c) {
  if (!c) { return; }
  document.getElementById('mcpName').value = c.name || '';
  document.getElementById('mcpCommand').value = c.command || '';
  document.getElementById('mcpArgs').value = JSON.stringify(c.args || [], null, 2);
  document.getElementById('mcpEnv').value = JSON.stringify(c.env || {}, null, 2);
  document.getElementById('mcpCwd').value = c.cwd || '';
  document.getElementById('mcpTimeout').value = String(c.timeout_sec || 45);
}

function selectedMcpConnectorId() {
  return (document.getElementById('mcpConnectorSel').value || '').trim();
}

function refreshMcpConnectorSelector() {
  const sel = document.getElementById('mcpConnectorSel');
  const current = sel.value || '';
  const opts = ['<option value="">(临时 MCP 配置)</option>'];
  mcpConnectorCache.forEach(c => {
    const label = `${c.name || c.id || '-'} | ${c.command || '-'}`;
    opts.push(`<option value="${escHtml(c.id)}">${escHtml(label)}</option>`);
  });
  sel.innerHTML = opts.join('');
  if (current && mcpConnectorCache.some(c => c.id === current)) {
    sel.value = current;
  }
}

async function loadMcpConnectors() {
  try {
    const res = await api('/api/mcp/connectors');
    mcpConnectorCache = Array.isArray(res.connectors) ? res.connectors : [];
    refreshMcpConnectorSelector();
    setText('mcpStatus', `MCP 连接器数量: ${mcpConnectorCache.length}`);
  } catch (e) {
    setText('mcpStatus', '加载 MCP 连接器失败: ' + e.message);
  }
}

async function syncMcpAwesomePresets() {
  try {
    const res = await api('/api/mcp/connectors/sync-presets', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({})
    });
    await loadMcpConnectors();
    setText('mcpStatus', `Awesome 预设已同步 | 新增=${res.added || 0} 总数=${res.total || 0}`);
  } catch (e) {
    setText('mcpStatus', '同步 MCP 预设失败: ' + e.message);
  }
}

function loadSelectedMcpConnectorToForm() {
  const id = selectedMcpConnectorId();
  if (!id) {
    setText('mcpStatus', '当前为临时 MCP 配置');
    return;
  }
  const found = mcpConnectorCache.find(x => x.id === id);
  if (!found) {
    setText('mcpStatus', '未找到 MCP 连接器');
    return;
  }
  fillMcpConnectorForm(found);
  setText('mcpStatus', `已加载 MCP: ${found.name || found.id}`);
}

async function saveMcpConnector() {
  try {
    const connector = mcpConnectorFromForm();
    if (!connector.name || !connector.command) {
      setText('mcpStatus', 'MCP 名称和命令必填');
      return;
    }
    const res = await api('/api/mcp/connectors/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({connector})
    });
    setText('mcpStatus', res.message || 'MCP 连接器已保存');
    await loadMcpConnectors();
    if (res.id) {
      document.getElementById('mcpConnectorSel').value = res.id;
    }
  } catch (e) {
    setText('mcpStatus', '保存 MCP 失败: ' + e.message);
  }
}

async function deleteSelectedMcpConnector() {
  const id = selectedMcpConnectorId();
  if (!id) {
    setText('mcpStatus', '请选择要删除的 MCP 连接器');
    return;
  }
  try {
    const res = await api('/api/mcp/connectors/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({connector_id: id})
    });
    setText('mcpStatus', `MCP 已删除: ${res.removed || 0}`);
    await loadMcpConnectors();
  } catch (e) {
    setText('mcpStatus', '删除 MCP 失败: ' + e.message);
  }
}

async function listMcpTools() {
  try {
    const query = (document.getElementById('mcpQuery').value || '').trim();
    const body = {
      connector_id: selectedMcpConnectorId(),
      connector: mcpConnectorFromForm(),
      query
    };
    const res = await api('/api/mcp/list-tools', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    setText('mcpStatus', `${res.message || '工具列表已加载'} | 数量=${res.tool_count ?? 0}`);
    setText('mcpPreview', JSON.stringify((res.tools || []), null, 2));
  } catch (e) {
    setText('mcpStatus', '列出 MCP 工具失败: ' + e.message);
  }
}

async function callMcpTool(inject=true, runOnce=false) {
  try {
    const toolName = (document.getElementById('mcpToolName').value || '').trim();
    if (!toolName) {
      setText('mcpStatus', '请输入 tool_name');
      return;
    }
    const query = (document.getElementById('mcpQuery').value || '').trim();
    const toolArgs = parseJsonText(document.getElementById('mcpToolArgs').value, {});
    const body = {
      connector_id: selectedMcpConnectorId(),
      connector: mcpConnectorFromForm(),
      tool_name: toolName,
      tool_args: toolArgs,
      query,
      inject: !!inject,
      run_once: !!runOnce
    };
    const res = await api('/api/mcp/call-tool', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    });
    setText('mcpStatus', res.message || 'MCP 已调用');
    setText('mcpPreview', res.extracted || JSON.stringify(res.result || {}, null, 2));
    if (inject) {
      await refresh();
    }
  } catch (e) {
    setText('mcpStatus', 'MCP 调用失败: ' + e.message);
  }
}

async function refresh() {
  try {
    const data = await api('/api/snapshot');
    setText('updatedAt', `更新时间: ${data.updated_at || '-'}`);
    document.getElementById('stateKv').innerHTML = kvHtml(data.state || {});
    const route = ((data.orchestration || {}).last_route_group || ((data.skill_specialist && data.skill_specialist.active)
      ? `${data.skill_specialist.domain}->${data.skill_specialist.expert_module}`
      : '-'));
    document.getElementById('routePill').textContent = `路由:${route}`;
    setText('decisionText', data.decision_text || '-');
    setText('protocolText', fmtProtocol(data.protocol || {}));
    setText('dispatchText', fmtDispatch(data.dispatch || {}));
    setText('externalText', fmtExternal(data.external || {}));
    setText('deepWorkerText', fmtDeepDream((data.deep_dream || {}).deep || {}, 'deep'));
    setText('dreamWorkerText', fmtDeepDream((data.deep_dream || {}).dream || {}, 'dream'));
    setText('memoryText', fmtMemorySystem(data.memory_system || {}));
    setText('cogV0Text', fmtCognitiveV0(data.cognitive_v0 || {}));
    setText('skillsRouterText', fmtSkillsRouter(data.skills_router || {}));
    const orchestration = data.orchestration || {};
    const workMemory = data.work_memory || {};
    setText('orchestrationText', fmtOrchestration(orchestration, workMemory));
    _pushOrchestration(orchestration);
    renderOrchestrationHeader(orchestration);
    renderOrchestrationTrend();
    const conscious = data.consciousness || {};
    setText('consciousText', fmtConsciousness(conscious));
    const crsValue = Number(conscious.CRS);
    if (!Number.isNaN(crsValue)) {
      _pushCrs(crsValue);
      renderCrsHeader(crsValue);
      renderCrsTrend();
    } else {
      renderCrsHeader(null);
      renderCrsTrend();
    }
    setText('guardrailText', fmtGuardrails(data.guardrails || {}));
    setText('murmurText', fmtMurmur(data.murmur || {}));
    setText('trajText', (data.trajectory || []).join('\\n') || '-');
    setText('narrativeText', data.narrative_bundle || '-');
  } catch (e) {
    setText('updatedAt', '刷新失败: ' + e.message);
    renderCrsHeader(null);
  }
}

async function sendInject(runOnce=false) {
  const text = document.getElementById('injectText').value.trim();
  if (!text) { setText('injectStatus', '请输入内容'); return; }
  try {
    const res = await api('/api/inject', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text, run_once: !!runOnce})
    });
    setText('injectStatus', res.message || '已注入');
    document.getElementById('injectText').value = '';
    await refresh();
  } catch (e) {
    setText('injectStatus', '失败: ' + e.message);
  }
}

async function sendIteration(triggerUpdate=false) {
  const text = document.getElementById('iterText').value.trim();
  if (!text) { setText('iterStatus', '请输入迭代需求'); return; }
  try {
    const res = await api('/api/iteration', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text, trigger_update: !!triggerUpdate})
    });
    setText('iterStatus', res.message || '已入队');
    document.getElementById('iterText').value = '';
    await refresh();
  } catch (e) {
    setText('iterStatus', '失败: ' + e.message);
  }
}

async function forceDeep() {
  try {
    const res = await api('/api/force-deep', {method: 'POST'});
    setText('updatedAt', res.message || '已请求深思');
    await refresh();
  } catch (e) {
    setText('updatedAt', '强制深思失败: ' + e.message);
  }
}

async function forceDream() {
  try {
    const res = await api('/api/force-dream', {method: 'POST'});
    setText('updatedAt', res.message || '已请求梦境回放');
    await refresh();
  } catch (e) {
    setText('updatedAt', '强制梦境回放失败: ' + e.message);
  }
}

document.getElementById('refreshBtn').addEventListener('click', refresh);
document.getElementById('deepBtn').addEventListener('click', forceDeep);
document.getElementById('dreamBtn').addEventListener('click', forceDream);
document.getElementById('injectBtn').addEventListener('click', () => sendInject(false));
document.getElementById('injectRunBtn').addEventListener('click', () => sendInject(true));
document.getElementById('iterSendBtn').addEventListener('click', () => sendIteration(false));
document.getElementById('iterUpdateBtn').addEventListener('click', () => sendIteration(true));
document.getElementById('apiLoadBtn').addEventListener('click', loadSelectedConnectorToForm);
document.getElementById('apiDeleteBtn').addEventListener('click', deleteSelectedConnector);
document.getElementById('apiSaveBtn').addEventListener('click', saveConnector);
document.getElementById('apiCallBtn').addEventListener('click', () => callConnector(false));
document.getElementById('apiCallRunBtn').addEventListener('click', () => callConnector(true));
document.getElementById('mcpLoadBtn').addEventListener('click', loadSelectedMcpConnectorToForm);
document.getElementById('mcpDeleteBtn').addEventListener('click', deleteSelectedMcpConnector);
document.getElementById('mcpSaveBtn').addEventListener('click', saveMcpConnector);
document.getElementById('mcpListToolsBtn').addEventListener('click', listMcpTools);
document.getElementById('mcpCallInjectBtn').addEventListener('click', () => callMcpTool(true, true));
document.getElementById('mcpCallOnlyBtn').addEventListener('click', () => callMcpTool(false, false));
document.getElementById('mcpSyncPresetsBtn').addEventListener('click', syncMcpAwesomePresets);
document.getElementById('routingPolicyLoadBtn').addEventListener('click', loadRoutingPolicy);
document.getElementById('routingPolicySaveBtn').addEventListener('click', saveRoutingPolicy);
document.getElementById('skillsPolicyLoadBtn').addEventListener('click', loadSkillsPolicy);
document.getElementById('skillsPolicySaveBtn').addEventListener('click', saveSkillsPolicy);
refresh();
loadConnectors();
loadMcpConnectors();
loadRoutingPolicy();
loadSkillsPolicy();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


class BrainWebApp:
    def __init__(self, base_dir: Path, db_path: Path, state_path: Path) -> None:
        self.base_dir = base_dir
        self.db_path = db_path
        self.state_path = state_path
        self.connector_service = PanelConnectorService(base_dir, db_path, state_path)
        self._connector_remote_delegate = self.connector_service._call_remote

    def list_connectors(self) -> dict[str, Any]:
        return self.connector_service.list_connectors()

    def save_connector(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.connector_service.save_connector(payload)

    def delete_connector(self, connector_id: str) -> dict[str, Any]:
        return self.connector_service.delete_connector(connector_id)

    def list_mcp_connectors(self) -> dict[str, Any]:
        return self.connector_service.list_mcp_connectors()

    def sync_mcp_presets(self) -> dict[str, Any]:
        return self.connector_service.sync_mcp_presets()

    def save_mcp_connector(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.connector_service.save_mcp_connector(payload)

    def delete_mcp_connector(self, connector_id: str) -> dict[str, Any]:
        return self.connector_service.delete_mcp_connector(connector_id)

    def list_mcp_tools(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.connector_service.list_mcp_tools(payload)

    def call_mcp_tool(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.connector_service._spawn_once = self._spawn_once
        return self.connector_service.call_mcp_tool(payload)

    def call_connector(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.connector_service._spawn_once = self._spawn_once
        self.connector_service._call_remote = self._call_remote
        return self.connector_service.call_connector(payload)

    def _call_remote(self, **kwargs) -> dict[str, Any]:
        return self._connector_remote_delegate(**kwargs)

    def _llm_config_path(self) -> Path:
        return self.base_dir / "llm_config.json"

    @staticmethod
    def _normalize_memory_strength(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"conservative", "保守"}:
            return "conservative"
        if raw in {"aggressive", "激进"}:
            return "aggressive"
        return "balanced"

    def get_routing_policy(self) -> dict[str, Any]:
        path = self._llm_config_path()
        cfg: dict[str, Any] = {}
        try:
            if path.exists() and path.is_file():
                raw = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
                if isinstance(raw, dict):
                    cfg = raw
        except Exception:
            cfg = {}
        policy = cfg.get("routing_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        task_prefs = policy.get("task_preferences", {})
        if not isinstance(task_prefs, dict):
            task_prefs = {}
        task_skill_packs = policy.get("task_skill_packs", {})
        if not isinstance(task_skill_packs, dict):
            task_skill_packs = {}
        normalized_packs: dict[str, list[str]] = {}
        for k, v in task_skill_packs.items():
            key = str(k or "").strip()
            if not key:
                continue
            if isinstance(v, list):
                vals = [str(x).strip() for x in v if str(x).strip()]
            elif isinstance(v, str):
                vals = [x.strip() for x in v.split(",") if x.strip()]
            else:
                vals = []
            normalized_packs[key] = vals[:24]
        memory_strength = self._normalize_memory_strength(policy.get("work_memory_strength", "balanced"))
        return {
            "ok": True,
            "routing_policy": {
                "task_preferences": task_prefs,
                "task_skill_packs": normalized_packs,
                "work_memory_strength": memory_strength,
            },
            "updated_at": now_iso(),
        }

    def save_routing_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_policy = payload.get("routing_policy", payload)
        if not isinstance(raw_policy, dict):
            return {"ok": False, "message": "routing_policy 必须是 JSON 对象"}

        task_prefs_raw = raw_policy.get("task_preferences", {})
        if not isinstance(task_prefs_raw, dict):
            return {"ok": False, "message": "task_preferences 必须是 JSON 对象"}
        task_skill_packs_raw = raw_policy.get("task_skill_packs", None)
        if task_skill_packs_raw is not None and (not isinstance(task_skill_packs_raw, dict)):
            return {"ok": False, "message": "task_skill_packs 必须是 JSON 对象"}
        memory_strength = self._normalize_memory_strength(raw_policy.get("work_memory_strength", "balanced"))

        task_prefs: dict[str, list[str]] = {}
        for k, v in task_prefs_raw.items():
            key = str(k or "").strip()
            if not key:
                continue
            if isinstance(v, list):
                items = [str(x).strip() for x in v if str(x).strip()]
            elif isinstance(v, str):
                items = [x.strip() for x in v.split(",") if x.strip()]
            else:
                items = []
            task_prefs[key] = items[:12]

        task_skill_packs: dict[str, list[str]] = {}
        if isinstance(task_skill_packs_raw, dict):
            for k, v in task_skill_packs_raw.items():
                key = str(k or "").strip()
                if not key:
                    continue
                if isinstance(v, list):
                    items = [str(x).strip() for x in v if str(x).strip()]
                elif isinstance(v, str):
                    items = [x.strip() for x in v.split(",") if x.strip()]
                else:
                    items = []
                task_skill_packs[key] = items[:24]

        path = self._llm_config_path()
        cfg: dict[str, Any] = {}
        try:
            if path.exists() and path.is_file():
                raw = json.loads(path.read_text(encoding="utf-8-sig", errors="ignore"))
                if isinstance(raw, dict):
                    cfg = raw
        except Exception:
            cfg = {}

        existing_policy = cfg.get("routing_policy", {})
        if not isinstance(existing_policy, dict):
            existing_policy = {}
        if not task_skill_packs:
            old_packs = existing_policy.get("task_skill_packs", {})
            if isinstance(old_packs, dict):
                for k, v in old_packs.items():
                    key = str(k or "").strip()
                    if not key:
                        continue
                    if isinstance(v, list):
                        items = [str(x).strip() for x in v if str(x).strip()]
                    elif isinstance(v, str):
                        items = [x.strip() for x in v.split(",") if x.strip()]
                    else:
                        items = []
                    task_skill_packs[key] = items[:24]

        cfg["routing_policy"] = {
            "task_preferences": task_prefs,
            "task_skill_packs": task_skill_packs,
            "work_memory_strength": memory_strength,
        }
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "message": "路由策略已保存",
            "routing_policy": cfg.get("routing_policy", {}),
            "updated_at": now_iso(),
        }

    def get_skills_policy(self) -> dict[str, Any]:
        policy = load_skill_router_policy(self.base_dir)
        return {
            "ok": True,
            "skills_policy": policy,
            "updated_at": now_iso(),
        }

    def save_skills_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = payload.get("skills_policy", payload)
        if not isinstance(raw, dict):
            return {"ok": False, "message": "skills_policy 必须是 JSON 对象"}
        policy = save_skill_router_policy(self.base_dir, raw)
        return {
            "ok": True,
            "message": "技能策略已保存",
            "skills_policy": policy,
            "updated_at": now_iso(),
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

    def snapshot(self) -> dict[str, Any]:
        state = load_runtime_state(self.state_path)
        conn = self._conn()
        try:
            payload = build_snapshot_payload(conn, state)
            payload["memory_system"] = collect_memory_status(conn)
            payload["cognitive_v0"] = collect_cognitive_v0_status(self.base_dir)
            payload["consciousness"] = collect_consciousness_status(conn, self.db_path)
            payload["skills_router"] = collect_skills_router_status(self.base_dir)
            return payload
        finally:
            conn.close()

    def inject(self, text: str, run_once: bool = False) -> dict[str, Any]:
        content = str(text or "").strip()
        if not content:
            return {"ok": False, "message": "输入内容为空"}

        conn = self._conn()
        try:
            enqueue_event(
                conn,
                source="manual",
                event_type="input",
                content=content[:4000],
                meta={"from": "brain_web_panel", "run_once": bool(run_once)},
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
        return {"ok": True, "message": "手动任务已入队"}

    def force_deep(self) -> dict[str, Any]:
        conn = self._conn()
        try:
            enqueue_event(
                conn,
                source="web-user",
                event_type="deep_request",
                content="force deep from web panel",
                meta={"from": "brain_web_panel"},
            )
        finally:
            conn.close()

        self._spawn_once(
            [
                "brain_loop.py",
                "--db",
                str(self.db_path),
                "--state",
                str(self.state_path),
                "--once",
                "--force-deep",
                "--max-events",
                "30",
            ]
        )
        self._spawn_once(
            [
                "deep_coder_worker.py",
                "--db",
                str(self.db_path),
                "--state",
                str(self.state_path),
                "--once",
                "--force-deep",
            ]
        )
        return {"ok": True, "message": "已请求强制深思"}

    def force_dream(self) -> dict[str, Any]:
        conn = self._conn()
        try:
            enqueue_event(
                conn,
                source="web-user",
                event_type="dream_request",
                content="force dream from web panel",
                meta={"from": "brain_web_panel"},
            )
        finally:
            conn.close()

        self._spawn_once(
            [
                "brain_loop.py",
                "--db",
                str(self.db_path),
                "--state",
                str(self.state_path),
                "--once",
                "--force-dream",
                "--max-events",
                "30",
            ]
        )
        self._spawn_once(
            [
                "deep_coder_worker.py",
                "--db",
                str(self.db_path),
                "--state",
                str(self.state_path),
                "--once",
                "--force-dream",
            ]
        )
        return {"ok": True, "message": "已请求强制梦境回放"}

    def iteration(self, text: str, trigger_update: bool) -> dict[str, Any]:
        content = str(text or "").strip()
        if not content:
            return {"ok": False, "message": "迭代内容为空"}

        conn = self._conn()
        try:
            enqueue_event(
                conn,
                source="web-user",
                event_type="iteration",
                content=content[:4000],
                meta={"from": "brain_web_panel", "trigger_update": bool(trigger_update)},
            )
        finally:
            conn.close()

        if trigger_update:
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
            self._spawn_once(
                [
                    "deep_coder_worker.py",
                    "--db",
                    str(self.db_path),
                    "--state",
                    str(self.state_path),
                    "--once",
                ]
            )
            return {"ok": True, "message": "迭代请求已入队；已触发更新"}

        return {"ok": True, "message": "迭代请求已入队"}


def make_handler(app: BrainWebApp):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, html: str, status: int = 200) -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict[str, Any]:
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except Exception:
                n = 0
            if n <= 0:
                return {}
            raw = self.rfile.read(n)
            try:
                data = json.loads(raw.decode("utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self._html(HTML_PAGE, status=200)
                return
            if path == "/api/snapshot":
                self._json(app.snapshot(), status=200)
                return
            if path == "/api/routing-policy":
                self._json(app.get_routing_policy(), status=200)
                return
            if path == "/api/skills-policy":
                self._json(app.get_skills_policy(), status=200)
                return
            if path == "/api/connectors":
                self._json(app.list_connectors(), status=200)
                return
            if path == "/api/mcp/connectors":
                self._json(app.list_mcp_connectors(), status=200)
                return
            self._json({"ok": False, "error": "not found"}, status=404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            body = self._read_json_body()
            if path == "/api/inject":
                res = app.inject(str(body.get("text", "")), run_once=bool(body.get("run_once", False)))
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/iteration":
                res = app.iteration(str(body.get("text", "")), trigger_update=bool(body.get("trigger_update", False)))
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/force-deep":
                self._json(app.force_deep(), status=200)
                return
            if path == "/api/force-dream":
                self._json(app.force_dream(), status=200)
                return
            if path == "/api/routing-policy/save":
                res = app.save_routing_policy(body)
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/skills-policy/save":
                res = app.save_skills_policy(body)
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/connectors/save":
                res = app.save_connector(dict(body.get("connector", {}) or {}))
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/connectors/delete":
                res = app.delete_connector(str(body.get("connector_id", "")))
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/connector-call":
                res = app.call_connector(body)
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/mcp/connectors/save":
                res = app.save_mcp_connector(dict(body.get("connector", {}) or {}))
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/mcp/connectors/delete":
                res = app.delete_mcp_connector(str(body.get("connector_id", "")))
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/mcp/connectors/sync-presets":
                res = app.sync_mcp_presets()
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/mcp/list-tools":
                res = app.list_mcp_tools(body)
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            if path == "/api/mcp/call-tool":
                res = app.call_mcp_tool(body)
                self._json(res, status=200 if bool(res.get("ok", False)) else 400)
                return
            self._json({"ok": False, "error": "not found"}, status=404)

        def log_message(self, format: str, *args) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="阿紫认知中枢 Web 面板")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8798)
    parser.add_argument("--db", default="azi_rebuild.db")
    parser.add_argument("--state", default="azi_state.json")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = base_dir / db_path

    state_path = Path(args.state)
    if not state_path.is_absolute():
        state_path = base_dir / state_path

    app = BrainWebApp(base_dir=base_dir, db_path=db_path, state_path=state_path)
    server = ThreadingHTTPServer((args.host, int(args.port)), make_handler(app))
    print(f"brain web panel: http://{args.host}:{args.port}")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
