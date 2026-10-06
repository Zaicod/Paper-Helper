# 登录注册与 Redis 会话学习手册

## 1. 模块职责

认证系统被拆成三层：

```text
React 登录/注册表单
  → FastAPI /api/auth/*
  → SQLAlchemy users 表：账号、邮箱、密码哈希
  → Redis：随机 Session、用户 ID、TTL
  → HttpOnly Cookie：只保存随机 Session token
```

数据库适合长期保存用户；Redis 适合高频读取、自动过期和立即注销的短期会话。Web 服务本身
不保存登录状态，所以进程重启或部署多个 Web 实例时，用户仍能通过 Redis 恢复会话。

## 2. 为什么不用 localStorage 和明文密码

- localStorage 中的令牌能被页面 JavaScript 读取，发生 XSS 时更容易被窃取；HttpOnly Cookie
  不允许 JavaScript 读取。
- 密码不加密保存，也不能解密保存。本项目使用 scrypt、每个密码独立随机盐和常量时间比较。
- Redis 键使用 Session token 的 SHA-256 摘要，Redis 数据泄露时不会直接暴露浏览器令牌。
- `SameSite=Lax` 限制常见跨站请求；生产 HTTPS 环境还应设置
  `PAPER_AGENT_COOKIE_SECURE=true`。

## 3. Session 生命周期

1. 注册或登录成功后生成 256 位以上随机 token。
2. Redis 写入 `paperflow:session:{token摘要}`，值为用户 ID，并设置 TTL。
3. 浏览器收到 `paperflow_session` HttpOnly Cookie。
4. 每次访问受保护 API，服务查询 Redis，并刷新 TTL，形成滑动过期。
5. 注销时同时删除 Redis 键和 Cookie。
6. Redis 键过期后，旧 Cookie 即使仍在浏览器中也不能通过认证。

## 4. 本地运行

```powershell
python -m pip install -e ".[dev,web]"
docker compose -f docker-compose.redis.yml up -d
docker compose -f docker-compose.redis.yml ps
paper-agent-web
```

健康检查：

```powershell
docker exec paperflow-redis redis-cli ping
```

返回 `PONG` 表示 Redis 可用。停止服务但保留会话数据：

```powershell
docker compose -f docker-compose.redis.yml stop
```

Compose 使用 AOF 和命名卷，因此普通容器重启不会丢失会话。不要在生产环境直接暴露 6379
端口；应使用私有网络、密码或 ACL，并按部署环境启用 TLS。

## 5. API

- `POST /api/auth/register`：创建用户并登录。
- `POST /api/auth/login`：支持用户名或邮箱登录。
- `GET /api/auth/me`：恢复当前登录用户，同时刷新 TTL。
- `POST /api/auth/logout`：删除服务端会话和浏览器 Cookie。

研究任务、论文检索、PDF 下载与资料库接口默认都需要登录，WebSocket 连接也会检查同一个
Cookie。静态登录页面和 `/api/auth/*` 保持公开。

## 6. 自动化测试

`tests/test_auth.py` 覆盖：

- 同一密码生成不同带盐哈希；
- 正确和错误密码验证；
- Redis key 不包含原始 token；
- Session 读取时刷新 TTL；
- 未登录访问返回 401；
- 注册、登录、重复注册和注销；
- 更换 Web 应用实例后恢复原有会话。

## 7. 当前边界

- 当前账号进入同一个共享研究工作空间，尚未按用户隔离论文与 Collection；如果产品定位为
  多租户个人资料库，需要给论文、分类和任务增加 owner/workspace 关系。
- 尚未实现邮箱验证、忘记密码、登录失败限流与管理员强制下线。
- SQLite `create_all` 适合学习环境；正式部署需要 Alembic 数据库迁移。
