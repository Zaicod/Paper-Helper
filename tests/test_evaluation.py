import json
from pathlib import Path

import pytest

from paper_agent.evaluation import (
    DimensionScores,
    HumanScoreSheet,
    build_human_score_sheet,
    deterministic_checks,
    load_reference_dataset,
    validate_completed_human_scores,
)
from paper_agent.models import PaperAnalysis


DATASET_PATH = Path(__file__).parents[1] / "evals" / "paper_analysis_reference.json"


def test_reference_dataset_contains_five_unique_papers():
    dataset = load_reference_dataset(DATASET_PATH)

    assert len(dataset.papers) == 5
    assert len({case.paper.paper_id for case in dataset.papers}) == 5


def test_new_human_score_sheet_is_intentionally_incomplete():
    dataset = load_reference_dataset(DATASET_PATH)
    sheet = build_human_score_sheet(dataset)

    with pytest.raises(ValueError, match="请先完成人工评分"):
        validate_completed_human_scores(
            sheet, {case.paper.paper_id for case in dataset.papers}
        )


def test_completed_human_score_sheet_passes_validation():
    dataset = load_reference_dataset(DATASET_PATH)
    sheet = build_human_score_sheet(dataset)
    for judgment in sheet.judgments:
        judgment.scores = DimensionScores(
            research_problem=2,
            methods=2,
            major_results=2,
            evidence_discipline=2,
        )

    validate_completed_human_scores(
        sheet, {case.paper.paper_id for case in dataset.papers}
    )


def test_deterministic_checks_detect_identifier_mismatch():
    dataset = load_reference_dataset(DATASET_PATH)
    paper = dataset.papers[0].paper
    analysis = PaperAnalysis(
        paper_id="wrong-id",
        title=paper.title,
        research_problem="问题",
        innovation_points=["创新"],
        methods=["方法"],
        results=["结果"],
        limitations=[],
        evidence_notes=["证据"],
        datasets=[],
    )

    checks = deterministic_checks(paper, analysis)

    assert checks["paper_id_exact"] is False
    assert checks["title_exact"] is True
