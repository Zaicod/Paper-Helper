# Redis：论文搜索缓存与按用户限流

Redis 增加在 Java 业务服务中。MySQL/H2 保存账号、收藏、任务和报告，ChromaDB 保存论文向量，Redis 保存可过期的公共搜索结果及限流计数。原有 mysql profile 的 Redis Session 配置仍独立保留。

## 启用

需要已运行的 Docker Desktop。在项目根目录执行：

```powershell
docker compose -f compose.redis.yml up -d
$env:PAPERFLOW_REDIS_ENABLED = 'true'
cd java-backend
.\run-local.cmd
```

Java 已经启动时，先在 IDEA 停止旧实例，再启动新实例，避免重复占用 H2 文件。IDEA 可在运行配置的环境变量中填写 `PAPERFLOW_REDIS_ENABLED=true`；也可在 `application-local.yml` 添加 `paperflow.redis.enabled: true`。环境变量需对实际启动 Java 的进程生效，在其他终端设置不会影响已启动的 IDEA。Vue 与 Python 不需要设置 Redis。

默认 Redis 只监听本机 6379，持久化到 Docker 命名卷。若该端口已有 Redis，可直接使用现有服务；也可以设置 PAPERFLOW_REDIS_PORT 后再启动 Compose 和 Java。停止本项目容器用 `docker compose -f compose.redis.yml stop`，不需要删除数据卷。

本地模式无需切换到 MySQL。未启用时不发起缓存和限流请求；启用后 Redis 连接失败时跳过缓存/限流，业务仍走原链路。mysql profile 的登录会话本来依赖 Redis，会话故障不属于此降级范围。

## 请求流程

搜索：认证用户 → 按用户检查搜索频率 → Service 验证并规范化参数 → 查询 Redis → 命中返回；未命中时调用 Python 获取真实论文、验证返回结果、写入 Redis。

创建任务或重试：数据库检查用户归属和幂等请求 → 验证参数、配置及所选资料 → 检查新任务频率 → 持久化任务。同一幂等请求重复提交直接返回原记录，不重复消耗限流额度。不同幂等标识表示新的请求，仍计数。

| 内容 | 默认值 |
| --- | --- |
| 正常搜索结果 | 缓存 600 秒 |
| 空搜索结果 | 缓存 30 秒 |
| 含来源故障警告的结果 | 缓存 60 秒 |
| 搜索 | 每账号 60 秒最多 30 次，缓存命中也计数 |
| 创建/重试研究任务 | 每账号 60 秒共用 5 次 |

Crossref 的 broad_search 是能力提示，不算来源故障。异常响应不缓存。搜索缓存键包含完整请求维度（关键词、精准/模糊模式、来源、排序、页码、每页条数），使用 SHA-256 避免键直接包含搜索词。缓存内容只包含公共论文元数据，不存个人笔记、API Key 或账号资料。

限流采用 Lua 原子执行 INCR 和 PEXPIRE，窗口从第一次请求开始；超限返回 HTTP 429 和中文提示，等待窗口过期后重试。该计数不是模型费用结算：后续数据库写入失败可能消耗一次额度；Redis 故障降级期间不保证限流。

## 配置项

| 环境变量 | 默认值 |
| --- | --- |
| PAPERFLOW_REDIS_ENABLED | false |
| PAPERFLOW_REDIS_HOST | 127.0.0.1 |
| PAPERFLOW_REDIS_PORT | 6379 |
| PAPERFLOW_REDIS_PASSWORD | 空 |
| PAPERFLOW_REDIS_SEARCH_TTL | 600 |
| PAPERFLOW_REDIS_EMPTY_TTL | 30 |
| PAPERFLOW_REDIS_DEGRADED_TTL | 60 |
| PAPERFLOW_REDIS_SEARCH_LIMIT | 30 |
| PAPERFLOW_REDIS_GENERATION_LIMIT | 5 |
| PAPERFLOW_REDIS_WINDOW_SECONDS | 60 |

local 配置的连接与命令超时为 300ms，mysql profile 保留原有 3 秒会话配置。Redis 使用 `paperflow:search:v1:` 和 `paperflow:rate:v1:` 前缀。不同部署应使用各自 Redis 实例或数据库；不要与不受信任的客户端共享 Redis 写权限。

## 代码入口

- `PaperSearchCacheService` / `RedisPaperSearchCacheService`：缓存接口、键生成、JSON 读写、过期时间和故障降级。
- `PaperSearchServiceImpl`：在请求验证完成后读取缓存，只缓存验证过的搜索结果。
- `UserRateLimitService` / `RedisUserRateLimitService`：按用户限流接口与 Lua 实现。
- `PaperSearchController`：从登录身份取用户 ID，执行搜索限流。
- `ResearchTaskServiceImpl`：在创建新记录之前执行生成限流，保留原有幂等性。

限流实现参考 [Redis INCR 官方文档](https://redis.io/docs/latest/commands/incr/) 的 Rate limiter 模式。缓存能减少重复搜索等待，首次搜索和过期后的搜索仍依赖外部来源。

## 测试

`RedisFeaturesTest` 使用测试替身验证缓存键、过期时间、坏缓存、禁用开关和连接故障。`RedisWorkflowApiTest` 使用真实 Redis 与受控 Python HTTP 接口，设置 `PAPERFLOW_TEST_REDIS_PORT` 后运行；未设置时跳过，日常测试不要求 Redis。

```powershell
# java-backend 目录，使用专用测试 Redis，避免和日常实例混用
$env:PAPERFLOW_TEST_REDIS_PORT = '专用测试Redis端口'
.\mvnw.cmd '-Dtest=RedisFeaturesTest,RedisWorkflowApiTest' test
```

集成测试不执行 FLUSHDB，只访问测试账号或随机键。不会调用真实大模型。

2026-10-20 验证：完整 Java 测试 82 项通过（无跳过），使用专用 Docker Redis 7.4.11 和受控 HTTP 论文源。验证了缓存复用、600 秒过期时间、空/降级结果的 TTL、失败不缓存、坏缓存删除重查、按账号限流、并发原子计数、窗口过期恢复、创建/重试幂等性及原功能回归。Redis 故障降级另由异常替身测试覆盖。Compose 配置检查通过；未重启日常 Java、Python 服务。
