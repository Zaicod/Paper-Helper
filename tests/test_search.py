from paper_agent.search import (
    ArxivSearchClient,
    FallbackSearchClient,
    OpenAlexSearchClient,
    SearchError,
    _restore_openalex_abstract,
)


ATOM_FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.01234v2</id>
    <published>2024-01-03T00:00:00Z</published>
    <title>  A Paper\nWith Spacing  </title>
    <summary>  An abstract\nwith useful evidence. </summary>
    <author><name>Alice</name></author>
    <author><name>Bob</name></author>
    <category term="cs.AI" />
    <link title="pdf" href="https://arxiv.org/pdf/2401.01234v2" />
  </entry>
</feed>
"""


def test_parse_arxiv_feed_into_domain_model() -> None:
    papers = ArxivSearchClient._parse_feed(ATOM_FIXTURE)

    assert len(papers) == 1
    assert papers[0].paper_id == "2401.01234v2"
    assert papers[0].title == "A Paper With Spacing"
    assert papers[0].authors == ["Alice", "Bob"]
    assert papers[0].categories == ["cs.AI"]
    assert papers[0].pdf_url == "https://arxiv.org/pdf/2401.01234v2"


async def test_fixture_search_filters_category_and_honors_limit() -> None:
    from paper_agent.search import FixtureSearchClient

    papers = await FixtureSearchClient().search("RAG", 1, "cs.CL")

    assert len(papers) == 1
    assert "cs.CL" in papers[0].categories


def test_restore_openalex_abstract_orders_inverted_positions() -> None:
    abstract = _restore_openalex_abstract(
        {"world": [1], "Hello": [0], "again": [2]}
    )

    assert abstract == "Hello world again"


def test_openalex_record_maps_to_paper() -> None:
    paper = OpenAlexSearchClient._to_paper(
        {
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.48550/arxiv.2401.01234",
            "display_name": "A Paper",
            "authorships": [{"author": {"display_name": "Alice"}}],
            "abstract_inverted_index": {"Useful": [0], "abstract": [1]},
            "publication_date": "2024-01-01",
            "primary_location": {
                "landing_page_url": "https://doi.org/example",
                "pdf_url": None,
            },
            "best_oa_location": {"pdf_url": "https://example.org/paper.pdf"},
            "open_access": {},
            "topics": [{"display_name": "Artificial Intelligence"}],
        }
    )

    assert paper.paper_id == "2401.01234"
    assert paper.source == "openalex"
    assert paper.abstract == "Useful abstract"
    assert paper.pdf_url == "https://example.org/paper.pdf"


async def test_fallback_search_uses_second_provider() -> None:
    class BrokenProvider:
        async def search(self, topic, limit, category=None):
            raise SearchError("timeout")

    class WorkingProvider:
        async def search(self, topic, limit, category=None):
            from paper_agent.search import FixtureSearchClient

            return await FixtureSearchClient().search(topic, limit, category)

    papers = await FallbackSearchClient(
        [BrokenProvider(), WorkingProvider()]
    ).search("RAG", 1)

    assert papers[0].paper_id == "demo-001"
