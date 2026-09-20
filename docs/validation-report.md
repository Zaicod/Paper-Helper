# v0.2 验证记录

## 离线验证

命令：

```powershell
paper-agent run --topic "retrieval augmented generation" --mode demo `
  --limit 2 --rag abstract --embedding-provider local `
  --context-token-budget 800
```

结果：

- 两篇论文均生成可追溯 citation。
- 每篇报告包含 ContextAudit。
- Markdown、HTML、JSON 三种表现层同时生成。

## MCP 协议验证

使用 MCP Python Client 通过 stdio 启动 Server 并完成：

1. initialize；
2. tools/list；
3. 调用 `index_papers`；
4. 调用 `retrieve_evidence`；
5. 返回证据块 `protocol-1:p0:c0`。

协议测试不是直接调用 Python 方法，而是真正经过 MCP stdio transport。

## Live PDF RAG 验证

命令：

```powershell
paper-agent run --topic "retrieval augmented generation" --mode live `
  --provider qwen --source openalex --limit 1 `
  --rag pdf --embedding-provider qwen `
  --context-token-budget 3000
```

运行结果：

- 论文：`2312.10997`，*Retrieval-Augmented Generation for Large Language Models: A Survey*。
- PDF：`https://arxiv.org/pdf/2312.10997`。
- 来源模式：`pdf`，没有回退摘要。
- 选入 chunk：6。
- 因预算丢弃 chunk：6。
- 估算上下文：2828/3000 token。
- 有效引用：`p1:c2`、`p2:c1`、`p14:c0`、`p15:c0`。
- 分析、总结、构思三个 Agent 阶段均成功。

## 验证中发现并修复的问题

### Qwen Embedding 批量限制

首次 live 索引收到 HTTP 400：单次 batch 不得超过 20。修复为 `OpenAICompatibleEmbedder` 自动按 20 条分批，并增加回归测试。

### Citation 格式漂移

模型把 chunk 引用输出成包含 `chunk_id` 和 `page` 的 JSON 字符串，而数据合同要求纯 chunk_id。修复为：

- 解析可识别的 JSON 字符串；
- 只接受当前 ContextPacket 的 chunk 白名单；
- 去重；
- 过滤模型虚构的 chunk ID；
- 没有有效引用时写入 evidence note。

这两个问题说明 live 验证的价值：单元测试可以证明本地逻辑，但不能提前覆盖供应商批量限制和真实模型格式漂移。
