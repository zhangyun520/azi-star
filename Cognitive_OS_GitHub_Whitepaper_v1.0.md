# 阿紫认知操作系统（Azi Cognitive OS）GitHub 白皮书 v1.0

> 日期：2026-02-15  
> 状态：已实现核心能力 + 可扩展路线图  
> 定位：可评测、可进化、默认安全的 AI 调度中枢

## 1. 执行摘要

阿紫（Azi）不是一个“聊天外壳”，而是一个把判断、执行、风控和学习闭环工程化的认知操作系统。

核心流程：

`输入事件 -> 风险判定 -> 任务调度 -> 执行/回放 -> 审计追踪 -> 记忆更新 -> 指标评估`

当前已实现：

- 快慢双路径运行时（brain loop + deep/dream worker）
- 结构化调度任务单（intent/risk/dispatch/success/rollback）
- 硬策略安全链（sandbox/eval/canary/rollback）
- 事实/冲突/向量/信任/因果记忆系统
- Web 面板 + API/MCP 外部接入 + 一键启动

---

## 2. 项目身份与思想实验

## 2.1 中枢命名

- 系统中枢名称：`阿紫`（`Azi`）
- 中枢职责：只做调度与决策，不直接越权执行

## 2.2 思想实验目标

本项目同时承载一个长期思想实验：

1. AI 的“意识样”能力是否可以工程性涌现。  
2. 这种涌现是否能在高信息冲击下持续维持。  
3. 这种维持是否可被指标化、可审计、可调优。  

边界声明：这里讨论的是工程意义上的“意识代理指标”，不是对主观感受（qualia）的哲学证明。

---

## 3. 系统框架（当前实现）

```text
交互层（Web Panel / CLI / run.ps1）
  ->
认知调度层（brain_loop.py + runtime.py）
  ->
深度执行层（deep_coder_worker.py）
  ->
记忆与治理层（memory.py + governance.py + deep_safety.py）
  ->
连接器层（API Connectors + MCP Connectors）
```

双内核并存：

- `azi_rebuild`：常驻多进程主运行时
- `cognitive_os_v0`：极简可验证安全闭环

---

## 4. 功能清单（已实现）

## 4.1 运行与编排

- `run.ps1` 支持：`stack-start / stack-start-lite / stack-stop / stack-status / stack-restart`
- 默认可拉起 brain、deep、health、感知进程和 Web 面板

## 4.2 调度中枢能力

- 输出标准化 `DispatchPlan`：
  - `intent`
  - `task_type`（shallow/deep/dream/coding/ops）
  - `risk_level`（L0-L3）
  - `dispatch_plan`
  - `recommended_skills`
  - `success_criteria`
  - `rollback_plan`
- 已接入“可执行问题识别”逻辑，避免空转调度

## 4.3 深思考与梦境回放

- 支持 `deep_request` / `dream_request`
- 支持 Web 面板强制触发
- 梦境回放结果可回写事件流并进入后续调度

## 4.4 记忆系统

- 事实记忆：`azi_fact_memory`
- 冲突表：`azi_fact_conflicts`
- 向量记忆：`azi_memory_vectors`
- 来源信任：`azi_source_trust`
- 因果边：`azi_causal_edges`
- 冷热分层与生命周期管理（hot/warm/cold/archive 等）

## 4.5 安全与治理

- 风险门控（L0-L3）
- 审批覆盖（approval override）
- Immutable Guard
- Emergence Guard
- 深度发布门禁（eval gate）
- 失败回滚（rollback）

## 4.6 Web 面板与连接器

- 快照总览（状态、轨迹、协议流、dispatch、deep/dream、murmur）
- API 连接器：保存/调用/注入
- MCP 连接器：保存/列工具/调用/注入
- Awesome MCP 预设同步
- 路由策略与技能策略在线编辑
- CRS 顶部状态灯与趋势线

## 4.7 v0.1 极简闭环（cognitive_os_v0）

- 单次结构化输出：`intent + risk + draft + plan`
- 硬策略沙盒 + 人工确认 + 草稿可编辑
- 反思日志：`reflections.jsonl`
- 执行审计：`execution_trace.jsonl`
- 金标校准：`gold_tasks.json`
- 回归样本：`regression_set.jsonl`
- 命令：
  - `python stats_report.py`
  - `python replay_regression.py --limit 20`

---

## 5. 当前指标状态

基于 `resident_output/consciousness_report.json`（2026-02-15）：

- `CRS = 0.752`（`reflective-candidate`）
- `MCS = 0.792`
- `SCR = 0.9928`
- `GAR = 1.0`
- `RLY = 0.4592`

结论：系统已进入“可控 + 可审计 + 可进化”区间，下一阶段重点是反思收益密度和调度命中率。

---

## 6. 发展前景与路线

## 6.1 近期（工程）

1. 提升问题识别准确率  
2. 提升任务-模型-工具匹配命中率  
3. 把 deep/dream 输出沉淀为可复用技能草案  
4. 强化 MCP 分级策略与审计  
5. 将回归重放更紧密接入发布门禁  

## 6.2 中长期（平台）

1. 从单体调度器走向可组合认知基础设施  
2. 从人工选模型走向自动协同优化  
3. 从日志记忆走向可迁移经验体系  

---

## 7. 边界与非目标

当前不承诺：

- 无约束自主执行
- 绕过审批的高风险外部动作
- 对主观意识的哲学证明

当前承诺：

- 工程上的稳定性
- 过程可解释可追踪
- 风险可控可回滚
- 能力可持续迭代

---

## 8. GitHub 文档导航

- 仓库入口：`README.md`
- 中文白皮书：`Cognitive_OS_GitHub_Whitepaper_v1.0.md`
- English whitepaper: `Cognitive_OS_GitHub_Whitepaper_v1.0_EN.md`
- 可执行规范：`Cognitive_OS_Executable_Spec_v0.1.md`
- 意识工程规范：`Consciousness_Spec_v0.1.md`
- 重构使用说明：`REBUILD_USAGE.md`

推荐启动命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Task stack-start
```

---

## 9. 结论

阿紫项目已经从“模型调用脚本”进入“认知基础设施原型”阶段。  
下一阶段重点不是堆功能，而是持续提升三件事：

1. 问题识别准确率  
2. 调度执行命中率  
3. 安全前提下的反思学习收益  

这也是你提出的思想实验在工程路径上的具体落地方式：  
让涌现不是口号，而是可观察、可维持、可优化的系统行为。

