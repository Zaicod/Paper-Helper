# Redis 搜索缓存与用户限流

用户确认：在 Java 侧接入论文搜索缓存及搜索/报告生成限流。保留当前 Controller / Service / Mapper、业务数据库与 Chroma 的职责。

- 独立开关 PAPERFLOW_REDIS_ENABLED，默认关闭，启用不要求切换 MySQL。已有 mysql profile 的 Redis Session 独立保留。
- 缓存放在 PaperSearchServiceImpl 的参数验证之后、Python 调用之前。键为版本前缀和规范化请求 JSON 的 SHA-256，包含 query、source、limit、page、sort、keywords（包含匹配模式和原顺序）。不混淆有无分页或精准与模糊匹配。
- 只缓存公开论文搜索 VO；正常 600 秒、空结果 30 秒、含来源失败警告的降级结果 60 秒。Crossref broad_search 信息提示不视为来源失败。异常不缓存。
- 单用户搜索 30 次/60 秒，创建或重试新研究任务共用 5 次/60 秒；Lua 原子 INCR/PEXPIRE 实现首请求开始的固定窗口。超限 HTTP 429 和中文提示。真实用户 ID 来自认证身份。
- 新任务限流在权限、资料、配置验证之后，入库之前；找到同一幂等请求直接返回，不重复计数。限流不是收费计量，Redis 成功计数后数据库写入失败可能消耗一次额度。
- Redis 操作失败时缓存视为未命中，限流放行；日志仅记录简短故障类型，不记录查询/模型密钥。损坏缓存忽略并删除。网络超时限制为短时间。
- 暂不加消息队列、热门词或任务状态缓存，不修改 Python 工作流。共享公开论文缓存不包含收藏笔记、API Key、账号信息。
- 单元测试验证键、过期时间、故障降级及限流；服务集成测试验证命中后不请求 Python、429、账户隔离和幂等提交。可用时用真实 Redis 验证 Lua 和 TTL。
