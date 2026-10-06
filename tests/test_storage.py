from pathlib import Path
from datetime import date, timedelta

from paper_agent.langgraph_workflow import run_fixture_research_graph
from paper_agent.mindmap import FixtureMindMapAgent
from paper_agent.storage import PaperLibrary


async def test_library_saves_report_without_duplicate_papers(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    state = await run_fixture_research_graph("RAG", limit=2)
    report = state["report"]

    library.save_report(report, "run-1")
    library.save_report(report, "run-2")

    papers = library.list_papers()
    assert [paper.paper_id for paper in papers] == ["demo-002", "demo-001"]
    assert all(paper.analysis_count == 2 for paper in papers)
    assert papers[0].authors == ["Demo Author C"]
    library.close()


async def test_library_supports_collections_and_tags(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    report = (await run_fixture_research_graph("RAG", limit=1))["report"]
    library.save_report(report, "run-1")

    collection = library.create_collection("必读", "准备面试时复习")
    library.add_to_collection(collection.id, "demo", "demo-001")
    library.add_to_collection(collection.id, "demo", "demo-001")
    library.add_tag("demo", "demo-001", "RAG")

    collections = library.list_collections()
    paper = library.get_paper("demo", "demo-001")
    assert collections[0].paper_count == 1
    assert paper is not None
    assert paper.tags == ["RAG"]
    library.close()


def test_mysql_url_selects_mysql_dialect_without_connecting() -> None:
    library = PaperLibrary(
        "mysql+pymysql://paper_agent:password@127.0.0.1:3306/paper_agent"
    )

    assert library.engine.dialect.name == "mysql"
    assert library.engine.driver == "pymysql"
    library.close()


async def test_collection_workspace_stores_notes_dates_and_mind_maps(
    tmp_path: Path,
) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    report = (await run_fixture_research_graph("RAG", limit=2))["report"]
    library.save_report(report, "run-1")
    collection = library.create_collection("RAG 工作区")
    for paper in report.papers:
        library.add_to_collection(collection.id, paper.source, paper.paper_id)

    library.update_collection_note(collection.id, "整体归纳")
    library.update_paper_note(collection.id, "demo", "demo-001", "单篇笔记")
    selected = library.get_collection_papers(
        collection.id, [("demo", "demo-001")]
    )
    today = date.today().isoformat()
    future = (date.today() + timedelta(days=1)).isoformat()
    assert len(library.get_collection_papers(collection.id, date_from=today)) == 2
    assert library.get_collection_papers(collection.id, date_from=future) == []
    overall, notes = library.get_collection_notes(collection.id)
    draft = await FixtureMindMapAgent().generate(
        "RAG 安全", selected, notes, overall
    )
    saved = library.save_mind_map(
        collection.id,
        "RAG 安全",
        None,
        None,
        "fixture-agent",
        draft,
        [("demo", "demo-001")],
    )
    library.link_research_run(collection.id, "run-1")
    detail = library.get_collection(collection.id)

    assert detail is not None
    assert detail.overall_note == "整体归纳"
    assert detail.papers[0].added_at is not None
    assert next(paper for paper in detail.papers if paper.paper_id == "demo-001").note == "单篇笔记"
    assert detail.mind_maps[0].id == saved.id
    assert detail.mind_maps[0].paper_ids == ["demo-001"]
    assert detail.research_run_ids == ["run-1"]
    library.close()


async def test_collection_search_and_delete_keep_paper_records(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    report = (await run_fixture_research_graph("RAG", limit=1))["report"]
    library.save_report(report, "run-1")
    target = library.create_collection("RAG 安全", "检索增强安全")
    library.create_collection("多智能体", "Agent 协作")
    library.add_to_collection(target.id, "demo", "demo-001")
    library.update_paper_note(target.id, "demo", "demo-001", "即将随收藏夹删除")

    assert [item.name for item in library.list_collections("安全")] == ["RAG 安全"]
    assert library.delete_collection(target.id) is True
    assert library.get_collection(target.id) is None
    assert library.get_paper("demo", "demo-001") is not None
    assert library.delete_collection(target.id) is False
    library.close()
