# LangGraph 第一阶段：Fixture 驱动的最小工作流

这一阶段只学习四个概念：`State`、`Node`、`Edge`、`Graph`。它完全离线，
不会访问论文网站，也不会消耗 Qwen 额度。

## 1. 先运行，再读代码

```powershell
python -m pip install -e ".[dev]"
paper-agent run --engine langgraph --mode demo --topic "RAG" --limit 2
pytest tests/test_langgraph_workflow.py -v
```

运行路径是：

```text
START → search → analyze → synthesize → ideate → render → END
```

请先打开 `src/paper_agent/langgraph_workflow.py`，按下面顺序阅读：

1. `ResearchGraphState`：所有节点共享的数据合同。
2. `search_papers`：读取输入，返回 `papers` 状态增量。
3. `analyze_papers`：读取 `papers`，顺序产生 `analyses`。
4. `synthesize_field`：读取全部分析，产生跨论文总结。
5. `ideate`：读取跨论文总结，产生候选研究构思。
6. `render_report`：组装同一个 `ResearchReport` 并渲染 Markdown。
7. `StateGraph` 部分：注册节点并声明固定边。
8. `compile()`：把图定义编译成可以 `ainvoke()` 的应用。

## 2. State 不是一堆全局变量

`ResearchGraphState` 是节点之间的数据合同。第一次调用只提供：

```python
{"topic": "RAG", "limit": 2, "category": None}
```

随后各节点只返回自己新增或修改的字段：

```text
search      → {papers}
analyze     → {analyses}
synthesize  → {synthesis}
ideate      → {idea_portfolio}
render      → {report, rendered_markdown}
```

节点不需要复制完整 State。LangGraph 会把返回的增量合并到当前 State。
`total=False` 表示后面的字段在初始状态中可以不存在；它不是说这些字段永远可有可无。

## 3. Node 是普通函数

节点不是 Agent。节点只是接收 State、完成单一职责并返回状态增量的函数。

- `search` 调用 Fixture 工具，行为确定。
- `analyze` 当前调用 `DemoResearchTeam`，不访问模型。
- `synthesize` 当前同样是可复现的假实现。
- `ideate` 根据研究空白生成可复现的演示构思。
- `render` 只负责组装领域对象和表现层文本。

第二阶段才会把单个 `analyze` 节点拆成多个并行任务。现在保留普通循环，是为了先看清
状态如何沿固定边传递。

## 4. Edge 只描述执行依赖

边表达“哪个节点完成后，哪个节点才可以运行”。例如 `analyze → synthesize` 表示：
跨论文总结必须等到单篇分析全部完成。

边不负责传参数。数据统一通过 State 传递，因此节点之间不会形成大量位置参数耦合。

## 5. 为什么保留旧工作流

`workflow.py` 仍然是当前完整功能的基线，LangGraph 第一阶段通过
`--engine langgraph` 单独运行。这样可以：

- 比较普通 Python 编排与图编排；
- 避免学习中的改动破坏 live/RAG 流程；
- 后续用同一批 Fixture 和评估数据做迁移前后回归测试。

## 6. 本阶段暂时没有什么

- 没有 Qwen 或 LangChain 模型调用；
- 没有 `Send` 并行分发；
- 没有 reducer；
- 没有失败分支和重试；
- 没有 checkpoint、memory 或人工中断；

这些不是遗漏，而是后续阶段要逐项加入、测试和解释的能力。

## 7. 动手练习

不要立即看答案，依次完成：

1. 把 `limit=2` 改为 `limit=3`，观察 State 中哪些字段长度发生变化。
2. 使用 `--category cs.AI`，解释为什么最后只剩一篇论文。
3. 在 `search_papers` 返回空列表时，解释为什么应该立即失败。
4. 不看图定义，画出每个节点读取和写入的 State 字段。
5. 尝试交换 `analyze` 与 `synthesize` 的边，记录出现的错误并解释原因。

完成标准：你能不用看代码说清楚“状态存什么、五个节点各做什么、六条边为什么这样连”。
