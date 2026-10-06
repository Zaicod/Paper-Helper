# 收藏夹研究工作区学习手册

## 1. 这次升级解决了什么问题

旧版本把搜索分类、收藏夹和研究任务看成三个相互独立的概念。新版本把收藏夹作为研究聚合根：

```text
收藏夹（研究分类）
  ├─ 收藏论文 + added_at
  ├─ 每篇论文笔记
  ├─ 收藏夹整体归纳
  ├─ 多次研究任务
  └─ 多张思维导图
```

这不是只改页面名称，而是把数据关系落到了数据库和 API 中。

## 2. 完整数据流

### 收藏夹研究任务

1. React 从 `GET /api/library/collections/{id}` 读取收藏夹论文。
2. 用户多选论文并填写本次研究方向。
3. 前端向 `POST /api/research` 发送 `collection_id` 与 `selected_papers`。
4. `ResearchTaskManager` 从资料库加载所选 `Paper`，注入 LangGraph state；Web 启动时若从 `.env` 读到 `DASHSCOPE_API_KEY`，同时注入 Qwen `AgentResearchTeam`。
5. LangGraph 的 search 节点发现 state 已有论文，就不再调用外部搜索；分析、总结和渲染节点原样复用。
6. 报告保存后，`collection_research_runs` 记录收藏夹与 run_id 的关系。

这里体现了工作流设计的重要原则：输入来源可以替换，下游数据合同保持稳定。

### 笔记

- `paper_notes` 使用 `(collection_id, paper_id)` 复合主键。同一篇论文放在不同收藏夹中，可以有不同语境的笔记。
- `collection_notes` 以 `collection_id` 为主键，保存整个方向的共同结论、争议和想法。
- 笔记不直接塞进 `papers` 表，因为论文元数据是共享事实，笔记是特定收藏夹中的主观知识。

### 思维导图

1. 用户设置论文加入日期范围、勾选论文并输入相关方向。
2. 后端先在数据库中做日期过滤与选择交集，模型不会看到范围外的论文。
3. Agent 接收论文元数据、单篇笔记和整体笔记。
4. Agent 输出 `MindMapDraft`，其中包含节点、边和关联 paper_id。
5. `mind_maps` 保存结构化 JSON，`mind_map_papers` 保存可查询的论文关系。

## 3. 为什么思维导图使用结构化输出

如果模型直接返回 Mermaid 或 HTML，内容和表现层会绑死，难以校验节点引用，也不方便以后换成 React Flow、D3 或导出图片。现在 Agent 只输出：

- `MindMapNode`：节点 id、标题、摘要、层级、paper_ids；
- `MindMapEdge`：起点、终点和关系；
- `MindMapDraft`：标题、概览、节点集合和边集合。

React 当前用层级卡片渲染。以后替换可视化框架时，不需要修改 Agent 或数据库合同。

## 4. Fixture Agent 与 Qwen Agent

`build_mind_map_agent()` 检查 `DASHSCOPE_API_KEY`：

- 有 Key：通过 Agents SDK 调用 Qwen，并由 `output_type=MindMapDraft` 约束结果；
- 无 Key：使用 `FixtureMindMapAgent`，按论文分类生成确定性图谱。

Fixture 不是伪造线上能力，而是开发替身。它使自动化测试不联网、不消耗额度，并让失败能稳定复现。

## 5. 建议按这个顺序学习

1. 在 `models.py` 找到 `MindMapDraft`，先理解数据合同。
2. 阅读 `storage.py` 的关系表，画出主键和外键。
3. 阅读 `get_collection_papers()`，解释日期过滤为什么在模型调用之前完成。
4. 阅读 `langgraph_workflow.py` 的 search 节点，解释注入已有论文如何复用工作流。
5. 阅读 `mindmap.py`，对比 Fixture Agent 和 Qwen Agent 的共同接口。
6. 阅读 `web_app.py` 的笔记和导图 API，观察 I/O 与业务层的边界。
7. 阅读 `CollectionsPage.tsx`，找出服务端状态、编辑中状态和提交中状态。
8. 运行 `pytest`，再临时改坏一个字段，观察哪一层测试会失败。

## 6. 可以继续做的练习

- 为笔记增加版本历史，而不是覆盖更新。
- 校验 Agent 输出中的每条 edge 都引用存在的 node id。
- 把 `mind_map_papers` 用于从论文反查相关导图。
- 将层级卡片替换为 React Flow，但不修改 `MindMapDraft`。
- 给收藏夹研究任务增加 live/fixture 模式选择，接入真实分析 Agent。
- 增加用户所有权字段，避免多个登录用户共享同一收藏夹。
