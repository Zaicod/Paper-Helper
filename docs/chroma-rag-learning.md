# ChromaDB 论文向量与 RAG

Java 负责账号、收藏夹和任务等业务资料，Python 负责正文提取、向量化、Chroma 持久化及 Agent 证据检索。Chroma 使用本地 `PersistentClient`，不需要另外启动数据库服务器。默认目录为项目工作目录下的 `outputs/chroma`，可用 `PAPERFLOW_CHROMA_DIR` 指定其他位置。

## 安装与准备本地模型

在项目根目录的 PowerShell 中执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[web,rag]'
.\.venv\Scripts\python.exe scripts/prepare_embeddings.py
```

准备脚本下载固定版本的 `Xenova/multilingual-e5-small` tokenizer 与量化 ONNX 权重，默认进入 Hugging Face 缓存。向量生成在本机 CPU 执行，维度为 384；文档使用 `passage:`，查询使用 `query:` 前缀，再做掩码均值池化和 L2 归一化。无需 Hugging Face Token 或 Embedding API Key，首次下载仍需可访问模型文件的网络。模型按需加载，不在 HTTP 服务启动时下载。

也可以指定容易查找的模型目录：

```powershell
.\.venv\Scripts\python.exe scripts/prepare_embeddings.py --output-dir outputs/models/multilingual-e5-small --smoke-json outputs/models/embedding-smoke.json
$env:PAPERFLOW_EMBEDDING_MODEL_DIR = 'D:\20476\Pictures\agent\outputs\models\multilingual-e5-small'
$env:PAPERFLOW_CHROMA_DIR = 'D:\20476\Pictures\agent\outputs\chroma'
```

`--smoke-json` 会执行真实中英文语义召回检查并保存结果；失败会报错。环境变量须配置在实际启动 Python 的终端或运行配置中；示例 `.env.example` 本身不是已生效的个人配置。Agent 生成学习报告仍需要 `DASHSCOPE_API_KEY` 或 `OPENAI_API_KEY`，本次免密钥仅针对向量生成。

## 资料如何进入 Chroma

收藏论文时只保存业务资料。首次执行真实研究或学习报告时，Python 获取资料、切分正文、生成向量并写入 Chroma；下次使用相同资料时复用已完成的索引。检索使用 Chroma 实际返回的片段，再按上下文预算供给 Agent，保留论文 ID、片段 ID、页码及来源链接。

普通研究继续支持摘要和 PDF 证据，PDF 获取失败时原有摘要回退会记录来源模式；下次 PDF 研究会重新尝试正文获取，失败回退的摘要不会阻止之后重新获取 PDF。学习报告只复用 PDF 正文索引；没有可用正文时提示补充 PDF，不把摘要当作全文。同一 URL 下的 PDF 发生变化时需要显式重建，不会承诺后台自动发现远端内容变化。

缓存身份包括账号范围、论文来源与 ID、资料/PDF 链接、正文版本、切分版本及向量模型身份。修改模型或维度会使用独立集合；部分写入失败的索引不会标为完整可复用。历史报告保存证据快照，不因之后的论文编辑或重建改写。

新的学习报告在 `evidence_snapshots` 中保存当时实际传给 Agent 的原文片段；研究报告在 `context_audits[].evidence_chunks` 中保存对应片段。这样即使同一链接的正文之后更新，仍能查看旧报告依据的文本、页码和来源。旧报告可以继续读取，但不会自动补造历史原文。

阅读代码时可依次查看 `paper_agent/tools/local_embeddings.py`（本地向量与按 token 分块）、`paper_agent/tools/chroma_index.py`（持久化与隔离）、`paper_agent/services/vector_store.py`（创建真实索引）、`paper_agent/tools/rag.py` 和 `paper_agent/services/study.py`（召回证据并交给 Agent）。Java 的 `ResearchTaskServiceImpl` 负责在内部任务中附加账号范围。

## 命名空间与重建

新 Java 任务的命名空间由服务端登录账号生成，形如 `java-user:123`；浏览器不能指定另一个账号的命名空间。旧任务没有此字段时按任务 ID 隔离，避免与其他任务共用缓存。CLI 默认使用独立的 `cli-local` 空间，可通过 `--index-namespace` 组织本机资料，例如：

```powershell
.\.venv\Scripts\paper-agent.exe run --topic 'multimodal learning' --mode live --rag abstract --index-namespace cli-local --rebuild-index
```

`--rebuild-index` 对本次选中的论文重新获取和建索引。CLI 参数仅用于本机入口，不会赋予浏览器指定任意账号的权限。查询同时限定账号空间、当前所选论文及其版本，不会召回未选中的收藏论文。取消收藏后，新任务不能再选择该论文；当前没有业务删除同步清除物理向量的功能。

学习报告需要刷新同一 PDF URL 的正文时，受服务令牌保护的 Python 内部任务请求也接受 `rebuild_index: true`。这是可信内部维护入口，当前 Vue/Java 任务表单没有重建开关，不能在浏览器请求中指定命名空间或借此访问其他账号索引。

离线 demo 保留原有 `HashingEmbedder` 和内存/JSON 索引，不要求下载模型。受控浏览器测试显式注入该测试替身，仅验证界面与任务链路；不能当作真实模型或 Chroma 质量验收。真实 Chroma 或本地模型失败不会静默回退到 demo。

## 本次界面回归

Python 127 项测试通过。真实本地 E5 与真实 Chroma 已通过中英文语义召回、跨进程重开、账号及所选论文隔离；默认模型缓存也通过离线推理。真实向量模型与 Chroma 接入的 StudyService 连续两次运行只加载一次 PDF，PDF 和生成模型边界在该检查中使用受控数据。

Java 49 项测试通过并打包成功；Vue 41 项测试与生产构建通过。三套实际本地服务完成 3 项浏览器测试，覆盖搜索与分页、多关键词、收藏夹论文选择、单篇/多篇学习报告和 DOCX 下载；桌面 1440 与手机 390 宽度截图已检查。该浏览器运行的外部文献源、PDF 与 Agent 模型明确使用受控替身，不代表真实模型质量或外部网站可用性；Chroma 持久化与真实语义模型须以对应独立验收结果为准。
