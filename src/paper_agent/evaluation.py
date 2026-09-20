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


class EvaluatorJudgment(BaseModel):
    paper_id: str
    scores: DimensionScores
    rationale: dict[str, str]
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
