# 对照黑马课程理解 Java 后端

采用你选定的 Spring Boot 单模块三层结构，使用 MyBatis，不拆微服务。

## 每层负责什么

| 目录 | 对应代码 | 职责 |
|---|---|---|
| `controller` | `LibraryController` | 接收 HTTP 请求，校验 DTO，获取当前用户，调用 Service，返回 `Result<VO>` |
| `service` | `LibraryService` | 定义业务功能的接口 |
| `service/impl` | `LibraryServiceImpl` | 实现权限判断、业务规则与 `@Transactional` 事务 |
| `mapper` | `CollectionMapper` | 编写 MyBatis SQL，用 `#{}` 绑定参数 |
| `entity` | `PaperCollection` | 对应数据库记录，普通 JavaBean |
| `dto` | `CollectionDTO` | 接收前端输入，如收藏夹名称和描述 |
| `vo` | `CollectionVO` | 返回页面需要的字段，不暴露数据库内部字段 |
| `common` | `Result`、`ApiExceptionHandler` | 统一响应与异常处理 |
| `config`、`auth` | 安全配置、`UserPrincipal` | 登录验证、会话及当前用户身份 |
| `client` | `WorkerClient` | 通过 HTTP 调用 Python |
| `task` | `ResearchSynchronizer` | 定时同步研究任务 |

## 先跟一条熟悉的 CRUD 请求

前端提交 `POST /api/library/collections`：

1. `CollectionDTO` 接收 `name`、`description`。
2. `LibraryController` 从登录会话取得用户 ID，调用 `LibraryService.create(...)`。
3. Spring 注入 `LibraryServiceImpl`；它检查本人是否已有同名收藏夹。
4. `CollectionMapper.insert(...)` 执行 `INSERT`，MyBatis 回填生成的 ID。
5. Service 组装 `CollectionVO`，Controller 使用 `Result.success(vo)` 返回。

成功响应示例：

```json
{"code":1,"msg":null,"data":{"id":1,"name":"Agent 阅读计划","description":"","paper_count":0}}
```

`DTO`、`VO` 部分使用 Java `record` 声明。它是固定字段的数据载体，编译器生成构造方法与读取方法，例如 `dto.name()`；用途对应课程里的 DTO/VO 类。数据库实体使用熟悉的私有字段及 getter/setter，方便理解 MyBatis 映射和新增主键回填。

## 再看研究任务怎样扩展三层架构

`ResearchController → ResearchTaskService → ResearchTaskServiceImpl → ResearchTaskMapper` 先保存任务，快速返回任务 ID。长时间运行的 Agent 不在提交请求的数据库事务内执行。

随后 `ResearchSynchronizer` 定时取待执行任务，通过 `WorkerClient` 调用 Python。Python 运行现有 `ResearchService`，执行检索、RAG、分析、综合和构思；Java 再通过 `ResearchTaskStore` 接口及其实现保存状态和报告。

这里可以学到普通 CRUD 之外的内容：HTTP 服务调用、超时、异步任务、幂等、任务状态机和故障恢复。Agent 的提示词、证据检索与工作流仍在 Python，可继续沿原有学习路径阅读。

## 数据库与旧版本

Flyway 负责建表和版本迁移，MyBatis 负责 SQL 查询与修改。原有 `pf_` 数据表保留，新增 V2 任务表；不需要删除本地数据来切换 MyBatis。修改业务字段时增加迁移，并同步实体和 Mapper。

第二阶段早期实现使用过 JPA；目前 Java 代码已统一改用 MyBatis。已有测试继续验证业务行为，同时适配统一的 `Result.data` 响应结构。旧 React 网页仍使用 Python，不使用这套 Java 登录账号。

建议阅读顺序：收藏夹创建 → 论文添加与事务回滚 → 注册登录 → 研究任务提交 → 后台同步 → Python Agent 执行。

启动与接口示例：[Java README](../java-backend/README.md)。任务学习：[第三阶段说明](phase3-learning.md)。

MyBatis 集成使用与当前 Spring Boot 3.5 对应的 3.0 系列 Starter，固定为 3.0.5；兼容范围参考 [MyBatis 官方说明](https://mybatis.org/spring-boot-starter/mybatis-spring-boot-autoconfigure/)。
