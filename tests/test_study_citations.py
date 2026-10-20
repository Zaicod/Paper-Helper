"""Word citations are readable without changing the stored Agent evidence IDs."""
import io
import unittest
from docx import Document
from paper_agent.services.study import StudyService
from paper_agent.interfaces.study_document import render_study_document
from tests.test_study_report import FakeLoader, FakeTeam, memory_index, paper


class StudyCitationTests(unittest.IsolatedAsyncioTestCase):
    async def report(self, count=1):
        return await StudyService(loader=FakeLoader(), team=FakeTeam(), index=memory_index()).run(
            'Learning report', papers=[paper('p'+str(i+1)) for i in range(count)])

    def text(self, report):
        return '\n'.join(p.text for p in Document(io.BytesIO(render_study_document(report))).paragraphs)

    async def test_every_report_section_uses_readable_numbers_and_preserves_original_data(self):
        report = await self.report()
        marker = '[p1:p1:0]'
        item = report.analyses[0]
        item.overview = 'Overview '+marker
        item.background = 'Background '+marker
        item.methods[0].name = 'Module '+marker
        item.methods[0].purpose = 'Purpose '+marker
        item.methods[0].inputs = 'Input '+marker
        item.methods[0].outputs = 'Output '+marker
        item.innovations = ['Innovation '+marker]
        item.results = ['Result '+marker]
        item.reflection = ['Reflection '+marker]
        report.synthesis = ['Synthesis '+marker]
        report.learning_plan = ['Plan '+marker]
        before = report.model_dump_json()
        text = self.text(report)
        self.assertNotIn('p1:p1:0', text)
        self.assertIn('Overview [1]', text)
        self.assertIn('[1] 第 1 页', text)
        self.assertIn(paper().pdf_url, text)
        self.assertEqual(before, report.model_dump_json())

    async def test_multi_paper_numbers_are_global_and_compound_citations_are_readable(self):
        report = await self.report(2)
        report.analyses[0].overview = 'First [p1:p1:0]'
        report.analyses[1].overview = 'Second [p2:p1:0]'
        report.synthesis = ['Together [p1:p1:0, p2:p1:0] and [0, 1].']
        text = self.text(report)
        self.assertNotIn(':p1:0', text)
        self.assertIn('First [1]', text)
        self.assertIn('Second [2]', text)
        self.assertIn('Together [1, 2] and [0, 1].', text)

    async def test_unknown_or_foreign_ids_are_flagged_instead_of_fabricating_evidence(self):
        report = await self.report(2)
        report.analyses[0].results = ['Unknown [p1:p99:0:t0]; foreign [p2:p1:0].']
        text = self.text(report)
        self.assertNotIn('p1:p99:0:t0', text)
        self.assertIn('引用待核对', text)
        self.assertNotIn('Unknown [1]', text)
