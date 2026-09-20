# 面向 Agent 应用开发实习的升级学习手册

## 1. 这次升级解决什么问题

旧版本把搜索结果中的摘要直接交给模型。它能展示多 Agent 工作流，但不能证明你掌握真正的 RAG、上下文控制、标准工具协议或反馈数据闭环。

升级后的主数据流是：

```text
搜索 Paper
  → 下载 PDF（失败则明确回退摘要）
  → 按页分块
  → 生成 Embedding
  → 写入向量索引
  → 针对问题检索候选 chunk
  → 去重并执行 token 预算
  → Agent 基于证据生成 PaperAnalysis + citations
  → 保存 ContextAudit
  → 跨论文总结与构思
  → Markdown / HTML / JSON
```

## 2. RAG 模块

阅读顺序：

1. `HashingEmbedder`：理解 Embedding 接口为什么要与模型供应商解耦。
2. `OpenAICompatibleEmbedder`：理解如何接入 Qwen 的兼容 Embedding API。
3. `TextChunker`：理解 chunk size、overlap 和页码元数据。
4. `VectorIndex`：理解入库、余弦相似度、过滤和持久化。
5. `PdfLoader`：理解网络超时、文件大小和 URL 安全边界。
6. `PaperRAG`：理解索引、检索与摘要回退如何组合。

必须能回答：

- 为什么搜索论文不等于 RAG？
- 为什么 chunk 必须保留 paper_id、page_number 和 source_url？
- 为什么测试使用本地 Embedding，而 live 使用语义 Embedding？
- PDF 失败时为什么应回退并标记，而不是静默假装全文成功？

## 3. 上下文工程

`ContextBuilder` 不负责“生成更长的 Prompt”，而是控制什么证据有资格进入 Prompt。

当前策略：

- 相同 chunk 只保留最高分版本；
- 按检索分数排序；
- 限制总 chunk 数；
- 限制单篇论文 chunk 数；
- 超过估算 token 预算的 chunk 被丢弃；
- 入选和丢弃信息写入 `ContextAudit`。

必须能解释：

- 上下文窗口大不代表应该塞满；
- 检索召回率和上下文精度之间存在取舍；
- token 预算为什么是可靠性、延迟和费用控制的一部分；
- 为什么报告只保存审计元数据，而不是重复保存完整 PDF 文本。

## 4. MCP 项目证据

MCP Server 是业务能力与 Agent/客户端之间的标准边界。当前 Server 使用 FastMCP，同时支持 stdio 和 streamable HTTP。

练习顺序：

1. 启动 `paper-agent-mcp --transport stdio`。
2. 在 MCP Inspector 或支持 MCP 的客户端中查看 tools/list。
3. 调用 `search_papers`。
4. 把结果序列化后传给 `index_papers`。
5. 调用 `retrieve_evidence`，检查 chunk_id 与 paper_id。
6. 传入 `../outside.json` 验证报告读取工具拒绝路径穿越。

面试时不要只说“会 MCP”，要展示：工具定义、输入 schema、传输方式、状态生命周期、错误边界和安全测试。

## 5. Agentic-RL 基础闭环

当前实现不是模型训练器，而是训练前最重要的数据闭环：

```text
Agent 输入和输出
  + 人工四维评分
  + evaluator 第二意见
  → AgentTrajectory
  → 人工 reward
  → SFT 候选 / 奖励轨迹
```

奖励计算：

```text
content_accuracy = (研究问题 + 方法 + 主要结果) / 6
evidence_fidelity = 证据约束 / 2
reward = 0.8 × content_accuracy + 0.2 × evidence_fidelity
```

奖励只使用人工评分。Evaluator 分数用于诊断，不能取代人工真值。

要进入下一阶段：

1. 每个相同 prompt 采样至少 2–4 个 completion；
2. 人工进行偏好排序，才能形成 DPO pair；
3. 若奖励可自动验证，可形成同 prompt 多候选的 GRPO group；
4. 划分 train/eval，训练后必须在保留集上重新评测；
5. 只有真正运行训练并报告基线差异后，才能在简历写“完成 SFT/GRPO”。

## 6. 推荐演示脚本

三分钟演示：

1. 画出搜索、RAG、Agent、报告的数据流。
2. 运行一次 demo RAG，打开 JSON 的 `citations` 和 `context_audits`。
3. 展示 MCP 的四个工具。
4. 展示人工评分转成奖励轨迹，但说明尚不满足 GRPO。

十分钟演示额外包括：

- 本地与 Qwen Embedding 的取舍；
- 并发只发生在单篇分析的原因；
- PDF、检索和分析三个阶段的失败边界；
- 人工评测与 evaluator 的两处分歧；
- 为什么“有 reward 数据”不等于“完成强化学习”。

## 7. 验收清单

- [ ] 离线 RAG demo 生成 Markdown、HTML、JSON。
- [ ] 至少一次 live PDF RAG 使用真实论文。
- [ ] 报告中的 citation 能定位到索引 chunk。
- [ ] context audit 能说明入选、丢弃和预算。
- [ ] MCP tools/list 和至少一次 tool call 成功。
- [ ] 5 条人工反馈导出为 rewarded trajectories。
- [ ] 能解释为什么当前数据不能直接用于 GRPO。
- [ ] 所有自动化测试通过。
