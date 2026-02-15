# Web Panel Architecture

## Goal
将面板按职责拆成清晰层次，避免单文件承担路由、协议、状态采集、连接器编排全部工作。

## Modules
- `brain_web_panel.py`
  - Web 页面与 `/api/*` 路由
  - 业务入口编排（注入、迭代、强制深思、强制梦境）
  - 委托 `PanelConnectorService` 执行连接器相关能力
- `azi_rebuild/panel_service.py`
  - 连接器 service 层
  - API/MCP 连接器 CRUD
  - MCP 工具枚举与调用
  - API 远程调用与事件注入
- `azi_rebuild/panel_connectors.py`
  - 连接器规范化、占位符解析、响应提取
  - MCP stdio 协议客户端
  - 内置 MCP 预设
- `azi_rebuild/panel_status.py`
  - 记忆系统状态采集
  - `cognitive_os_v0` 状态采集
  - consciousness 指标采集
- `azi_rebuild/runtime.py`
  - 运行时 DB 连接、事件入队、基础快照

## Request Path
1. 前端请求进入 `brain_web_panel.py`。
2. 路由层根据 API 类型调用：
   - `panel_service.py`（连接器/MCP）
   - `runtime.py`（事件与状态）
   - `panel_status.py`（状态聚合）
3. 返回统一 JSON。

## Next Refactor
- 增加 `azi_rebuild/panel_routes.py`，把 `make_handler` 的路由映射进一步抽离。
- 增加最小回归测试：
  - `/api/snapshot`
  - `/api/call-connector`
  - `/api/mcp/list-tools`
  - `/api/mcp/call-tool`
