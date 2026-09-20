from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from paper_agent.models import Paper, PaperAnalysis


RUBRIC = {
    "research_problem": "0=错误或缺失；1=方向正确但笼统/遗漏关键约束；2=准确说明论文要解决的问题。",
    "methods": "0=错误或缺失；1=抓住部分核心方法但不完整；2=核心方法和关键区别均准确。",
    "major_results": "0=错误、虚构或缺失；1=结论方向正确但关键结果不完整；2=主要结论及摘要给出的关键数字准确。",
    "evidence_discipline": "0=出现明显无依据事实；1=有轻微越界或证据边界不清；2=严格基于输入摘要并明确未知项。",
}


class ReferenceAnswer(BaseModel):
    research_problem: str
    methods: list[str]
    major_results: list[str]


class EvaluationCase(BaseModel):
    paper: Paper
    reference: ReferenceAnswer


class ReferenceDataset(BaseModel):
    dataset_name: str
    description: str
    papers: list[EvaluationCase]


class DimensionScores(BaseModel):
    research_problem: int = Field(ge=0, le=2)
    methods: int = Field(ge=0, le=2)
    major_results: int = Field(ge=0, le=2)
    evidence_discipline: int = Field(ge=0, le=2)

    @property
    def total(self) -> int:
        return sum(self.model_dump().values())


class HumanJudgment(BaseModel):
    paper_id: str
    scores: DimensionScores | None = None
    notes: str = ""


class DimensionRationales(BaseModel):
    research_problem: str
    methods: str
    major_results: str
    evidence_discipline: str


class EvaluatorJudgment(BaseModel):
    paper_id: str
    scores: DimensionScores
    rationale: DimensionRationales
    suspected_unsupported_claims: list[str]
    verdict: Literal["pass", "needs_review", "fail"]


class HumanScoreSheet(BaseModel):
    dataset_name: str
    rubric: dict[str, str]
    instructions: list[str]
    judgments: list[HumanJudgment]

    @model_validator(mode="after")
    def paper_ids_are_unique(self) -> HumanScoreSheet:
        ids = [item.paper_id for item in self.judgments]
        if len(ids) != len(set(ids)):
            raise ValueError("human score sheet contains duplicate paper_id values")
        return self


def load_reference_dataset(path: Path) -> ReferenceDataset:
    return ReferenceDataset.model_validate_json(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: BaseModel | dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, BaseModel):
        data = value.model_dump(mode="json")
    else:
        data = value
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_human_score_sheet(dataset: ReferenceDataset) -> HumanScoreSheet:
    return HumanScoreSheet(
        dataset_name=dataset.dataset_name,
        rubric=RUBRIC,
        instructions=[
            "逐篇对照 reference、论文摘要和 Agent 输出，不按措辞是否相同评分。",
            "在每个 scores 字段填入 0、1 或 2，并在 notes 中记录扣分依据。",
            "先完成全部人工评分，再运行 evaluator；不要参考 evaluator 后反向修改人工分。",
        ],
        judgments=[HumanJudgment(paper_id=case.paper.paper_id) for case in dataset.papers],
    )


def validate_completed_human_scores(
    sheet: HumanScoreSheet, expected_paper_ids: set[str]
) -> None:
    actual_ids = {item.paper_id for item in sheet.judgments}
    if actual_ids != expected_paper_ids:
        raise ValueError(
            f"人工评分 paper_id 不匹配：expected={sorted(expected_paper_ids)}, "
            f"actual={sorted(actual_ids)}"
        )
    missing = [item.paper_id for item in sheet.judgments if item.scores is None]
    if missing:
        raise ValueError("请先完成人工评分，尚未评分：" + ", ".join(missing))


def deterministic_checks(paper: Paper, analysis: PaperAnalysis) -> dict[str, bool]:
    return {
        "paper_id_exact": analysis.paper_id == paper.paper_id,
        "title_exact": analysis.title == paper.title,
        "research_problem_nonempty": bool(analysis.research_problem.strip()),
        "methods_nonempty": bool(analysis.methods),
        "results_nonempty": bool(analysis.results),
    }


def build_score_comparison(
    human_sheet: HumanScoreSheet,
    evaluator_judgments: list[EvaluatorJudgment],
) -> list[dict]:
    human_by_id = {item.paper_id: item for item in human_sheet.judgments}
    comparison = []
    for judgment in evaluator_judgments:
        human = human_by_id[judgment.paper_id]
        if human.scores is None:
            raise ValueError(f"人工评分未完成：{judgment.paper_id}")
        human_scores = human.scores.model_dump()
        evaluator_scores = judgment.scores.model_dump()
        comparison.append(
            {
                "paper_id": judgment.paper_id,
                "human_scores": human_scores,
                "human_total": human.scores.total,
                "evaluator_scores": evaluator_scores,
                "evaluator_total": judgment.scores.total,
                "total_difference": judgment.scores.total - human.scores.total,
                "requires_discussion": any(
                    evaluator_scores[key] != human_scores[key]
                    for key in human_scores
                ),
            }
        )
    return comparison


def build_evaluation_summary(
    human_sheet: HumanScoreSheet,
    evaluator_judgments: list[EvaluatorJudgment],
) -> dict:
    evaluator_by_id = {item.paper_id: item for item in evaluator_judgments}
    dimensions = tuple(RUBRIC)
    human_dimension_totals = {name: 0 for name in dimensions}
    evaluator_dimension_totals = {name: 0 for name in dimensions}
    disagreements = []
    low_score_cases = []
    unsupported_claims = []

    for human in human_sheet.judgments:
        if human.scores is None:
            raise ValueError(f"人工评分未完成：{human.paper_id}")
        evaluator = evaluator_by_id[human.paper_id]
        human_scores = human.scores.model_dump()
        evaluator_scores = evaluator.scores.model_dump()
        rationales = evaluator.rationale.model_dump()
        for dimension in dimensions:
            human_score = human_scores[dimension]
            evaluator_score = evaluator_scores[dimension]
            human_dimension_totals[dimension] += human_score
            evaluator_dimension_totals[dimension] += evaluator_score
            if human_score != evaluator_score:
                disagreements.append(
                    {
                        "paper_id": human.paper_id,
                        "dimension": dimension,
                        "human_score": human_score,
                        "evaluator_score": evaluator_score,
                        "human_notes": human.notes,
                        "evaluator_rationale": rationales[dimension],
                    }
                )
            if human_score < 2:
                low_score_cases.append(
                    {
                        "paper_id": human.paper_id,
                        "dimension": dimension,
                        "human_score": human_score,
                        "evaluator_score": evaluator_score,
                        "human_notes": human.notes,
                        "status": (
                            "human_and_evaluator_agree"
                            if human_score == evaluator_score
                            else "human_stricter_than_evaluator"
                        ),
                    }
                )
        for claim in evaluator.suspected_unsupported_claims:
            unsupported_claims.append(
                {"paper_id": human.paper_id, "claim": claim}
            )

    paper_count = len(human_sheet.judgments)
    max_per_dimension = paper_count * 2
    human_total = sum(human_dimension_totals.values())
    evaluator_total = sum(evaluator_dimension_totals.values())
    content_dimensions = ("research_problem", "methods", "major_results")
    human_content = sum(human_dimension_totals[name] for name in content_dimensions)
    evaluator_content = sum(
        evaluator_dimension_totals[name] for name in content_dimensions
    )
    max_content = paper_count * len(content_dimensions) * 2
    exact_dimension_matches = paper_count * len(dimensions) - len(disagreements)

    return {
        "metric_definitions": {
            "accuracy": "研究问题、方法、主要结果三个维度的得分之和 / 满分。",
            "evidence_fidelity": "evidence_discipline 得分之和 / 满分。",
            "agreement": "人工与 evaluator 完全相同的维度数 / 全部评分维度数。",
        },
        "sample_count": paper_count,
        "human": {
            "dimension_totals": human_dimension_totals,
            "overall_score": human_total,
            "overall_max": paper_count * len(dimensions) * 2,
            "overall_percent": round(human_total / (paper_count * len(dimensions) * 2) * 100, 2),
            "accuracy_score": human_content,
            "accuracy_max": max_content,
            "accuracy_percent": round(human_content / max_content * 100, 2),
            "evidence_fidelity_score": human_dimension_totals["evidence_discipline"],
            "evidence_fidelity_max": max_per_dimension,
            "evidence_fidelity_percent": round(
                human_dimension_totals["evidence_discipline"]
                / max_per_dimension
                * 100,
                2,
            ),
        },
        "evaluator": {
            "dimension_totals": evaluator_dimension_totals,
            "overall_score": evaluator_total,
            "overall_max": paper_count * len(dimensions) * 2,
            "overall_percent": round(evaluator_total / (paper_count * len(dimensions) * 2) * 100, 2),
            "accuracy_score": evaluator_content,
            "accuracy_max": max_content,
            "accuracy_percent": round(evaluator_content / max_content * 100, 2),
            "evidence_fidelity_score": evaluator_dimension_totals["evidence_discipline"],
            "evidence_fidelity_max": max_per_dimension,
            "evidence_fidelity_percent": round(
                evaluator_dimension_totals["evidence_discipline"]
                / max_per_dimension
                * 100,
                2,
            ),
        },
        "agreement": {
            "exact_dimension_matches": exact_dimension_matches,
            "dimension_count": paper_count * len(dimensions),
            "exact_agreement_percent": round(
                exact_dimension_matches / (paper_count * len(dimensions)) * 100,
                2,
            ),
            "mean_absolute_difference": round(
                sum(
                    abs(item["evaluator_score"] - item["human_score"])
                    for item in disagreements
                )
                / (paper_count * len(dimensions)),
                3,
            ),
        },
        "score_disagreements": disagreements,
        "human_low_score_cases": low_score_cases,
        "evaluator_suspected_unsupported_claims": unsupported_claims,
        "caution": (
            "Evaluator 与分析 Agent 使用同一模型系列，可能共享偏差；"
            "该结果只作为人工评审的第二意见。"
        ),
    }
