# Vue 接入：把 Java CRUD 与 Agent 变成可操作的页面

你已经熟悉黑马 Spring Boot 三层结构，可以把一个 Vue 页面和对应 Java Controller 放在一起阅读。Vue 用于浏览器界面，与后端采用 Java 或 Python 无关；本项目保留 TypeScript 来明确接口字段。

## 从收藏夹创建开始

| 前端位置 | 对应后端 | 学什么 |
|---|---|---|
| `views/CollectionsView.vue` | `controller/LibraryController` | 表单 `v-model`、提交事件、加载与失败状态 |
| `api/index.ts` | `CollectionDTO`、`CollectionVO` | 请求路径、JSON 字段与类型 |
| `api/http.ts` | `common/Result`、安全配置 | 解包 data、Cookie、CSRF 与 HTTP 错误 |
| `stores/auth.ts` | `AuthController` | 登录状态、页面刷新后恢复身份 |
| `router/index.ts` | 已认证接口 | 前端导航守卫与后端资源权限的区别 |

例如用户填写收藏夹名称，`v-model` 更新响应式变量，表单调用 `api.collections.create(...)`，请求进入 Java Controller → Service → ServiceImpl → Mapper，返回的 `Result.data` 更新页面列表。浏览器不提交用户 ID，Java 从登录会话获取身份。

前端路由守卫负责用户体验，不能代替后端权限检查。即使直接修改页面地址或请求参数，Java 仍按资源归属决定是否返回数据。

## 再看研究任务

`ResearchNewView` 提交参数；`composables/submission.ts` 为同一次研究意图保留幂等键。网络错误可能发生在 Java 已经受理之后，因此点击重试不能随意换键。任务进入详情页后，`composables/polling.ts` 每次请求结束后再安排下一次查询；终态停止、离页清理，旧请求不能覆盖新任务页面。

`TaskDetailView` 展示服务器实际状态和阶段事件；`ReportView` 读取结构化报告，分别显示分析、综合、构思和证据审计。报告文字使用 Vue 插值，外链限制 HTTP/HTTPS，不把模型文本直接作为 HTML 执行。

这条链路是：

```text
Vue 表单 → Java 保存任务与论文快照 → Python Agent / RAG
         ← Java 同步并保存结构化结果 ← Python 执行账本
Vue 轮询读取任务与报告
```

## 建议练习

1. 创建两份账号，分别添加同名收藏夹，观察资料隔离。
2. 先不启动 Python，提交研究并观察配置错误；再按文档启动完整链路。
3. 用离线演示完成一次研究，查看阶段事件、片段 ID 和分析内容之间的关系。
4. 研究过程中离开页面再返回，理解“页面停止轮询”和“后台任务停止”是不同的事情。
5. 保存笔记后刷新、重新登录，确认哪些数据来自数据库，哪些只是页面的输入草稿。

不要先把精力放在记住全部组件 API 上。先沿一个真实请求读懂数据、状态和失败处理，再逐步学习路由、Pinia、组合式函数和 TypeScript。

启动与接口边界见 [Vue README](../frontend-vue/README.md)。Java 分层见 [黑马课程对照](java-architecture.md)，Agent 接入见 [第三阶段说明](phase3-learning.md)。

## 本次验证

2026-10-19：19 项前端行为测试通过，TypeScript 检查和生产构建通过。Playwright 使用实际 Chrome，在真实 Vue / Java / Python 链路中完成一项包含注册、资料、笔记、演示研究、报告、登录恢复和用户隔离的端到端测试。检查了 1440×1080 和 390×844 两种视口，并目视检查截图。报告内容来自现有离线研究工作流，没有模拟 HTTP 响应。

结果文件为 `.tools/vue-e2e-smoke.json`，浏览器日志为 `.tools/vue-e2e-playwright.log`，桌面和手机截图为 `.tools/vue-desktop.png`、`.tools/vue-mobile.png`。临时数据库和验收进程已清理。此次没有调用真实模型，没有新增 MySQL/Redis 或生产部署验证。
