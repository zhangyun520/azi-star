# GitHub 发布清单（隐私安全版）

## 1) 先确认当前仓库已是公开模板

- `llm_config.json` 使用公开模板（默认 `OPENAI_API_KEY`，无私有 key 明文）
- `api_connectors.json` 使用公开模板
- `.gitignore` 已屏蔽运行态日志、数据库、状态文件、本地大目录
- `.env.example` 提供环境变量占位

## 2) 本地私有配置放到不提交文件

建议仅在本地使用以下文件名并加入忽略：

- `llm_config.local.json`
- `api_connectors.local.json`
- `mcp_connectors.local.json`
- `.env`

## 3) 初始化并提交（推荐白名单 add）

```powershell
git init
git add README.md .gitignore .env.example GITHUB_PUBLISH_CHECKLIST.md `
  Cognitive_OS_GitHub_Whitepaper_v1.0.md `
  Cognitive_OS_GitHub_Whitepaper_v1.0_EN.md `
  Cognitive_OS_Executable_Spec_v0.1.md `
  Consciousness_Spec_v0.1.md `
  REBUILD_USAGE.md MCP_TO_MODEL_DESIGN_v0.1.md `
  run.ps1 brain_web_panel.py brain_loop.py deep_coder_worker.py `
  llm_config.json api_connectors.json mcp_connectors.json `
  az_v2 azi_rebuild cognitive_os_v0 tests
git commit -m "chore: publish-safe open-source baseline (Azi Cognitive OS)"
```

## 4) 连接远程仓库并推送

```powershell
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

## 5) 发布前最后检查

```powershell
rg -n "sk-[A-Za-z0-9]{10,}|Bearer\\s+[A-Za-z0-9._-]{20,}|api\\.vectorengine\\.ai|VECTORENGINE_API_KEY" `
  --glob "!代码库/**" --glob "!Shu/**" --glob "!课程/**" --glob "!resident_output/**"
```

如果仍有命中，逐条确认是否为公开示例文本，而不是私有凭据或私有 endpoint。

