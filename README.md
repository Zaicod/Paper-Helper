# 论文研究多 Agent 助手

这是一个为 Agent 开发初学者设计的教学项目。它不是把所有能力塞进一个大 Prompt，而是把完整研究流程拆成可观察、可测试的模块：

```text
研究主题
  ↓
文献搜索工具（确定性 I/O）
  ↓
文献分析 Agent（每篇论文可并行）
  ↓
领域总结 Agent（跨论文归纳）
  ↓
创新构思 Agent（基于证据提出假设）
  ↓
Markdown 报告 + JSON 中间结果
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

真实模式会查询 arXiv 的公开 API，并用 Agents SDK 依次执行三个专职 Agent。第一版只分析题目与摘要：这是刻意限定的 MVP，报告会明确标注“无法从摘要确认”的内容，避免假装读过全文。

## 4. 从哪里读代码

建议按以下顺序阅读：

1. `src/paper_agent/models.py`：Agent 之间传递的“合同”。
2. `src/paper_agent/search.py`：确定性的文献搜索工具。
3. `src/paper_agent/prompts.py`：三个角色的职责边界和防幻觉规则。
4. `src/paper_agent/providers.py`：如何把 Qwen 的兼容 API 适配到 Agents SDK。
5. `src/paper_agent/agent_team.py`：如何把模型、指令、输出类型组成 Agent。
6. `src/paper_agent/workflow.py`：并行与串行如何组合成完整工作流。
7. `src/paper_agent/report.py`：把领域对象渲染成人能阅读的报告。
8. `src/paper_agent/cli.py`：应用入口和依赖装配。

更完整的设计解释见 [架构说明](docs/architecture.md)，分阶段开发安排见 [学习路线](docs/learning-roadmap.md)，第一次学习请直接按 [逐步学习手册](docs/study-guide.md) 操作。

## 5. 测试

```powershell
pytest
```

测试默认不访问网络、不调用模型，因此快速且不会产生 API 费用。

## 目前边界

- v0.1 只使用 arXiv 元数据与摘要，尚未下载和解析 PDF。
- 尚未做向量数据库、长期记忆、人工审批、引用页码定位和自动评测。
- 创新点是“候选研究假设”，不是已验证的新颖性结论；真正的新颖性仍需更广泛检索和领域专家审核。
