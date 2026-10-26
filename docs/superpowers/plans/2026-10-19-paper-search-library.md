# 论文网站搜索与收藏夹论文 CRUD

按用户确认复用现有 arXiv / OpenAlex。使用 writing-plans、test-driven-development；Python 搜索、收藏关系元数据修改、Vue 页面可并行委派，Maven 构建和最终联调串行执行。保留黑马单模块三层结构。

## 设计与边界

Vue 新增“搜索论文”导航和 `/papers` 页面，填写关键词、选择自动/arXiv/OpenAlex、结果数量1～20。显示标题、作者、摘要、日期、来源和 HTTP(S) 外链；选择本人收藏夹后调用现有添加论文接口，重复添加保留原笔记。空结果与外部网站错误分别显示，不使用示例数据伪装在线检索。

链路：Vue GET `/api/papers/search?query=...&source=auto&limit=10` → Java 认证与参数校验 → Python 带内部服务凭证的 GET `/internal/v1/papers/search` → 现有检索适配器。查询主题1～500字符，source仅auto/arxiv/openalex，limit1～20。Python 响应 `{contract_version:1,query,requested_source,used_source,papers}`。Java 返回同样数据包在 Result.data 中。成功空结果 papers为空；外部服务失败502，超时504；错误脱敏。自动模式可尝试另一个真实来源，不回退fixture。

Java 搜索调用不占数据库事务，独立总超时25秒；浏览器搜索请求总超时30秒。Worker 内部搜索复用现有适配器；arXiv遵循每次请求间隔至少3秒且单连接的限制。OpenAlex Key仅在Python环境配置，不出现在Vue或日志中；网络与服务额度会影响真实结果。

收藏夹论文新增 GET/PUT `/api/library/collections/{collectionId}/papers/{paperRecordId}`。PUT使用现有PaperDTO，source和paper_id不可改；改标题、摘要、作者、分类、发表时间或链接仅影响该收藏夹的个人资料。新增Flyway V3为关联表增加 `metadata_json MEDIUMTEXT NULL` 和 `metadata_edited BOOLEAN NOT NULL DEFAULT FALSE`。默认读取共享论文原始元数据；编辑后读取关联的个人快照。重复添加不清空个人快照与笔记，删除仅移除该收藏关系。所有操作先检查owner及membership。研究任务提交时沿用收藏夹detail接口，所以新任务使用个人编辑后的快照，旧任务输入与报告不被改写。

原手工录入继续保留，不自动声称用户提交的论文元数据经过外部核验。不修改共享论文表来实现个人编辑。搜索结果通过现有添加接口入库，无需新建账号体系或改动凭证。

## 文件分工与验收

- [x] Python：新搜索服务/worker内部路由、正常/空结果/失败/参数/鉴权/回退测试，先观察失败再实现。可注入检索工厂或httpx transport做离线测试，但正常启动始终真实来源。
- [x] Java收藏夹：V3、关联实体/Mapper、详情与修改接口、ServiceImpl个人快照、双用户/双收藏夹/重复添加/事务/新研究快照测试，先失败后实现。
- [x] Java搜索：WorkerClient复用有界HTTP传输，搜索Service/Controller/VO、认证校验与上游故障测试；不使用浏览器提供的远端URL。
- [x] Vue：搜索页、API和类型、导航，以及收藏夹论文编辑；请求不重叠、旧响应隔离、错误与空结果、URL安全、选择收藏夹与成功提示。先行为测试后实现。
- [x] 联调：真实三服务浏览器检索→收藏→查→改→重新研究→删除；外部文献API不稳定时可在文献源边界提供明确标注的受控HTTP测试源，不改变正常启动默认源。
- [x] 独立审查，完整Python/Java/前端测试与构建；实际尝试官方来源连接并记录真实状态，不把离线替身通过说成外部API可用。
- [x] 更新启动、OpenAlex可选凭证、学习文档和当前功能范围。

## 实际完成与验证

74 项 Python 测试通过；34 项 Java 测试通过并成功打包；23 项前端测试、TypeScript 与 Vite 构建通过。独立只读审查没有剩余可操作的阻塞问题。

三服务浏览器验收通过，文献源边界采用明确标注的本地真实 HTTP 测试源，验证两种解析器、空结果、失败/回退、收藏与个人编辑及新研究快照、用户隔离和局部删除。原有Vue浏览器流程也通过，临时进程与数据库清理。真实OpenAlex API与实际Python搜索服务单独成功；arXiv当前网络读取超时，已记录，不声称外部两站点都验收通过。

正常worker仍只请求真实API，没有默认fixture模式。更新需重启Java/Python；V3自动迁移，Vue刷新加载新导航。
