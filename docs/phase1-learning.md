# 第一阶段：从两个入口走通同一套研究能力

本阶段保留 Python Agent 核心，统一命令行和网页研究执行。Java 与 Vue 工程尚未创建。

## 1. 先理解实际调用链

```text
命令行参数 → cli.run_command ─┐
                            ├→ ResearchService → ResearchWorkflow
网页请求 → ResearchTaskManager ┘                     │
                                                   ├→ 获取论文
                                                   ├→ RAG 索引与证据选择
                                                   ├→ 并发分析、重试和单篇失败记录
                                                   ├→ 跨论文综合
                                                   └→ 研究构思 → ResearchReport
```

应用服务选择模式、模型、检索源和 RAG 配置；工作流执行研究步骤；入口负责参数、任务状态、文件输出和资料库保存。工作流无需了解 HTTP、浏览器或收藏夹数据库。

## 2. 建议按这个顺序阅读

1. `paper_agent/core/models.py`：看论文、分析、报告和阶段事件各自包含哪些字段。
2. `paper_agent/services/research.py`：看 demo/live 怎样构建依赖，以及两个入口怎样共用配置。
3. `paper_agent/workflows/research.py`：沿 `run` 阅读整个流程，再看 `_analyze_all` 中的并发、重试和失败隔离。
4. `paper_agent/tools/rag.py` 与 `context.py`：看摘要/PDF 如何变成片段、怎样检索、怎样控制上下文预算。
5. `paper_agent/agents/team.py`：看结构化输出和角色调用；再读 `prompts.py` 的证据约束。
6. `paper_agent/interfaces/web.py`：看后台任务怎样接收阶段事件，怎样向 WebSocket 客户端发送进度。
7. `tests/`：阅读失败案例，理解每条边界为什么需要验证。

## 3. 已实现的行为边界

- 正式网页与命令行使用同一应用服务；LangGraph 仍保留为独立离线学习入口。
- 网页默认 live + 摘要 RAG。demo 必须显式选择，不会因为缺少密钥而自动切换。
- demo 限制为离线的本地向量和摘要证据，可使用 fixture 证据决策；拒绝远程 PDF、远程向量和 Jev 调用。
- 显式提供可信论文时跳过搜索；不接受空列表、超过 20 篇或存在歧义的重复论文 ID。
- 收藏夹选定论文由服务端读取，浏览器只提交收藏夹与论文引用。
- 单篇分析失败会记录失败类型和重试次数；其他成功论文继续进入综合与构思。全部失败则停止。
- PDF 解析失败时回退该论文的摘要；其他论文继续使用正文。审计记录区分 pdf、abstract 和 abstract_fallback。
- 六个可计数阶段仍是 search、analyze、synthesize、ideate、render、persist；index 与阶段开始/失败作为任务消息，不增加页面进度分母。
- 报告导出失败或数据库保存失败时不会发布任务完成事件。
- 外部错误只公开安全的错误类型和阶段；内部异常链供调试使用，不通过报告、事件或命令行默认错误输出展示。
- 网页默认使用个人角色配置；显式指定 provider/model 时只覆盖本次任务，不修改个人保存的配置。

## 4. 可以自己复现的学习实验

先运行 README 中的 demo + abstract + fixture 命令，打开 HTML 报告，再查看 JSON 的 `context_audits`、`selected_chunk_ids` 和 `decisions`。

然后阅读并单独运行这些测试：

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_research_workflow.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_web_research.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_pdf_fallback.py -v
```

重点观察三类情况：一篇失败与全部失败的区别；PDF 回退后证据来源如何变化；已经登录但选择 demo 时为什么不应构建真实模型。

完整验证：

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

## 5. 下一阶段的衔接

下一阶段由 Java 接管用户、收藏夹和笔记，重点学习资源归属、事务和权限。`ResearchService` 是现成的 Python 能力边界，后续内部研究接口可以继续调用它。

当前尚未实现资料完整用户隔离、持久化任务恢复或真实模型质量评测。已有任务状态仍位于内存；本阶段的离线验证使用临时 SQLite 和会话替身，没有替代外部 MySQL、Redis 与真实模型的联调。
