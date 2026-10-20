# 论文搜索与收藏夹论文管理

新增功能复用项目现有 arXiv / OpenAlex 适配器。前端“搜索论文”页面调用 Java，Java 校验登录身份后调用 Python；Python 请求真实文献源。收藏和个人编辑由 Java / MyBatis 保存，保持黑马三层架构。

## 使用方式

更新后先重新启动 Java 和 Python，Vue 开发服务器会加载新的页面。Java 启动时通过 Flyway 自动应用 V3 迁移，为收藏关系增加个人元数据快照；无需删除现有数据库。

1. 在“我的资料库”创建收藏夹。
2. 打开“搜索论文”，输入关键词，选择自动、arXiv 或 OpenAlex，以及 1～20 条结果。
3. 展开摘要查看资料，选择目标收藏夹，点击“加入收藏夹”。重复添加保留已保存的个人笔记和修改。
4. 进入收藏夹，查看论文与笔记，点击“编辑论文资料”。可修改标题、摘要、作者、分类、发表时间及链接；来源和来源论文 ID 保持固定。
5. 不再需要时“移除论文”，只移除该收藏夹中的关系与笔记。其他收藏夹及已提交的研究历史不受影响。
6. 从该收藏夹发起新的研究，新任务使用提交时的个人论文快照；之后再改资料不会改写旧任务。

搜索和收藏不调用语言模型，无需 Qwen/OpenAI 模型 Key。Python 执行端和 Java 仍需要相同的 `PAPERFLOW_SERVICE_TOKEN`。启动三服务见 [Vue README](../frontend-vue/README.md)。

## 文献源配置与网络

arXiv 请求在 Python 进程的事件循环中串行，开始时间至少相隔 3 秒，遵循 [arXiv 官方 API 使用说明](https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md)。

OpenAlex 当前提供匿名访问额度，也可使用自己的 API Key 提高额度和查看用量，参考 [OpenAlex 官方鉴权说明](https://help.openalex.org/api/authentication/)。如果需要，在启动 Python 的 PowerShell 中配置：

```powershell
$env:OPENALEX_API_KEY = '自己的 OpenAlex API Key'
```

再启动或重启 Python。它与内部服务密钥、模型 API Key 是三种不同的配置；不需要把它放进 Vue 或 Java。

自动模式会依次尝试真实 arXiv 和 OpenAlex，不会回退到内置演示论文。成功但没有匹配内容时显示空结果；上游失败或超时则显示错误，可换来源重试。检索不会下载 PDF 正文，PDF 按钮只打开来源提供的链接。

## 对照三层架构读代码

| 层 | 代码 | 重点 |
|---|---|---|
| Vue 页面 | `views/PaperSearchView.vue` | 查询、来源、结果、收藏夹选择、失败保留结果 |
| Java Controller | `PaperSearchController` | 参数接收，统一 Result |
| Java Service 接口及实现 | `PaperSearchService`、`PaperSearchServiceImpl` | 参数与资料校验，超时和错误语义 |
| 内部 HTTP 客户端 | `WorkerClient.search` | 服务身份、编码查询词、响应大小与总超时 |
| Python 服务 | `services/paper_search.py` | 真实来源选择、回退、正常空结果与超时区分 |
| 检索适配器 | `tools/search.py` | arXiv Atom / OpenAlex JSON 解析、限流 |
| 资料业务 | `LibraryServiceImpl.updatePaper` | 资源归属、身份字段固定、个人快照 |
| MyBatis | `CollectionPaperMapper` | 只修改当前收藏关系的元数据 |

Java 新增接口：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/papers/search?query=关键词&source=auto&limit=10` | 已登录用户检索论文 |
| POST | `/api/library/collections/{id}/papers` | 添加搜索结果或手工录入论文，沿用已有接口 |
| GET | `/api/library/collections/{id}/papers/{paperRecordId}` | 本人收藏夹内论文详情 |
| PUT | 同上 | 保存该收藏夹的个人论文资料，使用 PaperDTO |
| DELETE | 同上 | 移除该收藏关系，沿用已有接口 |

`paperRecordId` 是数据库返回的数字 ID，不是 arXiv/OpenAlex 的字符串 ID。写操作仍需 CSRF。个人编辑不会更新共享 `pf_papers` 表；只有本人收藏关系新增 `metadata_json` 和 `metadata_edited`。手工录入或用户编辑的资料不会被宣称为已核验的科学事实。

## 验证范围

新行为覆盖参数、登录与服务身份、正常空结果、错误脱敏、超时、真实来源回退、个人编辑隔离、重复添加保留笔记，以及新任务快照与旧历史分离。完整测试和浏览器结果以实际验证记录为准。

从项目根目录运行检索与 CRUD 浏览器验收：

```powershell
.\.venv\Scripts\python.exe -B scripts\paper_search_smoke.py
```

此脚本使用真实 Vue / Java / Python 服务，但文献 API 边界使用**明确标注的本地 HTTP 测试源**，以稳定验证空结果、来源失败和回退。它不证明官方文献站点始终可用。正常 `worker` 启动不会导入测试源模块。

2026-10-19 另行真实联网检查：OpenAlex 官方 API 返回 200，实际搜索服务成功解析并返回两篇论文；arXiv 在当前网络出现读取超时。真实模型、MySQL/Redis 和生产部署不属于此次新增验证。

最终验证：74 项 Python 测试、34 项 Java 测试和打包、23 项前端测试、TypeScript 与生产构建全部通过。使用本地受控文献 API 的三服务浏览器验收覆盖搜索、空结果、502 错误、来源回退、两个本人收藏夹和另一用户的隔离、编辑作者姓名中的逗号、重复收藏、基于编辑资料的新研究和局部移除；旧版 Vue 工作流的浏览器回归也通过。桌面和手机搜索页面截图已检查。

记录见 `.tools/paper-search-e2e-smoke.json`、`.tools/paper-search-live-service.json`；受控文献源测试与真实外部可用性分别记录。正常启动不会读取测试源模块。

## 中文关键词与来源失败提示（2026-10-19 补充）

后续新增最相关、最新发表、引用最多和上游分页：引用排序使用 OpenAlex；翻页固定实际来源，重新搜索才重新选择来源。每页支持 10/20 篇，引用缺失显示未知。完整使用及学习报告说明见 `docs/study-report-learning.md`。

## 多关键词与 Crossref 备用来源

搜索条件现按登录账号保存到当前浏览器 localStorage。切换到资料库、研究任务再返回，或刷新页面，都会恢复已选关键词、逐项匹配方式、尚未添加的输入、文献来源、排序与每页数量。删除和清空立即更新保存内容；恢复时不会自动调用外部搜索。不同浏览器或设备之间不自动同步。浏览器禁止存储时会提示，搜索本身仍可使用。实现位于 Vue 的 `composables/searchDraft.ts`，账号状态来自原有 Pinia auth store；没有改动 Java/Python 接口。

关键词现在可以逐个添加到列表。输入后选择“精准匹配”或“模糊匹配”，按 Enter 或“添加关键词”；每项显示方式，可单独删除，也可清空。输入中的空格属于当前短语，不会自动拆成多个列表项。搜索按钮会将尚未添加的输入一起加入列表。

最多 10 个关键词，显示文本（含分隔符）总长度最多 500 个 UTF-16 单元；重复词忽略大小写并提示，保留原方式。精准按完整短语检索，模糊采用普通词检索，不承诺拼写纠错或任意子串匹配，也不自动翻译。arXiv/OpenAlex 组合关键词使用 AND；修改条件后重新搜索从第一页开始，翻页保留全部条件和实际来源。

本次另行联网检查，OpenAlex 和 Semantic Scholar 均返回 429，Crossref 返回 200，因此增加 Crossref 备用来源。引用排序的自动来源在全为模糊关键词时先试 OpenAlex，失败或空结果再尝试 Crossref。也可以手动选择 Crossref。

随后修复了默认“自动＋最相关/最新”没有尝试 Crossref 的遗漏：全为模糊词时按 arXiv → OpenAlex → Crossref 回退，精准词仍只使用能保持匹配语义的来源。2026-10-19 复查中，arXiv 在 8 秒边界超时，OpenAlex 限流，Crossref 约 3.3 秒返回 10 篇；记录见 `.tools/search-timeout-current-probe.json`。这是当次网络情况，不保证持续可用。

同轮真实“最相关”验证发现 Crossref 的 issued.date-parts=[[null]] 表示日期未知，旧解析把它判为错误而拒绝整页。现保留该论文、published 留空，其他正常日期不受影响。修复后 `multimodal learning / 自动 / 最相关 / 模糊` 实际用时 11.13 秒，回退 Crossref 返回 10 篇（3 篇日期未知），记录见 `.tools/auto-relevance-live-fixed.json`。105 项 Python 测试通过，受控三服务浏览器三项场景通过，包含默认最相关回退及原报告流程。

Google Scholar 官方帮助说明不提供批量访问并限制自动抓取；本项目没有直接抓取其网页。若后续接入，可评估第三方 SerpApi Google Scholar API，需单独服务凭证和可用额度；它不是 Google 官方 API。相关说明：[Google Scholar 帮助](https://scholar.google.com/intl/en/scholar/help.html)、[SerpApi 接口](https://serpapi.com/google-scholar-api)。当前未接入该付费/配额服务。

Crossref 使用宽泛书目信息匹配，不保证多个关键词同时出现，也不提供本项目所需的精准短语承诺，因此有精准词时不会回退到它，手动选择也会提示换源或改用模糊模式。其引用数仅统计 Crossref DOI 引用，不能与 OpenAlex 数字直接比较；部分论文没有摘要或开放 PDF，仍可收藏，但学习报告可能要求补充 PDF。

新增 SearchKeywordDTO 接收 text / match_mode，Java 校验并转交结构化关键词，Python 的 core/search_query.py 负责转义和编译，不让关键词变成查询运算符。结构化请求无需重复传 query，避免长中文 GET 超过服务器请求限制；旧 query 接口继续有效。

真实适配器结果见 `.tools/multi-keyword-crossref-live.json`；可用性探测见 `.tools/citation-sources-probe.json`。受控浏览器源和真实外部请求分开记录，不保证外部 API 随时可用。官方依据为 [Crossref 排序与引用口径](https://github.com/CrossRef/rest-api-doc)、[OpenAlex 匹配语法](https://help.openalex.org/api/searching/)和 [OpenAlex 限流说明](https://help.openalex.org/api/authentication/)。

此次验证通过 103 项 Python、47 项 Java、36 项 Vue 测试及 Java/Vue 构建。三项浏览器场景通过，包括真实本地 Tomcat 接收 500 字中文关键词、混合模式与删除、条件保持翻页、Crossref 自动回退和收藏，以及原有单篇/多篇学习报告与 DOCX 下载。桌面和手机关键词列表截图已检查。文献、PDF 和模型的受控测试边界明确标注，真实来源联网记录独立保存。

搜索不会自动翻译中文；arXiv 适配器使用完整短语匹配。本次真实联网复查中，“多模态论文”在 arXiv 返回 0 篇，英文 `multimodal learning` 返回 3 篇，OpenAlex 返回 HTTP 429（限流）。外部站点状态会变化，这与当天较早的联网记录并不矛盾。

自动模式下，一个来源正常返回空结果、另一个来源失败时，响应仍保留正常空结果，并通过 `warnings` 标出未完成检索的来源。页面显示来源失败原因，也会在输入中文时提示尝试英文关键词；不会把来源失败解释成没有相关论文。所有来源均被限流时返回 HTTP 429。

Java 到 Python 的 HTTP 客户端显式使用 HTTP/1.1，避免 HTTP/2 升级请求导致 Uvicorn 输出 `Unsupported upgrade request`。该警告本身不等于搜索失败，日志中的 HTTP 200 也只表示接口成功响应，不保证结果非空。

更新后需重启 Java、Python 服务并刷新 Vue 页面。此次回归通过 76 项 Python 测试、36 项 Java 测试及打包、24 项 Vue 测试和生产构建。使用受控文献源的三服务浏览器验收通过，验收期间 Python 日志未再出现 HTTP 升级警告；这不代表真实外部来源始终可用。
