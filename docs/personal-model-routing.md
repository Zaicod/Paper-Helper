# 个人模型路由学习手册

## 1. 为什么不是一个全局模型下拉框

不同 Agent 的任务复杂度不同：逐篇抽取会被调用很多次，更看重成本和速度；跨论文总结与创新构思调用次数少，但更依赖推理质量。把一个昂贵模型用于所有节点会浪费 token，把最小模型用于所有节点又可能降低最终报告质量。

本项目因此把模型选择放在 Agent 定义附近：

```text
当前用户
  ├─ Provider 凭据（Qwen / OpenAI / DeepSeek）
  └─ Agent 路由
       ├─ analyst      → provider + model
       ├─ synthesizer  → provider + model
       ├─ ideator      → provider + model
       └─ mindmap      → provider + model
```

这与 Agents SDK 官方“为 specialist 显式设置模型、在同一工作流混用不同模型档位”的建议一致：<https://developers.openai.com/api/docs/guides/agents/models>。

## 2. 密钥如何保存

- 浏览器只在保存时发送新密钥。
- 后端用 Fernet 对称加密后写入 `provider_credentials`。
- 加密主密钥不写数据库；生产环境使用 `PAPER_AGENT_SETTINGS_KEY`，本地开发自动生成 `outputs/web/.model-settings.key`。
- 查询设置只返回掩码和来源，不返回明文或密文。
- 个人配置优先；没有个人配置时才读取服务器环境变量。

注意：如果丢失 Fernet 主密钥，已经加密的个人 API Key 无法恢复，只能重新填写。这是预期的安全属性。

## 3. 请求时如何选择模型

研究任务创建时，FastAPI 从登录会话取得 `user_id`，读取该用户的三项研究 Agent 配置，创建一次任务专属的 `AgentResearchTeam`，再注入 `ResearchTaskManager`。它不会修改全局模型，因此两个用户并发运行时不会串配置。

思维导图接口单独解析 `mindmap` 路由并创建 `ConfiguredMindMapAgent`。所以修改思维导图模型不会影响逐篇分析。

## 4. 推荐方案

- 额度优先：所有角色使用 Qwen Flash。
- 均衡推荐：高频分析和导图使用 Flash，总结使用 Plus，创新使用 Max。
- 质量优先：所有角色使用 Max。

推荐只是初始配置。正确做法是使用同一批论文记录质量、延迟和 token 消耗，然后选择能达到质量阈值的最轻模型。官方资料也建议按实际工作流实验，而不是假设最大模型永远最划算。

## 5. 收藏夹删除边界

删除收藏夹会删除它的整体笔记、单篇语境笔记、思维导图和研究运行关联，但不会删除 `papers` 表中的公共论文元数据或本地 PDF。这避免一篇论文同时属于多个收藏夹时被误删。

## 6. 建议练习

1. 给 Provider 增加“测试连接”接口，并设置短超时。
2. 为每次 Agent 调用记录 provider、model、输入/输出 token 和耗时。
3. 基于 evaluator 分数与 token 消耗制作 Pareto 对比图。
4. 增加密钥轮换流程，并测试旧主密钥迁移。
5. 给收藏夹增加用户所有权，使资料空间也完全按用户隔离。
