# Java 业务后端：黑马三层架构与研究任务

这个独立的 Spring Boot 服务负责账号、会话、收藏夹、论文关联、笔记和持久化研究任务。Python 通过独立内部 HTTP 服务执行 Agent、RAG 和研究流程。Java 按你选定的黑马 Spring Boot 单模块三层结构组织，数据访问使用 MyBatis。

当前旧 React 页面仍调用 Python，尚未切换到这里。Java 与旧 Python 网页的账号、会话和数据独立，没有自动迁移旧账号、密码或收藏夹。论文添加接口接收元数据，搜索接口通过 Python 请求真实文献源；用户手工录入或编辑的资料不会被宣称为已核验。

2026-10-19 已新增 [Vue 工作台](../frontend-vue/README.md)，通过同源代理连接这里的 Java 接口，包含登录、资料与笔记、研究任务和报告。以下 PowerShell 示例仍可用于独立学习接口。

同日新增 arXiv/OpenAlex 搜索与收藏夹论文 GET/PUT：已登录用户可通过 `/api/papers/search` 检索，复用添加接口收藏；个人编辑保存在 V3 收藏关系快照中，不修改共享论文。参数、API 表及配置见 [论文搜索与 CRUD](../docs/paper-search-learning.md)。

## 快速启动

代码目录对应你学习的三层架构：

```text
cn.paperflow/
  controller/    接收请求、校验 DTO、返回 Result<VO>
  service/       业务接口
    impl/        业务规则、权限检查、事务
  mapper/        MyBatis 接口和 SQL
  entity/        数据库记录，普通 JavaBean
  dto/           前端提交的数据
  vo/            返回前端的数据
  common/        Result、异常与统一错误处理
  config/        安全、会话等配置
  client/        调用 Python 服务
  task/          定时同步研究任务
```

先沿 `LibraryController → LibraryService → LibraryServiceImpl → CollectionMapper` 阅读收藏夹创建路径，再看 `ResearchController` 的异步任务。Mapper 中使用 `#{参数}` 绑定 SQL 参数；Entity 不直接返回给浏览器。

在 Windows PowerShell 中执行：

```powershell
Set-Location D:\20476\Pictures\agent\java-backend
.\run-local.cmd
```

默认地址为 `http://127.0.0.1:8080`。这是 JSON API 服务，没有独立首页和 Swagger 页面；请用下面的请求示例体验。

项目使用 Spring Boot 3.5.16，Java 编译目标为 21。脚本按项目配置、`JAVA_HOME`、用户 `.jdks` 目录及可用编译器寻找 JDK 21～25。当前机器已有 JDK 25 可以使用；脚本仅在子进程内选择项目 JDK，不改变系统默认 JDK 8。

如自动查找失败，指定自己的安装目录：

```powershell
$env:PAPERFLOW_JAVA_HOME = 'C:\Users\20476\.jdks\openjdk-25'
.\run-local.cmd
```

Maven Wrapper 首次运行需要联网下载 Maven 和依赖。默认 `local` 配置使用 `java-backend/data/paperflow-business` 对应的 H2 文件数据库，无需安装 MySQL 或 Redis。停止服务后账号与资料仍保留；本地 Servlet 会话保存在内存，重启后需重新登录。不要同时启动两个进程使用同一个 H2 文件。

## 用一次完整请求理解业务

先保持服务运行，再打开另一个 PowerShell 窗口，按顺序执行。示例使用独立会话保存 Cookie，所有写请求携带 CSRF 请求头；注册或登录成功后必须重新获取 token。

以下辅助函数会把 JSON 作为 UTF-8 发送，适用于 Windows PowerShell：

```powershell
$base = 'http://127.0.0.1:8080'
function Get-PaperflowCsrf($Session) {
    $csrf = (Invoke-RestMethod "$base/api/auth/csrf" -WebSession $Session).data
    $headers = @{}
    $headers[$csrf.header_name] = $csrf.token
    return $headers
}
function Send-PaperflowJson($Method, $Path, $Body, $Session, $Headers) {
    $request = @{
        Uri = "$base$Path"
        Method = $Method
        WebSession = $Session
        Headers = $Headers
    }
    if ($null -ne $Body) {
        $request.ContentType = 'application/json; charset=utf-8'
        $request.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 10))
    }
    $result = Invoke-RestMethod @request
    if ($null -ne $result) { return $result.data }
}
```

注册账号 A 并创建收藏夹。每次演练生成新用户名，避免重复注册冲突：

```powershell
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 12)
$username = "reader_$suffix"
$password = 'LearningOnly123!'
$sessionA = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$headersA = Get-PaperflowCsrf $sessionA
$accountA = Send-PaperflowJson Post '/api/auth/register' @{
    username = $username
    email = "$username@example.com"
    password = $password
} $sessionA $headersA
$headersA = Get-PaperflowCsrf $sessionA
Invoke-RestMethod "$base/api/auth/me" -WebSession $sessionA

$collection = Send-PaperflowJson Post '/api/library/collections' @{
    name = 'Agent 阅读计划'
    description = '学习工具调用与证据检索'
} $sessionA $headersA
$collectionId = $collection.id
```

录入一条演示元数据，并保存论文笔记和收藏夹笔记。这里的标题与摘要仅用于演练：

```powershell
$externalId = "learning-$suffix"
$paper = Send-PaperflowJson Post "/api/library/collections/$collectionId/papers" @{
    source = 'manual'
    paper_id = $externalId
    title = 'Agent learning example'
    abstract = 'Manual metadata for a local API exercise.'
    authors = @('Learning user')
    categories = @('agent')
    page_url = 'https://example.com/paper'
} $sessionA $headersA

Send-PaperflowJson Put "/api/library/collections/$collectionId/paper-note" @{
    source = 'manual'; paper_id = $externalId; content = '关注检索失败时的停止条件。'
} $sessionA $headersA
Send-PaperflowJson Put "/api/library/collections/$collectionId/note" @{
    content = '先读工具调用，再比较 RAG 检索方案。'
} $sessionA $headersA
Invoke-RestMethod "$base/api/library/collections/$collectionId" -WebSession $sessionA
Invoke-RestMethod "$base/api/library/collections?page=0&size=10&query=Agent" -WebSession $sessionA
```

验证另一位用户不能读取该收藏夹：

```powershell
$sessionB = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$headersB = Get-PaperflowCsrf $sessionB
$usernameB = "other_$suffix"
$accountB = Send-PaperflowJson Post '/api/auth/register' @{
    username = $usernameB; email = "$usernameB@example.com"; password = $password
} $sessionB $headersB
$headersB = Get-PaperflowCsrf $sessionB
try {
    Invoke-RestMethod "$base/api/library/collections/$collectionId" -WebSession $sessionB
    throw '隔离验证失败：账号 B 读取到了账号 A 的收藏夹。'
} catch {
    if ($null -eq $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 404) { throw }
    '预期结果：账号 B 收到 404。'
}
Send-PaperflowJson Post '/api/auth/logout' $null $sessionB $headersB
```

账号 A 退出后重新登录，再更新和删除演练资料：

```powershell
Send-PaperflowJson Post '/api/auth/logout' $null $sessionA $headersA
$headersA = Get-PaperflowCsrf $sessionA
$loggedIn = Send-PaperflowJson Post '/api/auth/login' @{
    identifier = $username; password = $password
} $sessionA $headersA
$headersA = Get-PaperflowCsrf $sessionA

Send-PaperflowJson Put "/api/library/collections/$collectionId" @{
    name = 'Agent 阅读计划已演练'; description = '已验证登录、笔记和用户隔离'
} $sessionA $headersA
Send-PaperflowJson Delete "/api/library/collections/$collectionId/papers/$($paper.id)" $null $sessionA $headersA
Send-PaperflowJson Delete "/api/library/collections/$collectionId" $null $sessionA $headersA
Send-PaperflowJson Post '/api/auth/logout' $null $sessionA $headersA
```

演练会保留新建账号和共享论文元数据。移除论文仅删除本人收藏夹的关联与笔记，不删除其他收藏夹可能使用的共享论文。

## 接口约定

JSON 字段使用 `snake_case`；成功返回 `{ "code": 1, "msg": null, "data": ... }`，错误返回 `{ "code": 0, "msg": "安全错误信息", "data": null }`，同时保留准确的 HTTP 状态码。204 响应没有正文。下面辅助函数已解包 `data`。除获取 CSRF 和注册、登录外，业务接口都需要登录。所有 POST、PUT、DELETE 请求均需要 CSRF，包括注册、登录和退出。

| 方法 | 路径 | 请求与结果 |
|---|---|---|
| GET | `/api/auth/csrf` | 返回 `token`、`header_name`，与当前会话绑定 |
| POST | `/api/auth/register` | `username,email,password`；201，自动登录 |
| POST | `/api/auth/login` | `identifier,password`；200，用户名或邮箱登录 |
| GET | `/api/auth/me` | 当前账号，不返回密码哈希 |
| POST | `/api/auth/logout` | 204，清除会话 |
| GET | `/api/library/collections` | `query,page,size`；返回 `collections,total,page,size` |
| POST | `/api/library/collections` | `name,description?`；201，收藏夹概要 |
| GET | `/api/library/collections/{id}` | 本人收藏夹详情，包含 `papers,overall_note` |
| PUT | `/api/library/collections/{id}` | `name,description?`；更新名称与描述 |
| DELETE | `/api/library/collections/{id}` | 204，删除本人收藏夹及其关联 |
| PUT | `/api/library/collections/{id}/note` | `content`；更新收藏夹笔记 |
| POST | `/api/library/collections/{id}/papers` | 论文元数据；201，论文与本人笔记 |
| DELETE | `/api/library/collections/{id}/papers/{paperRecordId}` | 204，使用返回的内部数字 `id` |
| PUT | `/api/library/collections/{id}/paper-note` | `source,paper_id,content`；论文必须已在本人收藏夹中 |

列表页码从 0 开始，`size` 为 1～100；`query` 匹配本人收藏夹名称和描述。详情中的 `mind_maps`、`research_run_ids` 暂为空列表，任务历史通过 `/api/research/tasks` 查询；暂未提供思维导图接口。

`paper_id` 是来源中的外部标识，`id` 是 Java 数据库内部数字标识，删除关联使用后者。论文按 `source + paper_id` 全局去重；再次添加不覆盖已有元数据，也不清空本人原有笔记。不同用户的收藏关系和笔记独立。

用户名和邮箱会去除首尾空白并进行大小写标准化来检查唯一性。用户名为 3～64 个字符，可使用字母、数字、下划线、点和连字符；注册密码至少 8 个字符，并且 UTF-8 编码不得超过 72 字节，使用 BCrypt 保存。不要在日志、提交记录或截图里记录真实密码与凭证。

| 状态码 | 含义 |
|---|---|
| 400 | 字段、页码、URL 或密码长度无效 |
| 401 | 未登录或登录凭证错误 |
| 403 | 缺少或无效的 CSRF token；认证后应重新获取 |
| 404 | 资源不存在，或不属于当前用户 |
| 409 | 标准化后的账号/同用户收藏夹名称重复，或数据库写入冲突 |

论文 URL 仅接受 HTTP(S)。当前仅校验输入，不访问 URL，不代表论文真实存在或内容已经核验。

## Java 调用 Python Agent

开两个 PowerShell 窗口。两个窗口设置同一个至少 32 字符的服务密钥；以下字符串只用于本机学习，请自行替换。它不是模型 API Key。

窗口一启动 Python 执行端（需已安装项目的 `web` 依赖）：

```powershell
Set-Location D:\20476\Pictures\agent
$env:PAPERFLOW_SERVICE_TOKEN = 'local-study-token-change-me-at-least-32-chars'
.\.venv\Scripts\python.exe -B -m paper_agent.interfaces.worker --host 127.0.0.1 --port 8001
```

窗口二启动 Java（如果原 Java 已在运行，先停止再带上配置启动）：

```powershell
Set-Location D:\20476\Pictures\agent\java-backend
$env:PAPERFLOW_SERVICE_TOKEN = 'local-study-token-change-me-at-least-32-chars'
$env:PAPERFLOW_WORKER_URL = 'http://127.0.0.1:8001'
.\run-local.cmd
```

使用前面的请求辅助函数注册或登录，并刷新 CSRF。保持 `$sessionA`、`$headersA` 和 `$base` 可用，然后提交一次不需要模型 Key 的离线研究：

```powershell
$researchInput = @{
    idempotency_key = [Guid]::NewGuid().ToString()
    topic = 'Agent 工具调用与 RAG'
    mode = 'demo'
    limit = 3
    rag = 'abstract'
}
$task = Send-PaperflowJson Post '/api/research/tasks' $researchInput $sessionA $headersA
do {
    Start-Sleep -Seconds 1
    $task = (Invoke-RestMethod "$base/api/research/tasks/$($task.task_id)" -WebSession $sessionA).data
    $task.status
} while ($task.status -in @('queued', 'running'))
$task.report
$task.events
```

`demo` 使用离线论文和演示研究团队，仍经过真实工作流、RAG、HTTP 与数据库；结果用于学习，不代表真实模型效果。`mode='live'` 才调用真实模型，需要在 **Python 窗口**配置所选提供商的模型凭证，未配置时任务失败，不会回退 demo。

| 方法 | Java 路径 | 说明 |
|---|---|---|
| POST | `/api/research/tasks` | 返回 202；创建或重放同一用户的幂等任务 |
| GET | `/api/research/tasks` | `page,size` 分页本人的任务概要 |
| GET | `/api/research/tasks/{task_id}` | 本人任务、阶段事件和最终结构化报告 |

提交必须有 `idempotency_key`（UUID）、`topic`（1～500 字符）、`mode`（demo/live）。`limit` 默认 3、范围 1～20；`rag` 为 none/abstract，默认 abstract；`provider` 为 qwen/openai，默认 qwen；`model` 可选，最多 128 字符。只有同一规范化输入才能重用同一个幂等键；换参数必须换键，否则 409。相同输入并发重试仍返回同一任务。

要研究已收藏的论文，加 `collection_id` 和可选的 `paper_ids=@(内部数字ID)`。不提供 `paper_ids` 时选择该收藏夹全部论文，必须为 1～20 篇。Java 检查归属并从数据库生成快照；浏览器不直接提供论文元数据或用户 ID。后续移除收藏不会改写任务快照和报告。

状态依次为 queued、running、completed，失败为 failed，中断为 interrupted。报告仅在 completed 时提供；部分论文分析失败记录在 `report.analysis_failures`。`sync_error` 表示暂时无法同步，不等于研究已经失败。超出默认 1800 秒同步期限会中断本地同步，但远端可能仍在执行，应检查后再决定是否新建任务。

Java 使用 H2 文件（或 MySQL）保存任务历史；Python 默认使用 `outputs/worker/tasks.sqlite3` 保存独立执行账本。Python 进程重启把遗留 queued/running 标为 interrupted，支持历史查询，不会自动续跑。首版使用一个 Java 实例和一个 Python 执行进程；Python 默认最多同时执行 2 个任务、等待 16 个任务。不要使用多 worker 启动同一账本。

| 环境变量 | 设置位置 | 默认或要求 |
|---|---|---|
| `PAPERFLOW_SERVICE_TOKEN` | 两个服务 | 同一个至少 32 字符的内部服务密钥 |
| `PAPERFLOW_WORKER_URL` | Java | 未设置时业务可启动，但新研究提交返回 503 |
| `PAPERFLOW_WORKER_DB` | Python | `outputs/worker/tasks.sqlite3` |
| `PAPERFLOW_WORKER_REQUEST_TIMEOUT` | Java | 单次内部 HTTP 请求总超时，默认 5 秒 |
| `PAPERFLOW_TASK_TIMEOUT` | Java | 总同步期限，默认 1800 秒 |

Python 内部路径是 `/internal/v1/tasks/{task_id}`，只接受服务 Bearer 凭证；它不接收 Java 的浏览器登录 Cookie。旧网页和个人模型设置尚未迁移到该链路。

打包后验证整个双服务链路：

```powershell
..\.venv\Scripts\python.exe -B scripts\bridge_smoke.py
```

脚本自行启动和停止临时双服务、使用临时数据库，无需手动启动上述窗口。

## MySQL 与 Redis 配置

先自行准备一个独立的 MySQL 数据库及 Redis。默认本地模式不需要这些服务。不要将 Java 指向原 Python 资料库来尝试自动迁移。

```powershell
Set-Location D:\20476\Pictures\agent\java-backend
$env:PAPERFLOW_DB_URL = 'jdbc:mysql://127.0.0.1:3306/paperflow_business?useUnicode=true&characterEncoding=UTF-8&serverTimezone=UTC'
$env:PAPERFLOW_DB_USERNAME = '自己的数据库用户名'
$env:PAPERFLOW_DB_PASSWORD = '自己的数据库密码'
$env:PAPERFLOW_REDIS_HOST = '127.0.0.1'
$env:PAPERFLOW_REDIS_PORT = '6379'
$env:PAPERFLOW_REDIS_PASSWORD = ''
$env:PAPERFLOW_JAVA_HOME = 'C:\Users\20476\.jdks\openjdk-25'
$env:JAVA_HOME = $env:PAPERFLOW_JAVA_HOME
.\mvnw.cmd -B -ntp spring-boot:run '-Dspring-boot.run.profiles=mysql'
```

这里的 `JAVA_HOME` 只影响当前 PowerShell 会话。`run-local.cmd` 会显式选择本地模式，启动 MySQL 模式应使用上述 Maven 命令。通过环境变量提供凭证，不写入配置文件或提交记录。

MySQL 模式使用 Redis 保存会话，命名空间为 `paperflow:java:session`，会话超时为 7 天。Cookie 名为 `paperflow_java_session`，设置 HttpOnly、SameSite=Lax；HTTPS 部署时设置 `PAPERFLOW_COOKIE_SECURE=true`。HTTP 本地演练保持默认 false。

Flyway 创建版本化的 `pf_users`、`pf_collections`、`pf_papers`、`pf_collection_papers` 和 `pf_research_tasks` 表，V3 为收藏关系增加个人元数据字段；MyBatis Mapper 使用显式 SQL 读写，ServiceImpl 使用事务协调多个写操作。当前已移除 JPA/Hibernate，不会由 ORM 自动改表。该方案不覆盖 Python 旧表，不会把旧账号或会话自动变为 Java 账号。

## 测试与打包

```powershell
Set-Location D:\20476\Pictures\agent\java-backend
.\test.cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 -Action Package
```

测试使用独立的 H2 内存数据库，覆盖账号、CSRF、会话轮换、两用户隔离、分页、去重、笔记和事务回滚，不需要外部 MySQL、Redis 或模型服务。`Package` 同时运行测试并生成 `target/paperflow-business-0.1.0.jar`。

打包后还可以运行真实 HTTP 验证脚本（在 `java-backend` 目录）：

```powershell
..\.venv\Scripts\python.exe -B scripts\smoke.py
```

脚本在临时 H2 文件和随机本地端口启动打包后的服务，验证双用户权限、会话、笔记，以及重启后重新登录读取资料，结束时清理临时数据库和自身启动的服务。需要项目 Python 虚拟环境与 JDK 21～25，不需要先手动启动服务。

2026-10-18 最终验证：26 项 Java 测试通过并成功打包；64 项 Python 测试通过；双服务联调通过 62 次 HTTP 检查、完成 3 个离线研究任务，Java 和 Python 各重启一次后历史仍可读取；原资料接口的 32 次 HTTP 检查及一次 Java 重启也通过。HTTP 次数含轮询，不代表独立用例数量。所有本地验证使用 H2/SQLite，没有调用真实模型或执行真实 MySQL/Redis 联调。

测试环境与 MySQL/Redis 环境不同。H2 测试不能替代真实 MySQL 方言、Redis 会话和外部网络联调，验证范围以实际执行结果为准。

学习路径见 [第二阶段学习说明](../docs/phase2-learning.md) 和 [第三阶段学习说明](../docs/phase3-learning.md)。
