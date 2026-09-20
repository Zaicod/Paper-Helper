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
