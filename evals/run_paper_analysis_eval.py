from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from agents import Agent, Runner
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from paper_agent.agent_team import AgentResearchTeam
from paper_agent.evaluation import (
    EvaluatorJudgment,
    HumanScoreSheet,
    build_human_score_sheet,
    deterministic_checks,
    load_reference_dataset,
    save_json,
    validate_completed_human_scores,
)
from paper_agent.models import PaperAnalysis
from paper_agent.providers import (
    DEFAULT_QWEN_BASE_URL,
    DEFAULT_QWEN_MODEL,
    build_qwen_model,
    qwen_model_settings,
)


DEFAULT_DATASET = PROJECT_ROOT / "evals" / "paper_analysis_reference.json"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "evals" / "results"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="文献分析 Agent 的分阶段评测")
    parser.add_argument(
        "stage",
        choices=("analyze", "evaluate"),
        help="analyze 生成输出和人工评分表；evaluate 只在人工评分完成后运行",
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--model", default=None)
    return parser


def load_qwen():
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("需要在 .env 或环境变量中配置 DASHSCOPE_API_KEY。")
    model_name = os.getenv("QWEN_MODEL", DEFAULT_QWEN_MODEL)
    base_url = os.getenv("DASHSCOPE_BASE_URL", DEFAULT_QWEN_BASE_URL)
    return build_qwen_model(api_key, model_name, base_url)


def render_human_review(outputs: list[dict], rubric: dict[str, str]) -> str:
    lines = [
        "# 文献分析 Agent 人工评分单",
        "",
        "> 先独立人工评分，再运行 evaluator。参考答案是语义锚点，不要求逐字一致。",
        "",
        "## 评分规则",
        "",
    ]
    for name, rule in rubric.items():
        lines.append(f"- `{name}`：{rule}")
    for item in outputs:
        ref = item["reference"]
        actual = item["agent_output"]
        lines.extend(
            [
                "",
                f"## {item['paper_id']} — {item['paper']['title']}",
                "",
                "### 研究问题",
                "",
                f"- 参考：{ref['research_problem']}",
                f"- Agent：{actual['research_problem']}",
                "- 人工分（0—2）：",
                "",
                "### 方法",
                "",
                "参考答案：",
                *[f"- {value}" for value in ref["methods"]],
                "",
                "Agent 输出：",
                *[f"- {value}" for value in actual["methods"]],
                "",
                "人工分（0—2）：",
                "",
                "### 主要结果",
                "",
                "参考答案：",
                *[f"- {value}" for value in ref["major_results"]],
                "",
                "Agent 输出：",
                *[f"- {value}" for value in actual["results"]],
                "",
                "人工分（0—2）：",
                "",
                "### 证据约束",
                "",
                "Agent evidence_notes：",
                *[f"- {value}" for value in actual["evidence_notes"]],
                "",
                "人工分（0—2）：",
                "",
                "扣分依据 / 备注：",
            ]
        )
    return "\n".join(lines) + "\n"


async def analyze(args: argparse.Namespace) -> None:
    dataset = load_reference_dataset(args.dataset)
    model = load_qwen()
    if args.model:
        load_dotenv(PROJECT_ROOT / ".env")
        model = build_qwen_model(
            os.environ["DASHSCOPE_API_KEY"],
            args.model,
            os.getenv("DASHSCOPE_BASE_URL", DEFAULT_QWEN_BASE_URL),
        )
    team = AgentResearchTeam(
        basemodel=model,
        analyst_model=model,
        synthesis_model=model,
        ideator_model=model,
        model_settings=qwen_model_settings(),
    )

    outputs = []
    for index, case in enumerate(dataset.papers, start=1):
        print(f"[{index}/{len(dataset.papers)}] 分析 {case.paper.paper_id} ...")
        analysis = await team.analyze_paper(case.paper)
        outputs.append(
            {
                "paper_id": case.paper.paper_id,
                "paper": case.paper.model_dump(mode="json"),
                "reference": case.reference.model_dump(mode="json"),
                "agent_output": analysis.model_dump(mode="json"),
                "deterministic_checks": deterministic_checks(case.paper, analysis),
            }
        )

    save_json(args.results_dir / "analysis_outputs.json", {
        "dataset_name": dataset.dataset_name,
        "model": args.model or os.getenv("QWEN_MODEL", DEFAULT_QWEN_MODEL),
        "items": outputs,
    })
    score_sheet = build_human_score_sheet(dataset)
    save_json(args.results_dir / "human_scores.json", score_sheet)
    review_path = args.results_dir / "human_review.md"
    review_path.write_text(
        render_human_review(outputs, score_sheet.rubric), encoding="utf-8"
    )
    print(f"分析输出：{args.results_dir / 'analysis_outputs.json'}")
    print(f"人工评分表：{args.results_dir / 'human_scores.json'}")
    print(f"人工对照稿：{review_path}")
    print("请先填写人工评分表，再运行 evaluate 阶段。")


EVALUATOR_INSTRUCTIONS = """
你是文献分析质量评审员。你会收到论文摘要、人工参考答案和待评测的 Agent 输出。
请严格按给定的四项 0—2 分 rubric 独立评分，并输出 EvaluatorJudgment。

规则：
1. 参考答案是评分锚点，但不是要求逐字匹配；判断语义是否正确。
2. 不得利用你记忆中的论文正文补充输入之外的事实。
3. 明确指出待评输出中的无依据内容；不要因为语言流畅而加分。
4. paper_id 必须与输入完全一致。
5. total 不需要输出，由程序计算。
""".strip()


async def evaluate(args: argparse.Namespace) -> None:
    dataset = load_reference_dataset(args.dataset)
    human_path = args.results_dir / "human_scores.json"
    output_path = args.results_dir / "analysis_outputs.json"
    if not human_path.exists() or not output_path.exists():
        raise SystemExit("缺少分析输出或人工评分表，请先运行 analyze 阶段。")

    human_sheet = HumanScoreSheet.model_validate_json(
        human_path.read_text(encoding="utf-8")
    )
    try:
        validate_completed_human_scores(
            human_sheet, {case.paper.paper_id for case in dataset.papers}
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    analysis_data = json.loads(output_path.read_text(encoding="utf-8"))
    by_id = {item["paper_id"]: item for item in analysis_data["items"]}
    model = load_qwen()
    if args.model:
        model = build_qwen_model(
            os.environ["DASHSCOPE_API_KEY"],
            args.model,
            os.getenv("DASHSCOPE_BASE_URL", DEFAULT_QWEN_BASE_URL),
        )
    evaluator = Agent(
        name="文献分析评测员",
        instructions=EVALUATOR_INSTRUCTIONS,
        model=model,
        model_settings=qwen_model_settings(),
        output_type=EvaluatorJudgment,
    )

    judgments = []
    for index, case in enumerate(dataset.papers, start=1):
        print(f"[{index}/{len(dataset.papers)}] 评测 {case.paper.paper_id} ...")
        payload = {
            "rubric": human_sheet.rubric,
            "paper": case.paper.model_dump(mode="json"),
            "reference": case.reference.model_dump(mode="json"),
            "agent_output": by_id[case.paper.paper_id]["agent_output"],
        }
        result = await Runner.run(
            evaluator,
            "请独立评分：\n" + json.dumps(payload, ensure_ascii=False, indent=2),
        )
        judgments.append(result.final_output)

    human_by_id = {item.paper_id: item for item in human_sheet.judgments}
    comparison = []
    for judgment in judgments:
        human = human_by_id[judgment.paper_id]
        assert human.scores is not None
        comparison.append(
            {
                "paper_id": judgment.paper_id,
                "human_scores": human.scores.model_dump(),
                "human_total": human.scores.total,
                "evaluator_scores": judgment.scores.model_dump(),
                "evaluator_total": judgment.scores.total,
                "total_difference": judgment.scores.total - human.scores.total,
                "requires_discussion": any(
                    abs(judgment.scores.model_dump()[key] - human.scores.model_dump()[key]) >= 2
                    for key in human.scores.model_dump()
                ),
            }
        )

    save_json(args.results_dir / "evaluator_scores.json", {
        "warning": "Evaluator Agent 是第二意见，不是唯一真值。最终判断以人工复核和证据为准。",
        "judgments": [item.model_dump(mode="json") for item in judgments],
    })
    save_json(args.results_dir / "score_comparison.json", comparison)
    print(f"Evaluator 评分：{args.results_dir / 'evaluator_scores.json'}")
    print(f"人机差异表：{args.results_dir / 'score_comparison.json'}")


def main() -> None:
    args = build_parser().parse_args()
    if args.stage == "analyze":
        asyncio.run(analyze(args))
    else:
        asyncio.run(evaluate(args))


if __name__ == "__main__":
    main()
