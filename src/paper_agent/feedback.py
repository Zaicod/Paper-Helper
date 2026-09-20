from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from paper_agent.evaluation import DimensionScores, HumanScoreSheet


class RewardBreakdown(BaseModel):
    content_accuracy: float = Field(ge=0, le=1)
    evidence_fidelity: float = Field(ge=0, le=1)
    total: float = Field(ge=0, le=1)


class AgentTrajectory(BaseModel):
    trajectory_id: str
    paper_id: str
    prompt: dict
    completion: dict
    human_scores: DimensionScores
    evaluator_scores: DimensionScores | None = None
    reward: RewardBreakdown
    created_at: datetime


def calculate_reward(scores: DimensionScores) -> RewardBreakdown:
    values = scores.model_dump()
    content = (
        values["research_problem"] + values["methods"] + values["major_results"]
    ) / 6
    evidence = values["evidence_discipline"] / 2
    return RewardBreakdown(
        content_accuracy=round(content, 4),
        evidence_fidelity=round(evidence, 4),
        total=round(0.8 * content + 0.2 * evidence, 4),
    )


def export_feedback_dataset(results_dir: Path, output_dir: Path) -> dict:
    analysis_data = json.loads(
        (results_dir / "analysis_outputs.json").read_text(encoding="utf-8")
    )
    human = HumanScoreSheet.model_validate_json(
        (results_dir / "human_scores.json").read_text(encoding="utf-8")
    )
    evaluator_path = results_dir / "evaluator_scores.json"
    evaluator_by_id: dict[str, DimensionScores] = {}
    if evaluator_path.exists():
        evaluator_data = json.loads(evaluator_path.read_text(encoding="utf-8"))
        evaluator_by_id = {
            item["paper_id"]: DimensionScores.model_validate(item["scores"])
            for item in evaluator_data["judgments"]
        }

    items_by_id = {item["paper_id"]: item for item in analysis_data["items"]}
    trajectories: list[AgentTrajectory] = []
    for judgment in human.judgments:
        if judgment.scores is None:
            raise ValueError(f"人工评分未完成：{judgment.paper_id}")
        item = items_by_id[judgment.paper_id]
        trajectories.append(
            AgentTrajectory(
                trajectory_id=f"paper-analysis:{judgment.paper_id}",
                paper_id=judgment.paper_id,
                prompt={"paper": item["paper"]},
                completion=item["agent_output"],
                human_scores=judgment.scores,
                evaluator_scores=evaluator_by_id.get(judgment.paper_id),
                reward=calculate_reward(judgment.scores),
                created_at=datetime.now(timezone.utc),
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(
        output_dir / "rewarded_trajectories.jsonl",
        [item.model_dump(mode="json") for item in trajectories],
    )
    sft_rows = [
        {
            "messages": [
                {
                    "role": "user",
                    "content": "请严格基于论文元数据与摘要生成结构化分析：\n"
                    + json.dumps(item.prompt, ensure_ascii=False),
                },
                {
                    "role": "assistant",
                    "content": json.dumps(item.completion, ensure_ascii=False),
                },
            ],
            "metadata": {
                "paper_id": item.paper_id,
                "human_reward": item.reward.total,
            },
        }
        for item in trajectories
        if item.reward.total >= 0.8
    ]
    _write_jsonl(output_dir / "sft_candidates.jsonl", sft_rows)

    manifest = {
        "trajectory_count": len(trajectories),
        "sft_candidate_count": len(sft_rows),
        "preference_pair_count": 0,
        "grpo_eligible_group_count": 0,
        "reward_source": "human scores; evaluator scores are diagnostic only",
        "limitations": [
            "每个 prompt 目前只有一个 completion，不能直接用于 DPO 或 GRPO。",
            "需要为同一 prompt 采样多个候选并进行人工偏好/奖励标注。",
            "当前模块完成轨迹与奖励数据闭环，不代表已经训练模型。",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 Agent 反馈与训练候选数据")
    parser.add_argument("--results-dir", type=Path, default=Path("evals/results"))
    parser.add_argument("--output-dir", type=Path, default=Path("training/data"))
    args = parser.parse_args()
    manifest = export_feedback_dataset(args.results_dir, args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
