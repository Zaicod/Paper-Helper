# 学习报告功能与代码阅读

## 使用方法

先启动 Python 执行服务、Java 业务服务和 Vue。更新 Python 依赖后再启动，新增 DOCX 导出需要 python-docx：

```powershell
cd D:\20476\Pictures\agent
.\.venv\Scripts\python.exe -m pip install -e ".[web]"
```

Java 与 Python 的服务身份配置沿用原有 PAPERFLOW_SERVICE_TOKEN；Java 的 PAPERFLOW_WORKER_URL 指向 Python 服务。真实学习报告还需要 Python 配置 DASHSCOPE_API_KEY（Qwen）或 OPENAI_API_KEY（选择 OpenAI 时）。凭证只在执行端配置，不放入 Vue。

在“搜索论文”选择最相关、最新发表或引用最多。关键词可以添加多项，逐个选择精准或模糊匹配，支持移除和清空。每页 10 或 20 篇，翻页向文献来源请求真实下一页；修改条件后重新搜索。引用最多使用 OpenAlex；全为模糊关键词时可回退 Crossref。arXiv 不提供引用次数排序。没有引用数据时显示“暂无引用数据”。Crossref 为宽泛书目检索，引用数仅为其 DOI 收录口径，缺少摘要或 PDF 时需补充资料，不保证多个词同时出现。

将论文加入收藏夹。在收藏夹点击“生成单篇学习报告”，或勾选 1 至 20 篇后点击“生成所选论文学习报告”。填写主题，可补充学习目标和阅读体会，然后提交。任务完成后可以在详情页阅读并下载 DOCX。

PDF 必须可以公开访问。系统自动获取开放 PDF，解析正文证据和页码，再交给 Agent 分析。官方 arXiv 的 HTTP PDF 链接会升级为 HTTPS；其他下载只接受公开 HTTPS。没有 PDF、下载失败、加密、扫描版无可提取正文或超过处理限制时，任务指出对应论文，请在资料编辑中补充 PDF 链接后重试。不会静默改为摘要分析。

每篇报告包含论文概述、研究背景与问题、模型方法与模块解释、创新点与实验结果、学习体会。多篇额外提供方法对比和学习顺序。学习体会由 Agent 根据论文和你的笔记整理，不代表你已经完成复现或掌握全部内容。正文证据不支持的实验数字要求标为待核实。

## Java 三层架构

- ResearchController：接收任务请求、查询历史；文档下载调用 StudyDocumentService。
- ResearchTaskService → ResearchTaskServiceImpl：检查用户归属，读取所选论文和笔记，保存任务输入快照。
- ResearchTaskMapper：使用 MyBatis 写入原任务表，不新增 JPA 或多模块。
- ResearchSynchronizer / ResearchTaskStoreImpl：同步 Python 的进度、报告和安全失败原因。
- StudyDocumentService → StudyDocumentServiceImpl：校验本人已完成的学习报告，向 Python 发送保存的报告 JSON 并返回 Word。
- WorkerClient：服务身份、超时、响应大小与报告契约校验。

`task_type` 为 `research` 或 `study_report`；旧任务默认仍是 research。任务类型来自已保存的 payload_json，因此不需要数据库迁移。创建学习报告必须明确选择本人收藏夹中的论文，不能只传主题检索。

## Python Agent 链路

1. interfaces/worker.py 接收任务，使用原有 SQLite 持久任务账本和队列。
2. services/study.py 获取每篇论文证据并构造有预算的上下文。
3. tools/study_pdf.py 校验 DNS、连接已校验的公网 IP、逐跳验证重定向，限量读取 PDF 并提取带页码证据。
4. agents/study.py 的学习分析员解释每篇方法和实验，整理员综合多篇分析。
5. core/study.py 校验结构、所选论文覆盖与标题；服务校验每条引用来自实际提供的证据。
6. interfaces/study_document.py 将已完成的报告排版成 DOCX。下载不会再次调用模型或重新抓取 PDF。

DOCX 下载使用 Java 已保存的报告快照，不依赖 Python 账本中仍有原任务。修改或删除收藏夹不改写历史报告；下载仍需 Python 文档服务在线。普通研究报告保持原有结构和流程。

## 限制与验证

一次选择最多 20 篇；任务请求 UTF-8 大小超过 2 MiB 时提交直接返回错误，请减少论文或缩短笔记，不会截断内容。逐篇笔记与收藏夹笔记均沿用最多 50000 字符。PDF 限制为 25 MiB、200 页、提取文本 200 万字符；不支持 OCR。模型读取的是上下文预算内选出的 PDF 片段，不能保证覆盖原文全部细节。

单篇、多篇、PDF 失败、模型配置缺失、引用伪造、任务归属、历史快照和 Word 结构都有回归测试。浏览器验收通过三套真实本地服务，文献 API、PDF 证据与模型边界使用明确标注的受控测试数据；不能把它视作真实模型效果验证。新 PDF 读取器另行实际获取并解析了 arXiv 1706.03762（15 页）。

本环境未提供文档技能的配套渲染器和运行时加载工具，因此 DOCX 已验证文件结构、中文样式和浏览器下载，尚未完成 Word 页面渲染检查。真实模型报告质量也尚未实测。
