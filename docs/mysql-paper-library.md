# MySQL 论文资料库学习手册

## 1. MySQL 在本项目中负责什么

MySQL 保存可长期管理、筛选和关联的研究资产：

- `papers`：论文元数据、摘要和原文链接；
- `authors`、`paper_authors`：作者去重与署名顺序；
- `paper_categories`：arXiv 等来源分类；
- `research_runs`、`research_run_papers`：一次研究任务及其论文集合；
- `paper_analyses`：同一论文在不同研究任务中的分析历史；
- `analysis_failures`：失败阶段、错误类型和重试次数；
- `collections`、`collection_papers`：类似 Zotero 的收藏夹；
- `tags`、`paper_tags`：论文标签。

PDF 文件仍然保存为文件或对象存储，向量继续进入向量索引。不要把关系数据库、文件存储、
向量数据库和 LangGraph checkpoint 混成一个概念。

## 2. 为什么关键字段与 JSON 同时保存

标题、来源、论文 ID、研究问题等常用字段单独建列，方便筛选、唯一约束和关联；完整
`PaperAnalysis` 和 `ResearchReport` 使用 JSON 保存，模型增加字段时不需要立即拆改所有表。

这是“关系模型保证核心一致性，JSON 保留 Agent 输出灵活性”的折中。需要频繁筛选的 JSON
字段，后续应迁移为普通列或 MySQL generated column，不要依赖扫描全部 JSON。

## 3. 先用 SQLite 学习

不设置任何数据库变量时，Web 版会自动创建：

```text
outputs/paper_library.db
```

启动：

```powershell
python -m pip install -e ".[dev,web]"
paper-agent-web
```

跑完一次任务后访问：

```text
GET /api/library/papers
GET /api/library/papers?query=retrieval
GET /api/library/collections
```

## 4. 切换到 MySQL

开发环境先建立独立数据库和账号，不要让应用使用 root：

```sql
CREATE DATABASE paper_agent
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER 'paper_agent'@'localhost' IDENTIFIED BY '请替换为强密码';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
ON paper_agent.* TO 'paper_agent'@'localhost';
```

PowerShell：

```powershell
python -m pip install -e ".[dev,web,mysql]"

$env:PAPER_AGENT_DATABASE_URL = `
  "mysql+pymysql://paper_agent:你的密码@127.0.0.1:3306/paper_agent?charset=utf8mb4"

paper-agent-web
```

应用启动时 SQLAlchemy 会创建当前表结构。生产项目应使用 Alembic 管理迁移；不应依赖
`create_all()` 修改已经存在的表。

## 5. 自动入库数据流

```text
LangGraph render 完成
  → ResearchReport
  → PaperLibrary.save_report()
  → 事务内 upsert 论文、作者、分类
  → 写入研究批次与分析历史
  → WebSocket 推送 persist 事件
  → 再保存 Markdown / JSON / HTML
```

整个 `save_report()` 使用一个事务。如果写入中途失败，本次入库会回滚，不会留下半篇论文或
只有分析没有论文的孤立记录。Web 服务使用 `asyncio.to_thread()` 执行同步 SQLAlchemy 操作，
避免数据库 I/O 阻塞 WebSocket 事件循环。

## 6. Zotero 式操作接口

创建收藏夹：

```http
POST /api/library/collections
Content-Type: application/json

{"name": "必读论文", "description": "准备面试时复习"}
```

加入论文：

```http
POST /api/library/collections/1/papers
Content-Type: application/json

{"source": "demo", "paper_id": "demo-001"}
```

增加标签：

```http
POST /api/library/papers/demo/demo-001/tags
Content-Type: application/json

{"tag": "RAG"}
```

## 7. 当前边界

- 当前是资料库后端，不是 Zotero 的完整引用管理替代品；
- 尚未实现 BibTeX/RIS 导入导出、附件同步、批注和引用格式；
- 模糊搜索使用可移植的 `LIKE`，数据量大后应增加 MySQL `FULLTEXT` 或搜索引擎；
- 没有 Alembic schema migration；
- MySQL 并发写入需要进一步处理唯一键竞争和连接池容量；
- 数据库保存的是论文资产，不等于 LangGraph 的 checkpoint。

## 8. 学习问题

1. 为什么 `source + external_id` 是联合唯一键，而不是只用标题？
2. 为什么作者需要中间表和 `position`？
3. 为什么分析属于一次 `research_run`，不能直接覆盖在论文表上？
4. 为什么收藏夹与论文是多对多关系？
5. 数据库事务失败时，为什么必须整体回滚？
