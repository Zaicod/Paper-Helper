# Vue 论文研究工作台

Vue 3 + TypeScript + Vue Router + Pinia + Vite，连接项目现有 Java 三层架构后端。浏览器只调用 Java；Python 负责后台 Agent 执行。

## 安装与启动

当前机器的 Node.js 24.13.0 已验证可用；工程要求 Node.js 22.18 或更高版本。首次安装：

```powershell
Set-Location D:\20476\Pictures\agent\frontend-vue
npm ci
npm run dev
```

打开 [Vue 工作台](http://127.0.0.1:5173)。本地端口固定为 5173，占用时会明确退出，可停止自己已有的进程或用 `npm run dev -- --port 其他端口`。

Java 默认运行在 `http://127.0.0.1:8080`。前端开发及预览服务器把 `/api` 代理给 Java，因此 Cookie 与 CSRF 可以按同源方式工作。要改变 Java 地址，可复制 `.env.example` 为 `.env.local`，修改 `PAPERFLOW_JAVA_URL` 后重启 Vite。该变量只供 Vite 服务器使用。

## 启动完整研究流程

需要三个窗口，两个后端使用相同的内部服务密钥。以下密钥字符串仅演示配置位置，请换成自己的至少 32 字符字符串；它不是模型 API Key，也不应写入前端代码。

窗口一，Python 执行端：

```powershell
Set-Location D:\20476\Pictures\agent
$env:PAPERFLOW_SERVICE_TOKEN = 'local-study-token-change-me-at-least-32-chars'
.\.venv\Scripts\python.exe -B -m paper_agent.interfaces.worker --host 127.0.0.1 --port 8001
```

窗口二，Java 业务后端：

```powershell
Set-Location D:\20476\Pictures\agent\java-backend
$env:PAPERFLOW_SERVICE_TOKEN = 'local-study-token-change-me-at-least-32-chars'
$env:PAPERFLOW_WORKER_URL = 'http://127.0.0.1:8001'
.\run-local.cmd
```

窗口三运行前端 `npm run dev`。Java 与 Python 的安装前提见 [Java 启动说明](../java-backend/README.md) 和 [项目说明](../README.md)。Java 默认 H2、Python 默认 SQLite，无需先安装 MySQL/Redis；离线演示无需模型凭证。

只体验账号、收藏夹和笔记时，启动 Java 与 Vue 即可。研究任务需要 Python 执行端；未配置时页面会显示 Java 返回的错误。

## 在页面中体验

1. 注册一个新工作台账号，进入“我的资料库”。旧 React/Python 账号尚未迁移。
2. 新建收藏夹，然后在“搜索论文”中检索 arXiv/OpenAlex，选择收藏夹后加入。也可手工填写论文资料。收藏夹内支持论文详情、个人元数据编辑、笔记及移除；个人编辑只影响当前收藏夹。
3. 从收藏夹发起研究，或在“研究任务”中按主题创建研究。选择“离线演示”和“摘要 RAG”先熟悉流程。
4. 查看实际阶段记录、逐篇分析、综合结论、研究构思、证据审计及失败论文。
5. 刷新页面后会从服务器恢复登录身份；Java 本地会话随 Java 重启失效，需要重新登录，资料及任务历史仍保留。

真实模型模式使用 Python 环境中的凭证，可选择 Qwen/OpenAI；页面不保存模型密钥。论文搜索不调用模型；正常启动使用真实文献源，自动模式会尝试 arXiv/OpenAlex，失败不返回演示论文。来源网络与额度配置见 [搜索学习说明](../docs/paper-search-learning.md)。个人模型设置迁移、思维导图等尚未提供新的 Vue 管理页面。

## 代码与验证

```text
src/
  api/            Java 接口、Result 解包、Cookie 与 CSRF
  stores/auth.ts  登录身份与刷新恢复
  router/         页面路由与访问守卫
  views/          登录、收藏夹、研究任务与任务详情
  components/     结构化研究报告
  composables/    幂等提交和无重叠轮询
  types.ts        与 Java DTO/VO 对应的接口类型
  style.css       工作台公共样式及响应式布局
```

```powershell
npm test
npm run build
npm run preview
```

`build` 先做 TypeScript 检查，再生成 `dist/`；`preview` 在 [本地预览](http://127.0.0.1:4173) 查看生产构建，也代理 `/api`。直接打开 `dist/index.html` 不能代替服务器运行。

实际浏览器验收从项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -B scripts\vue_smoke.py
```

脚本使用临时数据库与随机端口启动真实 Java、Python、Vite，并通过 Playwright 操作注册、收藏论文、笔记、Agent 报告、登录恢复、权限隔离和手机布局。优先使用已安装的 Chrome；没有可用浏览器时先在前端目录运行 `npx playwright install chromium`。需要先按 Java 文档构建可执行 jar。

本地预览不是生产部署。部署时使用静态站点服务器为 Vue 提供 history 路由回退，并把同源 `/api` 反向代理给 Java；不要把 Python 内部服务密钥放到前端环境变量中。

学习路线见 [Vue 接入学习说明](../docs/vue-learning.md)。参考 [Vue 官方入门](https://vuejs.org/guide/quick-start.html)、[Vite 说明](https://vite.dev/guide/)、[Pinia](https://pinia.vuejs.org/getting-started)。

搜索与论文 CRUD 的独立浏览器验收可从项目根目录运行 `.\.venv\Scripts\python.exe -B scripts\paper_search_smoke.py`。该验收在文献 API 边界使用本地受控 HTTP 测试源；正式页面仍请求真实文献站点。更新后请重启两个后端，让 Python 加载新路由、Java 加载新接口并应用 V3 迁移。
