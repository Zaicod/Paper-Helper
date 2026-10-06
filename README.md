# 论文研究多 Agent 助手

这是一个为 Agent 开发初学者设计的教学项目。它不是把所有能力塞进一个大 Prompt，而是把完整研究流程拆成可观察、可测试的模块：

```text
研究主题
  ↓
文献搜索工具（确定性 I/O）
  ↓
PDF/摘要解析 → 分块 → Embedding → 向量索引
  ↓
上下文工程（检索、去重、token 预算、来源审计）
  ↓
文献分析 Agent（每篇论文可并行，输出 chunk 引用）
  ↓
领域总结 Agent（跨论文归纳）
  ↓
创新构思 Agent（基于证据提出假设）
  ↓
Markdown + HTML 报告 + JSON 中间结果
```

## 为什么从这个架构开始

- 搜索使用普通工具，而不是让 LLM “回忆”论文，避免虚构文献。
- 分析、总结、构思由三个专职 Agent 完成，让每个 Prompt 的职责单一。
- 工作流顺序由 Python 控制，便于调试、控制费用，并理解数据如何流动。
- 所有 Agent 都返回 Pydantic 结构化数据，后续程序不需要解析不稳定的自然语言。
- 逐篇分析并发执行；总结必须等待全部分析；构思必须等待总结。这展示了 Agent 系统中的依赖关系。
- 项目提供完全离线的演示模式，没有 API Key 也能先跑通工程链路。

## 1. 五分钟跑通离线版本

PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
paper-agent run --topic "retrieval augmented generation" --mode demo
```

演示模式使用内置的三篇示例论文和规则化假数据。它用于理解控制流，不代表真实的论文分析质量。结果会写入 `outputs/`。

### LangGraph 第一阶段学习图

在不影响原工作流的前提下，项目提供 Fixture 驱动的最小 LangGraph：

```powershell
paper-agent run --engine langgraph --mode demo --topic "RAG" --limit 2
pytest tests/test_langgraph_workflow.py -v
```

当前图执行 `START → search → analyze → synthesize → ideate → render → END`；Fixture 入口仍不访问网络或模型，Web 入口可注入个人模型路由。
逐步讲解和练习见 [LangGraph 第一阶段学习手册](docs/langgraph-phase1.md)。

### Web UI 与实时任务进度

项目吸收 `MultiAgent-Search` 的 FastAPI、后台任务和 WebSocket 思路，为论文工作流增加了
会话隔离的浏览器入口：

```powershell
python -m pip install -e ".[dev,web]"
paper-agent-web --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`，即可观察 `search → analyze → synthesize → ideate → render → persist`
各节点的实时事件，并下载任务独立目录中的 Markdown、JSON、HTML。设计取舍与安全分析见
[MultiAgent-Search 融合记录](docs/multiagent-search-integration.md)。

前端使用 React 19、TypeScript、Vite 和 Lucide Icons，提供响应式研究仪表盘、LangGraph
节点状态、WebSocket 实时事件、研究产物下载及论文资料库。日常只运行 FastAPI 即可使用已
构建的前端；修改前端源码时使用：

```powershell
cd frontend
npm install
npm run dev
# 提交前把生产静态文件构建进 Python 包
npm run build
```

开发服务器为 `http://127.0.0.1:5173`，会把 `/api` 和 `/ws` 代理到 8000 端口。组件、状态、
构建和练习说明见 [前端学习手册](docs/frontend-guide.md)。

收藏夹现在同时承担“研究分类”和“知识工作区”的职责：研究任务可从收藏夹中多选论文，
每篇论文有独立笔记，收藏夹有整体归纳笔记，并记录论文加入日期。思维导图 Agent 支持按
加入日期、所选论文和研究方向生成结构化图谱；配置 `DASHSCOPE_API_KEY` 时调用 Qwen，
未配置时使用确定性的 Fixture Agent。数据流和练习见
[收藏夹研究工作区学习手册](docs/collection-research-workspace.md)。

点击右上角用户头像可进入个人模型设置。每个用户分别保存 Provider、加密 API Key 与四个
Agent 的模型路由；文献分析员、总结员、构思员和思维导图 Agent 可以使用不同模型。系统
提供额度优先、均衡和质量优先三种起始方案，并允许直接填写 Provider 支持的其他模型 ID。
安全边界和运行时装配见 [个人模型路由学习手册](docs/personal-model-routing.md)。

左侧导航使用 React Router 拆成四个独立页面：研究工作台 `/`、论文资料库 `/library`、
研究任务 `/tasks`、收藏夹 `/collections`。FastAPI 为这些入口提供 SPA 回退，因此复制链接
或刷新子页面不会返回 404。

网页中的“关键词论文检索”会调用真实 arXiv/OpenAlex 搜索接口。选择已有分类或输入新的分类
名称后，点击“下载并归类”，服务端会校验 PDF、保存到 `outputs/library/pdfs/`，并把论文元
数据、下载记录和 Collection 关系写入 SQLite/MySQL。搜索结果同时提供论文原文页和公开 PDF
源链接；入库后提供由本服务托管的稳定下载链接。

Web 研究结果会自动进入论文资料库。默认使用 `outputs/paper_library.db`，无需额外服务；
若要切换 MySQL：

```powershell
python -m pip install -e ".[dev,web,mysql]"
$env:PAPER_AGENT_DATABASE_URL="mysql+pymysql://paper_agent:密码@127.0.0.1:3306/paper_agent?charset=utf8mb4"
paper-agent-web
```

表结构、收藏夹/标签 API 和数据库设计练习见
[MySQL 论文资料库学习手册](docs/mysql-paper-library.md)。

### 登录注册与 Redis 会话

用户账号保存在 SQLite/MySQL 的 `users` 表，密码使用带随机盐的 scrypt 哈希；登录会话以随机
令牌保存在 Redis，浏览器只接收 `HttpOnly + SameSite=Lax` Cookie。启动本地 Redis：

```powershell
docker compose -f docker-compose.redis.yml up -d
docker exec paperflow-redis redis-cli ping
paper-agent-web --host 127.0.0.1 --port 8000
```

默认会话有效期为 7 天，并在访问时刷新 TTL。Web 服务重启不会清除登录；主动退出会立即删除
Redis 中的会话。Redis 地址、TTL 和 HTTPS Cookie 配置见 `.env.example`，完整数据流与安全
设计见 [Redis 登录学习手册](docs/auth-redis.md)。

## 2. 使用 Qwen 新人免费额度运行真实版本

先在阿里云百炼华北2（北京）地域开通服务、领取新人额度并创建“通用 API Key”。然后执行：

```powershell
$env:DASHSCOPE_API_KEY="你的百炼 API Key"
paper-agent run --topic "multi-agent reinforcement learning" --mode live --provider qwen --model qwen3.8-flash --limit 3
```

默认 `--source auto` 会先查询 arXiv；若 arXiv 超时或失败，会自动改用 OpenAlex。若你的网络访问 arXiv 不稳定，可以直接跳过它：

```powershell
paper-agent run --topic "multi-agent reinforcement learning" --mode live --provider qwen --model qwen3.8-flash --source openalex --limit 3
```

OpenAlex 可匿名调用。若之后查询量增大，可免费申请 Key 并设置 `$env:OPENALEX_API_KEY="..."`。

项目默认使用北京地域的兼容地址：

```text
https://dashscope.aliyuncs.com/compatible-mode/v1
```

如果百炼控制台提供了业务空间专属 API Host，建议设置：

```powershell
$env:DASHSCOPE_BASE_URL="https://你的WorkspaceId.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
```

`qwen3.8-flash` 被选为默认值，是因为它支持本项目需要的 JSON Schema 结构化输出。项目会关闭思考模式，减少 token 消耗并提高 JSON 输出稳定性。Qwen 模式下会关闭 OpenAI Tracing，因为该追踪服务需要 OpenAI 凭证。

以后要换另一个兼容模型，只需改变 `--model`；也可以长期设置 `$env:QWEN_MODEL="模型ID"`。本项目依赖 JSON Schema，所选模型必须支持严格结构化输出。

为了防止额度耗尽后自动计费，请在百炼控制台开启“免费额度用完即停”，并确认 Key、Base URL 与北京地域一致。

## 3. 使用 OpenAI 运行真实版本

```powershell
$env:OPENAI_API_KEY="你的 API Key"
$env:OPENAI_MODEL="gpt-5.6-luna"
paper-agent run --topic "multi-agent reinforcement learning" --mode live --provider openai --limit 5
```

真实模式会查询 arXiv/OpenAlex，并用 Agents SDK 执行三个专职 Agent。不启用 `--rag` 时只分析题目与摘要。

## 4. 启用全文 RAG 与上下文工程

零成本本地向量演示：

```powershell
paper-agent run --topic "retrieval augmented generation" --mode demo `
  --rag abstract --embedding-provider local --context-token-budget 2000
```

真实 PDF RAG：

```powershell
paper-agent run --topic "retrieval augmented generation" --mode live `
  --provider qwen --source openalex --limit 3 `
  --rag pdf --embedding-provider qwen `
  --embedding-model text-embedding-v4 `
  --context-token-budget 6000
```

流程会优先下载 PDF、按页分块、生成 Embedding、执行向量检索，并把入选 chunk 作为证据交给分析 Agent。PDF 下载或解析失败时会显式记录 `abstract_fallback`。报告中的 `context_audits` 会记录来源模式、入选 chunk、丢弃数量和估算 token。

`local` 使用确定性 Hashing Embedding，适合测试但语义能力有限；求职演示应展示一次 `qwen` Embedding 的 live 结果。

## 5. MCP Server

stdio 模式：

```powershell
paper-agent-mcp --transport stdio
```

HTTP 模式：

```powershell
paper-agent-mcp --transport streamable-http
```

MCP Server 暴露四个工具：

- `search_papers`：搜索 arXiv/OpenAlex。
- `index_papers`：把论文元数据和摘要加入本地向量索引。
- `retrieve_evidence`：按查询和 paper_id 检索证据。
- `read_research_report`：安全读取 `outputs` 中的 JSON 报告。

这提供了可展示的 MCP 项目证据：工具 schema、异步调用、有状态索引和路径穿越防护。

## 6. Agentic-RL 数据闭环

```powershell
paper-agent-feedback --results-dir evals/results --output-dir training/data
```

该命令把人工评分、Agent 输出和 evaluator 第二意见导出为：

- `rewarded_trajectories.jsonl`：带人工奖励的完整轨迹；
- `sft_candidates.jsonl`：高质量 SFT 候选；
- `manifest.json`：数据规模、奖励来源和训练适用性。

当前每个 prompt 只有一个 completion，因此不能假装已经具备 DPO/GRPO 数据。下一步需要对同一输入采样多个候选，再做人类偏好或可验证奖励标注。

## 7. 从哪里读代码

建议按以下顺序阅读：

1. `src/paper_agent/models.py`：Agent 之间传递的“合同”。
2. `src/paper_agent/search.py`：确定性的文献搜索工具。
3. `src/paper_agent/prompts.py`：三个角色的职责边界和防幻觉规则。
4. `src/paper_agent/providers.py`：如何把 Qwen 的兼容 API 适配到 Agents SDK。
5. `src/paper_agent/agent_team.py`：如何把模型、指令、输出类型组成 Agent。
6. `src/paper_agent/rag.py`：PDF、分块、Embedding 与向量索引。
7. `src/paper_agent/context.py`：token 预算、去重与证据选择。
8. `src/paper_agent/workflow.py`：并行、重试与 RAG 如何组合。
9. `src/paper_agent/mcp_server.py`：可独立运行的 MCP Server。
10. `src/paper_agent/feedback.py`：人工奖励和训练候选导出。
11. `src/paper_agent/report.py`：Markdown/HTML/JSON 表现层。
12. `src/paper_agent/cli.py`：应用入口和依赖装配。
13. `frontend/src/App.tsx`：React 页面、交互状态和工作流可视化。
14. `frontend/src/api.ts`：REST API 与 WebSocket 边界。
15. `src/paper_agent/mindmap.py`：Fixture/Qwen 思维导图 Agent 与结构化输出。
16. `src/paper_agent/storage.py`：收藏夹、加入日期、两层笔记和思维导图持久化。
17. `src/paper_agent/model_settings.py`：个人密钥加密、推荐方案与运行时模型解析。

更完整的设计解释见 [架构说明](docs/architecture.md)，分阶段开发安排见 [学习路线](docs/learning-roadmap.md)，第一次学习请直接按 [逐步学习手册](docs/study-guide.md) 操作。

新增升级说明见 [RAG、上下文、MCP 与反馈学习手册](docs/internship-upgrade.md)。

## 8. 测试

```powershell
pytest
```

测试默认不访问网络、不调用模型，因此快速且不会产生 API 费用。

## 目前边界

- 本地索引适合教学与作品集，不是大规模生产向量数据库。
- PDF 文本提取不包含 OCR，扫描件可能回退到摘要。
- 当前 token 数为字符近似值，不是特定模型 tokenizer 的精确计数。
- 当前有检索式证据上下文，但没有跨用户长期记忆。
- Agentic-RL 模块完成轨迹与奖励闭环，尚未生成偏好对或执行训练。
- 创新点是“候选研究假设”，不是已验证的新颖性结论；真正的新颖性仍需更广泛检索和领域专家审核。
