# 架构说明：每个模块为什么存在

## 1. 系统边界

用户给出研究主题，系统返回：带证据引用的单篇论文卡片、跨论文领域总结、候选创新想法。默认模式只使用标题和摘要；启用 `--rag pdf` 后优先读取 PDF 正文，并对失败论文显式回退到摘要。

## 2. 核心模块

### `models.py`：数据合同

这里定义 `Paper`、`EvidenceChunk`、`ContextPacket`、`PaperAnalysis`、`FieldSynthesis`、`ResearchIdea` 和 `ResearchReport`。Agent 输出不是随意文本，而必须满足这些结构。

设计意义：

- 模块解耦：总结 Agent 不需要知道分析 Agent 的 Prompt，只依赖其输出结构。
- 运行时校验：漏字段或错误类型会尽早暴露。
- 易测试：测试可以构造固定对象，不必真的调用模型。
- 易持久化：同一份数据既能生成 Markdown，也能保存为 JSON。

### `search.py`：文献搜索工具与故障回退

搜索是外部世界的确定性 I/O。工具支持 arXiv 与 OpenAlex，分别解析 Atom XML 和 JSON，再统一转换为内部 `Paper`。`FallbackSearchClient` 会在首选源超时或失败时尝试独立备用源。

它没有被设计成“搜索 Agent”，因为数据库查询本身不需要语言模型推理。LLM 可以决定搜索词，但不应该编造搜索结果。后续版本会加入查询改写 Agent，但实际检索仍由工具执行。

### `prompts.py`：角色边界

三个 Prompt 分别优化局部任务：证据提取、跨文献综合、可检验假设生成。每个 Prompt 都要求区分“原文证据”和“合理推断”。

设计意义：职责越窄，输出越稳定；问题发生时，也更容易知道应修改哪个 Prompt。

### `providers.py` 与 `agent_team.py`：模型适配和 Agent 定义

`providers.py` 把不同厂商的模型接口转换成 Agents SDK 可使用的模型对象；`agent_team.py` 再组合模型、指令与结构化输出。它们不负责业务顺序，只定义模型如何接入，以及每个专家“是谁、会产出什么”。

设计意义：把厂商适配、角色定义和工作流分离。OpenAI 与 Qwen 共用完全相同的专家角色和流程；未来替换模型、调整 Prompt 或做 A/B 测试时，不必修改业务编排。

### `rag.py` 与 `context.py`：证据和上下文工程

`rag.py` 负责 PDF 获取、文本分块、Embedding、向量检索和索引持久化；`context.py` 负责去重、排序、token 预算和丢弃记录。

两者拆分是因为“检索到哪些候选”和“允许哪些候选进入模型上下文”是两个不同问题。前者优化召回，后者控制精度、成本和上下文污染。

### `workflow.py`：编排器

编排器明确规定数据依赖：

```text
search(topic) → index evidence
    ├─ retrieve(paper 1) → analyze(paper 1) ─┐
    ├─ retrieve(paper 2) → analyze(paper 2) ─┼─ synthesize ─ ideate
    └─ retrieve(paper 3) → analyze(paper 3) ─┘
```

逐篇分析互不依赖，因此并行；综合需要看到所有论文，因此串行；创新构思需要领域空白，因此位于最后。

第一版选择“代码编排”而非“LLM 自主路由”，原因是顺序固定、容易复现、费用可预测，也更适合第一次学习。任务变得开放后，再加入 manager Agent 或 handoff。

### `report.py`：表现层

报告渲染不调用模型，只把同一个 `ResearchReport` 变成 Markdown、HTML 和 JSON。这样可以保证表现层不会改变研究内容。

### `mcp_server.py`：协议边界

FastMCP Server 把搜索、建库、证据检索和报告读取发布为标准工具。业务服务可单元测试，stdio transport 另有真实协议集成测试。

### `feedback.py`：反馈与奖励数据

人工评分被转换成可复查 reward，而 evaluator 只保留为诊断信号。模块能够导出奖励轨迹和 SFT 候选，并明确指出当前单候选数据不满足 DPO/GRPO。

### `demo_team.py`：离线替身

它和真实 Agent 实现相同协议，但不调用模型。目的不是模拟智能，而是让你先验证工程结构、学习依赖注入并编写零费用测试。

## 3. 一次运行中的状态

状态不是一段越来越长的聊天记录，而是逐步变丰富的领域对象：

```text
topic
→ papers
→ evidence chunks
→ context packets + context audits
→ analyses
→ synthesis
→ ideas
→ report
```

这种显式状态比隐式聊天上下文更容易恢复、审计和评测。

## 4. 可靠性原则

- 可追溯：每项分析携带论文 ID；每个想法说明它针对哪个研究空白。
- 不越过证据：摘要未给出具体结果时，输出“摘要未说明”，而不是猜测。
- 失败隔离：单篇分析可以单独重试，未来不必重跑全部论文。
- 中间结果落盘：JSON 方便复现、调试和制作训练/评测数据集。
- 人在回路：创新想法只作为候选，必须经过研究者判断。

## 5. 下一版的关键演进

1. 加入 OCR 和更准确的版面/章节解析。
2. 为检索建立带标注的问题集，计算 Recall@k、MRR 和引用命中率。
3. 查询规划 Agent：把研究方向扩展成多个检索式并去重。
4. 评审 Agent：检查证据覆盖、事实一致性和想法的新颖性。
5. 数据库任务状态、缓存、断点恢复、费用和精确 tokenizer 统计。
6. 对相同输入采样多候选，收集偏好对或可验证奖励，再决定 SFT/DPO/GRPO。
