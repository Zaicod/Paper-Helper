import json
from pathlib import Path

from paper_agent.evaluation import DimensionScores
from paper_agent.feedback import calculate_reward, export_feedback_dataset


RESULTS_DIR = Path(__file__).parents[1] / "evals" / "results"


def test_human_evidence_score_contributes_to_reward() -> None:
    high = calculate_reward(
        DimensionScores(
            research_problem=2,
            methods=2,
            major_results=2,
            evidence_discipline=2,
        )
    )
    low_evidence = calculate_reward(
        DimensionScores(
            research_problem=2,
            methods=2,
            major_results=2,
            evidence_discipline=0,
        )
    )

    assert high.total == 1
    assert low_evidence.total == 0.8


def test_feedback_export_is_human_rewarded_and_not_fake_grpo(tmp_path: Path) -> None:
    manifest = export_feedback_dataset(RESULTS_DIR, tmp_path)

    trajectories = (tmp_path / "rewarded_trajectories.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    saved_manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["trajectory_count"] == 5
    assert len(trajectories) == 5
    assert saved_manifest["grpo_eligible_group_count"] == 0
    assert "human scores" in saved_manifest["reward_source"]
