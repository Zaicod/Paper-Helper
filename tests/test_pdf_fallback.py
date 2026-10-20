"""Offline coverage for isolating unreadable PDF evidence to one paper."""

import unittest

from pypdf.errors import FileNotDecryptedError, ParseError, PdfReadError, PdfStreamError

from paper_agent.agents.demo import DemoResearchTeam
from paper_agent.core.models import Paper
from paper_agent.tools.rag import HashingEmbedder, PaperRAG
from paper_agent.workflows.research import ResearchWorkflow


def sample_papers():
    return [
        Paper(
            paper_id=f"pdf-{index}",
            title=f"Research evidence {index}",
            authors=["Fixture Researcher"],
            abstract=f"Abstract evidence for paper {index}: research method and results.",
            page_url=f"https://example.test/papers/{index}",
            pdf_url=f"https://example.test/papers/{index}.pdf",
        )
        for index in range(3)
    ]


class OfflineSearch:
    async def search(self, topic, limit, category=None):
        return sample_papers()[:limit]


class SelectivePdfLoader:
    def __init__(self, failure):
        self.failure = failure
        self.calls = []

    async def load(self, url):
        self.calls.append(url)
        if url.endswith("/0.pdf"):
            raise self.failure
        return [(1, "Full text research problem, method, experiment results and limitations.")]


class PdfFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_parser_failure_falls_back_without_interrupting_other_papers(self):
        for error_type in (PdfReadError, ParseError, PdfStreamError, FileNotDecryptedError):
            with self.subTest(error=error_type.__name__):
                loader = SelectivePdfLoader(error_type("Unreadable fixture PDF"))
                evidence = PaperRAG(HashingEmbedder(), include_pdfs=True, pdf_loader=loader)
                workflow = ResearchWorkflow(OfflineSearch(), DemoResearchTeam(), evidence=evidence)

                try:
                    report = await workflow.run("RAG evidence", limit=3)
                except Exception as exc:
                    self.fail(f"One unreadable PDF interrupted the entire workflow: {exc!r}")

                self.assertEqual(len(loader.calls), 3)
                self.assertEqual(len(report.analyses), 3)
                self.assertEqual(report.analysis_failures, [])
                self.assertEqual(
                    {audit.paper_id: audit.source_mode for audit in report.context_audits},
                    {"pdf-0": "abstract_fallback", "pdf-1": "pdf", "pdf-2": "pdf"},
                )
                fallback = await evidence.retrieve("Abstract evidence", paper_id="pdf-0")
                self.assertTrue(fallback.chunks)
                self.assertTrue(all(chunk.page_number is None for chunk in fallback.chunks))
                self.assertTrue(all("Abstract evidence" in chunk.text for chunk in fallback.chunks))

    async def test_unexpected_loader_programming_error_remains_visible(self):
        evidence = PaperRAG(
            HashingEmbedder(), include_pdfs=True,
            pdf_loader=SelectivePdfLoader(TypeError("Fixture programming mistake")),
        )
        with self.assertRaisesRegex(TypeError, "Fixture programming mistake"):
            await evidence.index_papers(sample_papers())


if __name__ == "__main__":
    unittest.main()
