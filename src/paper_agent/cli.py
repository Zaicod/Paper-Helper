from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from paper_agent.demo_team import DemoResearchTeam
from paper_agent.report import save_report
from paper_agent.search import (
    ArxivSearchClient,
    FallbackSearchClient,
    FixtureSearchClient,
    OpenAlexSearchClient,
)
from paper_agent.workflow import ResearchWorkflow
from dotenv import load_dotenv

load_dotenv()

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-agent",
        description="教学型论文研究多 Agent 助手",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="运行一次研究工作流")
    run_parser.add_argument("--topic", required=True, help="研究方向或检索主题")
    run_parser.add_argument(
        "--mode",
        choices=("demo", "live"),
        default="demo",
        help="demo 完全离线；live 使用 arXiv 与所选模型 API",
    )
    run_parser.add_argument(
        "--provider",
        choices=("openai", "qwen"),
        default="qwen",
        help="live 模式的模型提供商",
    )
    run_parser.add_argument(
        "--model",
        default="qwen3.8-flash",
        help="覆盖默认模型名称，例如 qwen3.8-flash",
    )
    run_parser.add_argument("--limit", type=int, default=3, help="论文数量，1—20")
    run_parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs"), help="结果目录"
    )
    run_parser.add_argument(
        "--category",
        choices=("cs.CL", "cs.AI"),
        default=None,
        help="让搜索结果只保留指定分类",
    )
    run_parser.add_argument(
        "--source",
        choices=("auto", "arxiv", "openalex"),
        default="auto",
        help="文献源；auto 在 arXiv 失败时自动切换 OpenAlex",
    )
    return parser


async def run_command(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.mode == "demo":
        search = FixtureSearchClient()
        team = DemoResearchTeam()
    elif args.provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("OpenAI live 模式需要 OPENAI_API_KEY。")
        from paper_agent.agent_team import AgentResearchTeam

        search = _build_live_search(args.source)
        team = AgentResearchTeam(
            model=args.model or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        )
    else:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise SystemExit("Qwen live 模式需要 DASHSCOPE_API_KEY。")
        from paper_agent.agent_team import AgentResearchTeam
        from paper_agent.providers import (
            DEFAULT_QWEN_BASE_URL,
            DEFAULT_QWEN_MODEL,
            build_qwen_model,
            qwen_model_settings,
        )

        model = build_qwen_model(
            api_key=api_key,
            model_name=args.model
            or os.getenv("QWEN_MODEL", DEFAULT_QWEN_MODEL),
            base_url=os.getenv("DASHSCOPE_BASE_URL", DEFAULT_QWEN_BASE_URL),
        )
        search = _build_live_search(args.source)
        team = AgentResearchTeam(
            model=model,
            model_settings=qwen_model_settings(),
        )

    workflow = ResearchWorkflow(search=search, team=team)
    report = await workflow.run(
        topic=args.topic,
        limit=args.limit,
        category=args.category,
    )
    return save_report(report, args.output_dir)


def _build_live_search(source: str):
    if source == "arxiv":
        return ArxivSearchClient()
    if source == "openalex":
        return OpenAlexSearchClient(api_key=os.getenv("OPENALEX_API_KEY"))
    return FallbackSearchClient(
        [
            ArxivSearchClient(timeout_seconds=8.0),
            OpenAlexSearchClient(api_key=os.getenv("OPENALEX_API_KEY")),
        ]
    )


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "run":
        markdown_path, json_path = asyncio.run(run_command(args))
        print("研究工作流已完成。")
        print(f"Markdown: {markdown_path.resolve()}")
        print(f"JSON: {json_path.resolve()}")
