from pathlib import Path

from paper_agent.context import ContextBuilder, estimate_tokens
from paper_agent.models import EvidenceChunk, Paper
from paper_agent.rag import (
    HashingEmbedder,
    OpenAICompatibleEmbedder,
    PaperRAG,
    VectorIndex,
)


def _paper(paper_id: str, abstract: str, pdf_url: str | None = None) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=["Author"],
        abstract=abstract,
        page_url=f"https://example.com/{paper_id}",
        pdf_url=pdf_url,
    )


async def test_vector_index_retrieves_relevant_paper() -> None:
    rag = PaperRAG(HashingEmbedder(), top_k_per_query=2)
    papers = [
        _paper("attention", "transformer attention sequence translation"),
        _paper("lora", "low rank adaptation freezes model weights"),
    ]
    await rag.index_papers(papers)

    packet = await rag.retrieve("low rank adaptation", top_k=1)

    assert packet.chunks[0].paper_id == "lora"


def test_context_builder_enforces_budget_and_records_drops() -> None:
    chunks = [
        EvidenceChunk(
            chunk_id=f"p:c{index}",
            paper_id="p",
            text="x" * 80,
            source_url="https://example.com/p",
            score=1 - index / 10,
        )
        for index in range(3)
    ]
    builder = ContextBuilder(token_budget=estimate_tokens(chunks[0].text), max_chunks=3)

    packet = builder.build("query", chunks)

    assert [item.chunk_id for item in packet.chunks] == ["p:c0"]
    assert packet.dropped_chunk_ids == ["p:c1", "p:c2"]
    assert packet.estimated_tokens <= packet.token_budget


async def test_pdf_failure_falls_back_to_abstract() -> None:
    class FailingPdfLoader:
        async def load(self, url: str):
            raise ValueError("broken pdf")

    paper = _paper(
        "fallback",
        "abstract evidence remains available",
        "https://example.com/paper.pdf",
    )
    rag = PaperRAG(
        HashingEmbedder(),
        include_pdfs=True,
        pdf_loader=FailingPdfLoader(),
    )

    await rag.index_papers([paper])
    packet = await rag.retrieve("abstract evidence", paper_id=paper.paper_id)

    assert rag.source_mode_for(paper.paper_id) == "abstract_fallback"
    assert packet.chunks


async def test_vector_index_can_be_saved_and_loaded(tmp_path: Path) -> None:
    chunk = EvidenceChunk(
        chunk_id="p:c0",
        paper_id="p",
        text="retrieval evidence",
        source_url="https://example.com/p",
    )
    path = tmp_path / "index.json"
    first = VectorIndex(HashingEmbedder())
    await first.add([chunk])
    first.save(path)
    second = VectorIndex(HashingEmbedder())
    second.load(path)

    results = await second.search("retrieval evidence", top_k=1)

    assert results[0].chunk_id == chunk.chunk_id


async def test_compatible_embedder_batches_provider_requests() -> None:
    class Item:
        def __init__(self, index: int, value: float) -> None:
            self.index = index
            self.embedding = [value]

    class EmbeddingsResource:
        def __init__(self) -> None:
            self.batch_sizes: list[int] = []

        async def create(self, model: str, input: list[str]):
            self.batch_sizes.append(len(input))
            return type(
                "Response",
                (),
                {"data": [Item(index, float(len(text))) for index, text in enumerate(input)]},
            )()

    resource = EmbeddingsResource()
    client = type("Client", (), {"embeddings": resource})()
    embedder = OpenAICompatibleEmbedder(client, "embedding-model", batch_size=2)

    vectors = await embedder.embed(["a", "bb", "ccc", "dddd", "eeeee"])

    assert resource.batch_sizes == [2, 2, 1]
    assert vectors == [[1.0], [2.0], [3.0], [4.0], [5.0]]
