"""interfaces cli implementation."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from pydantic import ValidationError

from paper_agent.core.errors import PublicResearchError, public_error_message
from paper_agent.interfaces.report import save_report
from paper_agent.services.research import (
    ResearchOptions, ResearchService, build_live_search as _build_live_search,
)
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
        "--engine",
        choices=("legacy", "langgraph"),
        default="legacy",
        help="legacy 使用原 Python 工作流；langgraph 运行第一阶段离线学习图",
    )
    run_parser.add_argument(
        "--rag",
        choices=("none", "abstract", "pdf"),
        default="none",
        help="证据模式：none 仅原始摘要；abstract 建立摘要索引；pdf 优先全文并在失败时回退摘要",
    )
    run_parser.add_argument(
        "--decision",
        choices=("none", "fixture", "jev"),
        default="none",
        help="RAG 证据决策门：fixture 离线演练；jev 调用 TypeSafe API",
    )
    run_parser.add_argument(
        "--embedding-provider",
        choices=("local", "qwen"),
        default="local",
        help="RAG 向量来源；local 免费可复现，qwen 使用兼容 Embedding API",
    )
    run_parser.add_argument(
        "--embedding-model",
        default=None,
        help="Embedding 模型，Qwen 默认读取 QWEN_EMBEDDING_MODEL",
    )
    run_parser.add_argument(
        "--context-token-budget",
        type=int,
        default=6000,
        help="每篇论文进入分析 Agent 的估算 token 上限",
    )
    run_parser.add_argument("--rag-top-k", type=int, default=4)
    run_parser.add_argument('--index-namespace', default='cli-local', help='CLI 本地索引命名空间；Java 服务使用服务端账号空间')
    run_parser.add_argument('--rebuild-index', action='store_true', help='重新获取和向量化所选论文，发布新的完整索引版本')
    run_parser.add_argument(
        "--rag-index",
        type=Path,
        default=Path("outputs/rag_index.json"),
        help="demo 的 JSON 索引路径；live 使用 PAPERFLOW_CHROMA_DIR 持久化",
    )
    run_parser.add_argument(
        "--provider",
        choices=("openai", "qwen"),
        default="qwen",
        help="live 模式的模型提供商",
    )
    run_parser.add_argument(
        "--model",
        default=None,
        help="覆盖所选 provider 的默认模型名称",
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


async def run_command(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    if args.engine == "langgraph":
        if args.mode != "demo" or args.rag != "none" or args.decision != "none":
            raise SystemExit("LangGraph 第一阶段只支持 --mode demo --rag none --decision none。")

        from paper_agent.workflows.research_graph import run_fixture_research_graph

        state = await run_fixture_research_graph(
            topic=args.topic,
            limit=args.limit,
            category=args.category,
        )
        return save_report(state["report"], args.output_dir)

    try:
        options = ResearchOptions(
            mode=args.mode, rag=args.rag, decision=args.decision,
            provider=args.provider, model=args.model, source=args.source,
            embedding_provider=args.embedding_provider,
            embedding_model=args.embedding_model,
            context_token_budget=args.context_token_budget,
            rag_top_k=args.rag_top_k,
            index_namespace=getattr(args, 'index_namespace', 'cli-local'),
            rebuild_index=getattr(args, 'rebuild_index', False),
        )
        service = ResearchService(options, index_path=args.rag_index if args.rag != "none" else None)
        report = await service.run(args.topic, args.limit, args.category)
    except ValidationError as exc:
        messages = [item['msg'] for item in exc.errors(include_input=False, include_context=False)]
        raise SystemExit('; '.join(messages)) from None
    except (ValueError, PublicResearchError) as exc:
        raise SystemExit(public_error_message(exc)) from None
    return save_report(report, args.output_dir)


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "run":
        markdown_path, json_path, html_path = asyncio.run(run_command(args))
        print("研究工作流已完成。")
        print(f"Markdown: {markdown_path.resolve()}")
        print(f"JSON: {json_path.resolve()}")
        print(f"HTML: {html_path.resolve()}")
