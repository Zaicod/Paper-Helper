import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from paper_agent.mcp_server import PaperMCPService, read_research_report
from paper_agent.models import Paper


async def test_mcp_service_indexes_and_retrieves_evidence() -> None:
    service = PaperMCPService()
    paper = Paper(
        paper_id="mcp-1",
        title="MCP Paper",
        authors=["Author"],
        abstract="retrieval augmented generation with evidence",
        page_url="https://example.com/mcp-1",
    )

    status = await service.index([paper])
    packet = await service.retrieve("retrieval evidence", paper_id="mcp-1")

    assert status["indexed"] == 1
    assert packet["chunks"][0]["paper_id"] == "mcp-1"


def test_mcp_report_reader_blocks_path_traversal(tmp_path) -> None:
    outside = tmp_path.parent / "outside.json"
    outside.write_text(json.dumps({"secret": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="inside output_dir"):
        read_research_report("../outside.json", str(tmp_path))


async def test_stdio_mcp_protocol_lists_project_tools() -> None:
    project_root = Path(__file__).parents[1]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "paper_agent.mcp_server", "--transport", "stdio"],
        cwd=str(project_root),
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            response = await session.list_tools()
            paper = Paper(
                paper_id="protocol-1",
                title="Protocol Paper",
                authors=["Author"],
                abstract="agent protocol retrieval evidence",
                page_url="https://example.com/protocol-1",
            )
            indexed = await session.call_tool(
                "index_papers",
                {"papers_json": json.dumps([paper.model_dump(mode="json")])},
            )
            retrieved = await session.call_tool(
                "retrieve_evidence",
                {"query": "retrieval evidence", "paper_id": "protocol-1", "top_k": 1},
            )

    assert {tool.name for tool in response.tools} == {
        "search_papers",
        "index_papers",
        "retrieve_evidence",
        "read_research_report",
    }
    assert indexed.isError is False
    assert retrieved.isError is False
    assert "protocol-1:p0:c0" in retrieved.content[0].text
