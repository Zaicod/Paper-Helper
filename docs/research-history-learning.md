# 研究任务分类与历史记录

研究任务页面提供三个标签：进行中（queued、running）、未完成（failed、interrupted）、历史研究（completed）。默认进入进行中。每页 10 条，按创建时间倒序排列；已完成任务保留在原任务表中，不复制到新表。

输入研究主题后按回车或点击搜索，查询当前分类的所有匹配记录；清空恢复完整列表。分类、已提交搜索词和页码保存在 URL 中，从任务详情点击返回任务或刷新页面都能恢复。任务状态变化后点击刷新列表即可查看最新分类。

## Java 三层调用

`ResearchController.list` 接收 category、keyword、page、size，交给 `ResearchTaskService.list`。Service 实现校验参数，将分类转为状态列表，对关键词进行大小写归一化和 LIKE 特殊字符转义。`ResearchTaskMapper` 用绑定参数按当前用户、状态和主题筛选，列表查询和总数查询共享过滤条件。

接口示例：`GET /api/research/tasks?category=history&keyword=Agent&page=0&size=10`。接口页码从 0 开始，页面 URL 的 page 从 1 开始。category 可选 active、unfinished、history，省略则保持原来查询所有状态的接口行为。

Vue 的 `ResearchView.vue` 以路由参数为查询依据，切换分类或搜索时重置页码。每次查询清除旧结果，并使用请求版本号忽略较早返回的结果；刷新时如果页数缩小，会回到有效页码。

## 启用与验证

重启 Java 后端，再刷新 Vue 页面。Python 服务不需要重启。

2026-10-20 验证：Java 70 项、Vue 77 项测试通过，前端生产构建通过。浏览器使用测试接口数据验证桌面和手机布局、分类、分页、搜索、详情返回及刷新恢复；后端通过 MockMvc 与 H2 验证真实 SQL 查询、用户隔离和分页。未连接实际 MySQL 验证。
