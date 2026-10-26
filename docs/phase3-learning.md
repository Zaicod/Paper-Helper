# 第三阶段：让 Java 管业务，让 Python 执行 Agent

这一阶段把两个已能独立运行的服务接起来。Java 保存登录用户提交的任务、论文快照、进度和报告；Python 复用原有 ResearchService 执行检索、摘要 RAG、逐篇分析、综合和研究构思。

浏览器只需要登录 Java，并调用 `/api/research/tasks`。成功响应统一为 `{code: 1, msg: null, data: ...}`，失败为 `{code: 0, msg: 安全提示, data: null}`；删除成功仍返回无正文的 HTTP 204。Python 的 `/internal/v1/tasks/{task_id}` 是内部执行接口，要求独立的 Bearer 服务密钥，不接受 Java 登录 Cookie。

## 先理解一条完整请求

1. 用户登录 Java，取得 CSRF token，提交主题或自己的收藏夹论文 ID。
2. Java 检查收藏夹归属，从数据库读取论文元数据，把输入快照和任务 UUID 保存下来。
3. 后台同步器把相同 UUID 和快照发送到 Python。HTTP 调用期间不占用数据库事务。
4. Python 在 SQLite 账本记录执行 ID 与输入哈希，后台运行 ResearchService，并持续保存事件。
5. Java 轮询 Python，把状态和最终报告写回业务数据库。用户刷新或重新登录后仍可查询。

`demo` 会真实执行上述 HTTP、持久化和 Agent/RAG 工作流，但用演示研究团队生成明确标注为演示的内容，不需要模型密钥，也不能据此判断真实模型的研究质量。

## Java 学习重点

Java 采用黑马课程常见的单模块分层：`controller → service 接口 → service/impl → mapper → entity`，输入放 `dto`，输出放 `vo`，统一响应使用 `Result`。Mapper 使用 MyBatis 的显式 SQL；项目没有 Spring Data JPA Repository，也不依赖实体脏检查自动保存。

先看任务 Controller 如何接收 DTO 和当前登录用户，再看 Service 接口及实现类如何解析用户拥有的收藏论文、生成快照和检查幂等键。接着看 Mapper 的 SQL 如何同时限定用户与资源 ID。最后看后台同步器如何把一次长任务拆成多次短 HTTP 请求。

以收藏夹笔记为例，Controller 调用 `LibraryService.collectionNote`，`LibraryServiceImpl` 先验证收藏夹归属，再调用 `CollectionMapper.updateNote`。只有明确执行 UPDATE，修改才会写进数据库。`@Transactional` 把相关 SQL 组成一次提交或回滚。

这比普通增删改查多了三件事：

- **状态机**：queued、running、completed、failed、interrupted 各自代表什么；只有 completed 才有报告。
- **事务边界**：先把任务保存下来，再调用远程服务；网络超时不应该让数据库连接一直被事务占用。
- **幂等**：同一用户使用相同 idempotency_key 和相同输入，应拿到同一个任务。相同键改了输入返回 409；重新发送不能产生新的执行 ID。

特别观察：收藏夹删除后，已提交任务的论文快照和报告仍然存在；重放旧请求也不重新读取收藏夹。任务历史属于提交它的用户，知道 UUID 并不等于有查询权限。

## Agent 学习重点

从 `paper_agent/services/research.py` 阅读到 `paper_agent/workflows/research.py`：执行端只是适配器，原有研究逻辑仍集中在服务与工作流。接着阅读独立 worker 的账本与 HTTP 接口，理解任务接收、后台执行和结果查询为何分开。

报告中的 `context_audits` 记录检索选中的片段、上下文预算和来源模式；`events` 记录 search、index、analyze、synthesize、ideate 的进展。报告存在、事件完整和证据审计有内容，比单纯收到 HTTP 200 更能说明链路已跑通。

幂等账本可以避免相同执行 ID 被重复接收为新任务，但这不等于分布式系统已经实现任意故障下的模型“恰好调用一次”。进程崩溃时，任务被标为 interrupted，需要用户决定是否创建新任务；不会自动重放潜在昂贵的模型调用。

## 运行与自测

先按 `java-backend/README.md` 安装 Python 依赖并打包 Java，然后在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -B .\java-backend\scripts\bridge_smoke.py
```

脚本会启动实际的 Java jar 与 Python worker，使用临时 H2、SQLite 数据库和随机端口；创建两个用户，研究收藏论文和主题检索论文，检查报告、证据审计、幂等、越权及双服务重启后的历史。最后只停止自己启动的进程并清理临时数据库。

运行日志在 `.tools/java-phase3-business-smoke.log` 和 `.tools/java-phase3-worker-smoke.log`；成功结果写入 `.tools/java-phase3-bridge-smoke.json`。联调结果以实际运行产物为准，不把脚本存在视为验证已经通过。

2026-10-18 已使用当前 MyBatis / Result 架构的打包服务完成真实联调：双服务脚本通过 62 次 HTTP 检查，完成 3 个离线 demo 任务，并分别重启 Java、Python 各一次，确认任务与报告历史仍可查询。原收藏夹脚本也通过 32 次 HTTP 检查及一次 Java 重启，确认迁移后收藏夹和私人笔记仍正常。

这些检查覆盖 Java 登录与 CSRF、可信收藏论文快照、主题检索、RAG 证据审计、完整工作流事件、两层幂等冲突、用户隔离、删除收藏夹后保留任务，以及双服务重启后的持久化。HTTP 次数包含状态轮询，不等同于独立测试用例数量。

阅读 Java 代码前，可先看 [Java 分层与调用链](java-architecture.md)。完整 Python / Java 测试结果以项目启动文档中的验证记录为准。

本阶段仍使用单个 Java 同步器实例和单个 Python 执行进程，没有消息队列或自动续跑。MySQL/Redis、真实模型需独立验证。2026-10-19 新 Vue 工作台已接入这些任务接口，见 [Vue 学习说明](vue-learning.md)；旧 React 页面继续走原 Python 接口。
