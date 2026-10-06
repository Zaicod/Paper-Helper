# React 前端学习手册

## 1. 为什么选择 React + TypeScript + Vite

这个界面不是独立的“漂亮外壳”，而是 Agent 工作流的可观察层：它既要管理表单和任务状态，
又要接收 WebSocket 事件并把 LangGraph 节点状态映射到界面。React 适合把这些状态拆成可维护
的组件；TypeScript 让前端数据结构与 FastAPI 返回值形成明确合同；Vite 提供快速开发服务器和
可由 FastAPI 直接托管的生产构建。

Lucide React 只负责图标，不承担组件状态。界面样式由项目自己的 CSS 控制，便于学习布局、
响应式设计和设计 token，而不会被大型 UI 组件库隐藏关键原理。

## 2. 数据流

```text
研究表单
  → POST /api/research
  → 获得 task_id
  → WebSocket /ws/{task_id}
  → React 合并节点事件和任务状态
  → GET /api/tasks/{task_id} 校准最终状态
  → 展示下载链接并刷新 /api/library/papers
```

前端不执行检索、分析或报告生成。它只负责收集输入、调用后端、展示状态和结果。这让同一套
后端以后可以被 CLI、React 页面或其他客户端复用。

关键词下载模块是另一条独立数据流：

```text
关键词 → GET /api/search/papers → arXiv/OpenAlex
      → 用户选择 Collection → POST /api/library/import
      → 校验并下载 PDF → paper_downloads + collection_papers
      → GET /api/library/downloads/{id}
```

导入接口只接受已经由服务端搜索并缓存的 `source + paper_id`，不接受客户端提供任意下载
URL。这是为了避免 SSRF：攻击者不能借论文下载功能访问本机或内网地址。

## 3. 关键文件

- `frontend/src/App.tsx`：登录恢复、共享状态、WebSocket 生命周期和路由装配。
- `frontend/src/pages/ResearchPage.tsx`：创建研究任务。
- `frontend/src/pages/LibraryPage.tsx`：关键词检索、PDF 下载和论文库。
- `frontend/src/pages/TasksPage.tsx`：LangGraph 节点与实时事件。
- `frontend/src/pages/CollectionsPage.tsx`：收藏夹知识工作区、两层笔记和思维导图。
- `frontend/src/pages/SettingsPage.tsx`：个人 Provider、密钥和 Agent 模型路由。
- `frontend/src/components/DashboardLayout.tsx`：左侧导航和公共页面框架。
- `frontend/src/api.ts`：所有 HTTP/WebSocket 调用，隔离传输细节。
- `frontend/src/types.ts`：前后端数据合同。
- `frontend/src/styles.css`：颜色、间距、响应式断点与组件视觉。
- `frontend/vite.config.ts`：开发代理和生产输出目录。
- `src/paper_agent/web_app.py`：FastAPI API、静态资源托管和后台任务。

## 4. 开发与构建

先启动后端：

```powershell
paper-agent-web --host 127.0.0.1 --port 8000
```

另开终端启动前端热更新：

```powershell
cd frontend
npm install
npm run dev
```

修改完成后生成生产资源：

```powershell
npm run build
```

Vite 会把结果写入 `src/paper_agent/web_static/`。因此部署时只需要启动 FastAPI，不需要再运行
Node 服务。不要手工编辑 `web_static/assets` 内带 hash 的文件；它们应始终由 Vite 生成。

## 5. 建议学习顺序

1. 从 `types.ts` 开始，找到 `ResearchTask` 和 `TaskEvent`，理解前端依赖哪些后端字段。
2. 阅读 `api.ts`，分别解释 REST 为什么适合创建/查询任务，WebSocket 为什么适合推送进度。
3. 在 `App.tsx` 中追踪一次点击：提交表单、创建任务、跳转 `/tasks`、订阅事件、更新节点。
4. 修改 `styles.css` 中的 `--brand`，观察设计 token 如何影响整个界面。
5. 给任务失败状态设计一个醒目的错误卡片，并为重连策略增加自动化测试。

## 6. 当前边界

- 当前使用 React Router：`/`、`/library`、`/tasks`、`/collections` 均可独立访问和刷新。
- 任务状态保存在当前浏览器页面中，刷新后不会自动恢复上一次任务。
- 论文检索和下载已支持 Collection 分类；标签编辑尚未接入可视化控件。
- 前端以 TypeScript 构建作为静态检查，下一阶段可加入 Vitest 和 React Testing Library。
