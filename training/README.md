# Agent 反馈与训练数据

运行：

```powershell
paper-agent-feedback --results-dir evals/results --output-dir training/data
```

`rewarded_trajectories.jsonl` 保存带人工奖励的轨迹，`sft_candidates.jsonl` 保存高分 SFT 候选，`manifest.json` 明确数据是否满足不同训练方式。

当前数据不包含同一 prompt 的多个候选或偏好对，因此不满足 DPO/GRPO。不要在简历中把本目录描述成已经完成强化学习训练。
