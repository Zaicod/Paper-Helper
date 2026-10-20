# 第三阶段：Java 与 Python 研究任务闭环

本计划细化已批准的整体方案第三阶段，按测试先行执行。独立的 Python 执行端和 Java 业务端可并行委派，联调与最终构建串行执行。无 Git 仓库，不创建提交。

## 契约与边界

- Java POST `/api/research/tasks`：必填 `idempotency_key`（UUID）、`topic`（1～500）、`mode`（demo/live）；可选 `limit`（默认3，1～20）、`rag`（none/abstract，默认abstract）、`provider`（qwen/openai，默认qwen）、`model`（最多128）、`collection_id`、`paper_ids`（收藏夹内数字 ID，1～20）。提供收藏夹时从 Java 数据库解析论文，不接收浏览器论文元数据；未指定 paper_ids 时选全部，超20拒绝。未指定收藏夹时 Python 按主题检索。
- 同一用户的 idempotency_key 对同一规范化输入返回同一任务，输入不同409；重放不重新读取已变化的收藏夹来覆写任务快照。任务拥有独立 UUID、owner_id 和提交时参数快照，删除收藏夹不删除任务历史。
- Java GET `/api/research/tasks` 分页本人任务；GET `/{id}` 返回本人任务及报告，越权404。所有写操作沿用登录与 CSRF。
- Python POST `/internal/v1/tasks/{task_id}`，Bearer 服务密钥，JSON：`contract_version:1,topic,limit,options:{mode,rag,provider,model?},papers:null或Paper[]`。UUID 作为幂等执行ID；相同内容重放200，不同409；首次202。
- Python GET 相同路径返回快照：`contract_version:1,task_id,status,events,report,error_code,error_message`；不存在404。status：queued/running/completed/failed/interrupted。report 为现有 ResearchReport 的 JSON，events 为 ResearchStageEvent[]（至多200）。completed必须有report，其他状态report为null；错误不返回堆栈、密钥或原始外部异常。
- Python 使用独立 SQLite 执行账本，持久化输入哈希、状态、事件和报告，后台调用现有 ResearchService。限制待处理队列与并发；启动时把原queued/running标记interrupted。同一账本仅允许单进程使用，默认绑定127.0.0.1，不开放跨域。密钥必须配置且至少32字符。
- Java Flyway V2 创建独立任务表，保存输入、结果、事件与状态。定时后台提交和轮询；网络调用不占数据库事务。提交超时保留原任务ID重试，不自动生成新执行；通信错误保留可查询任务及安全提示。超过总同步期限标记interrupted，提示远端可能仍在执行，不声称已取消。
- 服务地址和密钥仅来自环境配置；未配置时 Java 业务仍可启动，研究提交返回503。模型凭证只由 Python 环境提供，本阶段不迁移个人模型设置。
- Java 单实例同步器、Python 单执行进程作为首版运行边界；无消息队列、自动续跑、Vue迁移、PDF远端下载或新模型SDK。

## 实施清单

### 用户追加的 Java 架构要求

用户明确选择黑马 Spring Boot 单模块三层结构与 MyBatis。所有 Java 模块统一使用 `controller → service 接口 → service.impl → mapper`，普通 `entity`、独立 `dto`/`vo`。移除早期 JPA，保留已有 Flyway SQL 和数据库数据；Mapper 使用显式 SQL，ServiceImpl 使用事务。成功响应统一 `Result {code:1,msg:null,data:业务对象}`，错误 `code:0,msg:安全提示,data:null`，204 无正文，HTTP 状态含义不变。既有 Java 演练与测试同步适配。Python 内部任务契约不使用该 Result 包装。

- [x] Python：先写服务身份、幂等冲突、后台完成、失败脱敏、事件与报告落盘、重启中断测试；验证失败后实现独立执行账本与 FastAPI 入口。
- [x] Java：先写认证、任务幂等、归属、可信论文快照、状态同步与故障恢复测试；验证失败后实现任务表、DTO、服务、控制器与HTTP轮询客户端。
- [x] 联调：打包 Java，启动真实 Python 和 Java；注册、收藏论文、创建demo研究、轮询报告、同键重放、双用户越权、重启读取历史。
- [x] 验证：运行完整 Python / Java 测试，审查幂等、事务和异常边界；记录没有验证的真实模型与MySQL/Redis环境。
- [x] 文档：启动脚本/示例、环境变量、第三阶段学习路线、当前架构与已知限制。

## 验收依据

离线 demo 闭环真实经过 HTTP 和现有 Agent/RAG，不用假报告替代联调。测试以执行次数、数据库状态、持久化结果和用户资源归属为依据；进程重启只恢复查询历史，不自动恢复模型调用。

## 最终验证记录

2026-10-18：26 项 Java 测试通过，可执行 jar 构建成功（Windows 启动脚本选择本机 JDK 25，编译目标21）。64 项 Python 测试通过。真实双服务联调62次 HTTP 检查、3个离线研究任务、Java与Python各重启一次后历史仍可查询；原资料HTTP验证32次检查及一次Java重启通过。HTTP次数包含轮询。

代码审查发现并修复了并发幂等提交冲突、跨语言标题长度不一致、收到响应头后正文等待无总超时三项问题；新增回归均观察到修复前预期失败，修复后通过。复查无剩余可操作问题。

真实模型、MySQL/Redis、生产部署与Vue页面未在本次验证。旧网页仍使用原Python入口；内部任务协议使用环境服务密钥，未迁移个人模型凭证。进程重启可以查历史，不代表自动续跑。
