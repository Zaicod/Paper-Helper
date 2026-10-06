from pathlib import Path

import httpx

from paper_agent.catalog import DownloadedPdf, PaperCatalog
from paper_agent.models import Paper
from paper_agent.storage import PaperLibrary
from paper_agent.web_app import ResearchTaskManager, create_app


def sample_paper() -> Paper:
    return Paper(
        paper_id="2401.01234",
        source="arxiv",
        title="A Searchable Paper",
        authors=["Ada Researcher"],
        abstract="A test abstract about retrieval.",
        published="2024-01-03",
        categories=["cs.CL"],
        page_url="https://arxiv.org/abs/2401.01234",
        pdf_url="https://arxiv.org/pdf/2401.01234",
    )


class FakeSearchClient:
    async def search(
        self, topic: str, limit: int, category: str | None = None
    ) -> list[Paper]:
        assert topic == "retrieval"
        papers = [sample_paper()]
        if category:
            papers = [paper for paper in papers if category in paper.categories]
        return papers[:limit]


class FakeDownloader:
    def __init__(self, root: Path) -> None:
        self.root = root

    async def download(self, paper: Paper) -> DownloadedPdf:
        path = self.root / paper.source / f"{paper.paper_id}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        content = b"%PDF-1.7\nfixture"
        path.write_bytes(content)
        return DownloadedPdf(
            path=path,
            source_url=paper.pdf_url or "",
            size_bytes=len(content),
        )


async def test_catalog_search_download_and_classify(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    pdf_root = tmp_path / "pdfs"
    search = FakeSearchClient()
    catalog = PaperCatalog(
        library,
        pdf_root,
        arxiv=search,
        openalex=search,
        downloader=FakeDownloader(pdf_root),  # type: ignore[arg-type]
    )

    results = await catalog.search("retrieval", category="cs.CL", source="auto")
    imported = await catalog.download_to_collection(
        results[0].source,
        results[0].paper_id,
        collection_name="RAG 必读",
    )

    assert imported.collections == ["RAG 必读"]
    assert imported.download_id is not None
    resolved = catalog.resolve_download(imported.download_id)
    assert resolved is not None
    assert resolved[0].read_bytes().startswith(b"%PDF-")
    assert library.list_collections()[0].paper_count == 1
    library.close()


async def test_catalog_web_api_returns_local_download_link(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    manager = ResearchTaskManager(tmp_path / "reports", library=library)
    pdf_root = tmp_path / "pdfs"
    search = FakeSearchClient()
    catalog = PaperCatalog(
        library,
        pdf_root,
        arxiv=search,
        openalex=search,
        downloader=FakeDownloader(pdf_root),  # type: ignore[arg-type]
    )
    app = create_app(manager=manager, catalog=catalog)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/search/papers",
            params={"query": "retrieval", "source": "arxiv"},
        )
        assert response.status_code == 200
        assert response.json()["papers"][0]["paper_id"] == "2401.01234"

        imported = await client.post(
            "/api/library/import",
            json={
                "source": "arxiv",
                "paper_id": "2401.01234",
                "collection_name": "NLP",
            },
        )
        assert imported.status_code == 201
        assert imported.json()["collections"] == ["NLP"]

        downloaded = await client.get(imported.json()["local_download_url"])
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"] == "application/pdf"
        assert downloaded.content.startswith(b"%PDF-")

    library.close()


async def test_catalog_rejects_import_that_was_not_searched(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    catalog = PaperCatalog(library, tmp_path / "pdfs")

    try:
        await catalog.download_to_collection(
            "arxiv", "not-cached", collection_name="安全测试"
        )
    except KeyError as exc:
        assert "先搜索" in str(exc)
    else:
        raise AssertionError("uncached paper import should fail")
    library.close()
