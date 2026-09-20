from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from paper_agent.context import ContextBuilder
from paper_agent.models import Paper
from paper_agent.rag import HashingEmbedder, PaperRAG
from paper_agent.search import ArxivSearchClient, FallbackSearchClient, OpenAlexSearchClient


class PaperMCPService:
    """Testable application service behind the MCP transport."""

    def __init__(self) -> None:
        self.rag = PaperRAG(
            HashingEmbedder(),
            context_builder=ContextBuilder(token_budget=4000, max_chunks=8),
        )
        self.indexed_paper_ids: set[str] = set()

    async def search(
        self,
        topic: str,
        limit: int = 5,
        category: str | None = None,
        source: str = "auto",
    ) -> list[dict]:
        if source == "arxiv":
            client = ArxivSearchClient()
        elif source == "openalex":
            client = OpenAlexSearchClient()
        elif source == "auto":
            client = FallbackSearchClient(
                [ArxivSearchClient(timeout_seconds=8), OpenAlexSearchClient()]
            )
        else:
            raise ValueError("source must be auto, arxiv, or openalex")
        papers = await client.search(topic, limit, category)
        return [paper.model_dump(mode="json") for paper in papers]

    async def index(self, papers: list[Paper]) -> dict:
        new_papers = [paper for paper in papers if paper.paper_id not in self.indexed_paper_ids]
        if new_papers:
            await self.rag.index_papers(new_papers)
            self.indexed_paper_ids.update(paper.paper_id for paper in new_papers)
        return {
            "indexed": len(new_papers),
            "total_indexed": len(self.indexed_paper_ids),
            "paper_ids": sorted(self.indexed_paper_ids),
        }

    async def retrieve(
        self, query: str, paper_id: str | None = None, top_k: int = 5
    ) -> dict:
        packet = await self.rag.retrieve(query, top_k=top_k, paper_id=paper_id)
        return packet.model_dump(mode="json")


service = PaperMCPService()
server = FastMCP("paper-helper", host="127.0.0.1", port=8765, stateless_http=True)


@server.tool()
async def search_papers(
    topic: str,
    limit: int = 5,
    category: str | None = None,
    source: str = "auto",
) -> list[dict]:
    """Search trusted paper providers and return structured metadata."""

    return await service.search(topic, limit, category, source)


@server.tool()
async def index_papers(papers_json: str) -> dict:
    """Index paper metadata/abstracts supplied as a JSON array for local RAG."""

    raw = json.loads(papers_json)
    if not isinstance(raw, list):
        raise ValueError("papers_json must contain a JSON array")
    papers = [Paper.model_validate(item) for item in raw]
    return await service.index(papers)


@server.tool()
async def retrieve_evidence(
    query: str,
    paper_id: str | None = None,
    top_k: int = 5,
) -> dict:
    """Retrieve evidence chunks from papers indexed in this MCP process."""

    return await service.retrieve(query, paper_id, top_k)


@server.tool()
def read_research_report(report_name: str, output_dir: str = "outputs") -> dict:
    """Read one generated JSON report while preventing path traversal."""

    root = Path(output_dir).resolve()
    path = (root / report_name).resolve()
    if root not in path.parents or path.suffix.lower() != ".json":
        raise ValueError("report must be a JSON file inside output_dir")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper Helper MCP Server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    args = parser.parse_args()
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
