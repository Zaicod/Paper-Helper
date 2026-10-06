# MultiAgent-Search 项目分析与融合记录

## 1. 外部项目的核心结构

`MultiAgent-Search` 是一个电商场景的 DeepAgents 应用：主智能体动态选择网络搜索、MySQL
和 RAGFlow 子智能体，FastAPI 接收任务，WebSocket 推送工具与子智能体进度，SQLite 保存
对话 checkpoint，并把结果写入会话目录。

值得学习的部分：

- FastAPI 接口与 Agent 后台任务解耦；
- WebSocket 将长任务的阶段进度推给浏览器；
- 每个任务使用独立 ID 和输出目录；
- 已完成事件可以被前端展示；
- LangGraph/DeepAgents 运行在 Web 服务内部，而不是让 HTTP 路由承担业务逻辑。

## 2. 没有直接复制的部分

- 电商 Prompt、MySQL 与 RAGFlow 和论文研究领域无关；
- DeepAgents 的动态主智能体会让确定的论文处理顺序更难测试；
- 原上传接口直接使用客户端文件名，需要额外防路径穿越；
- SQL 工具允许模型提交任意查询，不适合直接进入本项目；
- 原路径函数允许会话目录外的绝对路径，隔离并不完整；
- 原项目缺少自动化测试，不能作为当前回归基线。

因此本次融合采用“复用架构思想、重新实现领域适配层”的方式，没有复制外部业务工具。
外部项目使用 MIT License；如果以后复制其实质代码，必须保留其版权与许可证声明。

## 3. 融合后的数据流

```text
浏览器表单
  → POST /api/research
  → ResearchTaskManager 创建 task_id 与后台 asyncio.Task
  → LangGraph: search → analyze → synthesize → ideate → render
  → graph.astream(stream_mode="updates")
  → WebSocket /ws/{task_id} 推送节点完成事件
  → PaperLibrary 将论文、分析与研究批次去重写入 SQLite/MySQL
  → outputs/web/{task_id}/ 保存 Markdown、JSON、HTML
  → GET /api/tasks/{task_id} 查询状态与下载链接
```

## 4. 为什么使用 TaskManager

HTTP 请求必须快速返回，研究任务在后台执行。TaskManager 同时解决：

- 保存后台任务引用，避免“启动后无人管理”；
- 保存任务状态和错误；
- 保存历史事件，WebSocket 晚连接也不会错过前面节点；
- 为每个任务维护独立订阅队列；
- 把输出限制在 `outputs/web/{task_id}`；
- 允许测试直接等待任务完成，而不依赖真实服务器。

## 5. 运行

```powershell
python -m pip install -e ".[dev,web]"
paper-agent-web --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`。本阶段仍然使用 Fixture，不联网、不调用 Qwen。

运行测试：

```powershell
pytest tests/test_web_app.py -v
pytest
```

## 6. 当前边界与下一步

当前 Web 服务只连接第一阶段 Fixture LangGraph。下一步依次加入：

1. `Send + reducer` 单篇论文并行分析；
2. LangChain + Qwen 结构化输出；
3. RAG 检索进度与单篇失败事件；
4. SQLite checkpoint 和任务恢复；
5. `interrupt()` 人工审核；
6. 限流、认证、任务过期清理和生产部署。
