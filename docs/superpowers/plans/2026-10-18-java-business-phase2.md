# Java 用户与资料管理第二阶段实施计划

> **For agentic workers:** Use the executing-plans and test-driven-development workflows to implement this approved phase task by task. Independent authentication and library components may be delegated; serialize Maven builds because they share one output directory.

**Goal:** 新增可独立运行的 Java 业务服务，实现账户、会话、收藏夹、论文关联与笔记，并验证用户之间的数据隔离。

**Architecture:** Java 服务位于 `java-backend/`，使用独立的 `pf_` 业务表。默认本地 H2 文件数据库和 Servlet 会话，`mysql` 配置使用 MySQL 与 Redis 会话。现有 Python 研究入口保持可用；本阶段不自动切换旧网页、不迁移现有全局资料，不将旧账号密码或会话当成 Java 账号。

**Tech Stack:** Spring Boot 3.5.16、Spring Security、Spring Data JPA、Bean Validation、Flyway、H2、MySQL、Spring Session Redis、Maven Wrapper；Java 编译目标 21，当前机器使用现有 JDK 25 构建。

## 约束与接口约定

- 旧 Python 数据不写入；新服务使用独立数据库配置和 `pf_` 表。
- 所有收藏夹读取与修改先以 `id + owner_id` 定位资源；不存在和不属于本人都返回 404。
- 全局论文元数据去重，个人收藏关联与笔记按收藏夹隔离；用户提交的元数据不能覆写已有共享论文。
- JSON 使用 snake_case。错误响应仅返回安全的 `{ "detail": "..." }`。
- 未登录返回 401；缺少或错误的 CSRF 凭证返回 403；字段无效 400；冲突 409。
- 会话 cookie 使用 `paperflow_java_session`，与 Python 会话分开。HTTP-only、SameSite=Lax；HTTPS 环境可开启 Secure。
- GET `/api/auth/csrf` 获取 CSRF token，所有写请求携带其 header；登录和注册之后刷新 token。
- BCrypt 密码不以明文保存；限制 UTF-8 编码长度以避免 BCrypt 72 字节上限问题。
- 所有新修改操作由服务层事务包裹；数据库约束提供最终并发保护。
- 测试不要求外部 MySQL/Redis，不调用真实模型。MySQL/Redis 通过独立配置和可选容器验证。

## 任务一：构建、独立数据模型与迁移

文件：`java-backend/pom.xml`、`PaperflowApplication.java`、`application*.yml`、`db/migration/V1__business_library.sql`、Maven Wrapper。

- [x] 建立 Java 21 编译目标、固定 Spring Boot 和 Maven Wrapper 版本。
- [x] 创建 `pf_users`、`pf_collections`、`pf_papers`、`pf_collection_papers` 表和归属、唯一、外键约束。
- [x] 默认使用 H2 文件，测试使用 H2 内存，MySQL 地址与密码仅从环境配置读取。
- [x] 用 Flyway 初始化，Hibernate 只执行 validate，不以自动 DDL 修改旧表。
- [x] 验证迁移、应用启动和可执行 jar 构建。

## 任务二：注册、登录与安全会话

文件：`cn/paperflow/auth/`、`cn/paperflow/config/`、`auth/AuthIntegrationTest.java`。

对外接口：

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/api/auth/csrf` | 返回 token 与 header_name |
| POST | `/api/auth/register` | 创建账号并登录，201 |
| POST | `/api/auth/login` | 用户名或邮箱登录，200 |
| GET | `/api/auth/me` | 当前账号 |
| POST | `/api/auth/logout` | 清除会话，204 |

内部接口：`UserPrincipal.id()` 返回已认证用户 ID，供业务控制器使用；`UserAccount` 与 `UserRepository` 只在后端处理密码哈希。

- [x] 先编写账户、CSRF、会话和失败登录测试，记录预期失败。
- [x] 实现标准化用户名/邮箱、唯一约束、密码编码和安全错误响应。
- [x] 显式保存认证上下文；认证成功时轮换会话 ID 并清除旧 CSRF token。
- [x] 配置 mysql profile 的 Redis 会话与 cookie，默认本地模式不连接 Redis。
- [x] 测试重复账号、错误密码、密码哈希、退出失效及 CSRF 保护。

## 任务三：用户隔离的收藏夹、论文与笔记

文件：`cn/paperflow/library/`、`library/LibraryApiTest.java`。

对外接口：

| 方法 | 路径 | 行为 |
|---|---|---|
| GET/POST | `/api/library/collections` | 本人的分页列表/创建 |
| GET/PUT/DELETE | `/api/library/collections/{id}` | 详情/修改/删除 |
| PUT | `/api/library/collections/{id}/note` | 更新收藏夹笔记 |
| POST | `/api/library/collections/{id}/papers` | 添加论文元数据与个人关联 |
| DELETE | `/api/library/collections/{id}/papers/{paperRecordId}` | 移除关联，不删除共享论文 |
| PUT | `/api/library/collections/{id}/paper-note` | 更新本人收藏夹中已有论文的笔记 |

首次论文录入提交 `source`、`paper_id`、`title`、`abstract`、`authors`、`categories`、`page_url` 等元数据。它是资料管理入口，本阶段不宣称元数据已由外部文献源核验。

- [x] 先编写双用户越权测试，记录预期失败。
- [x] 实现先校验归属、后读取或写入关联数据的事务服务。
- [x] 同名收藏夹跨用户允许，同一用户内冲突；列表与搜索不泄露其他用户结果。
- [x] 重复添加论文不清空已有笔记；删除收藏夹只删除本人关联与笔记。
- [x] 验证关联写入失败时，论文与关联写入共同回滚。

## 任务四：联调、运行和学习资料

文件：`java-backend/README.md`、`java-backend/scripts/`、`docs/phase2-learning.md`、根目录 README。

- [x] 通过实际 HTTP 会话验证 CSRF → 注册 → 创建收藏夹 → 添加论文 → 写笔记 → 登录另一账号拒绝访问 → 退出。
- [x] 检查 mysql profile 的配置绑定与 Redis 会话实现；具备可用容器服务时才执行外部集成。
- [x] 构建可执行 jar，验证本地模式不需要外部数据库或 Redis。
- [x] 运行原 Python 回归，确认研究能力保持可用。
- [x] 独立代码审查后修复已确认问题，记录验证结果与尚未覆盖的环境。
- [x] 更新项目说明，明确 Java 服务、旧 Python 网页和后续任务接入之间的边界。

## 构建与验证命令

从 `java-backend` 目录执行，进程内设置项目 JDK（不改系统默认）：

```powershell
$env:JAVA_HOME = 'C:\Users\20476\.jdks\openjdk-25'
.\mvnw.cmd -B -ntp test
.\mvnw.cmd -B -ntp package
```

从项目根目录执行 Python 回归：

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

每项测试的断言以 HTTP 行为、资源归属和数据库状态为依据；不把测试本身调用的模拟行为当作业务功能证据。

## 实施验证记录

第二阶段已实施并完成独立代码审查。18 项 Java 集成测试通过，可执行 jar 构建成功；32 项真实 HTTP 检查通过，包含一次服务重启及重新登录后读取资料；原 Python 55 项回归测试通过。编译产物为 Java 21 字节码，本机使用 JDK 25 构建。

MySQL profile 与 Redis 会话配置已检查，但本次未启动真实 MySQL/Redis，外部集成仍待验证。旧 React 继续调用 Python；没有迁移旧账号或资料，没有接入 Java → Python 研究任务或 Vue 页面。
