import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from paper_agent.interfaces.cli import build_parser, run_command
from paper_agent.services.research import ResearchService


class CliResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_uses_shared_service_and_retains_rag_output(self):
        with tempfile.TemporaryDirectory(prefix='paper_cli_test_') as tmp:
            root = Path(tmp)
            args = build_parser().parse_args([
                'run', '--topic', 'RAG', '--mode', 'demo', '--rag', 'abstract',
                '--decision', 'fixture', '--output-dir', str(root),
                '--rag-index', str(root / 'index.json'),
            ])
            original = ResearchService.run
            with patch.object(ResearchService, 'run', autospec=True, side_effect=original) as run:
                paths = await run_command(args)
            self.assertEqual(run.call_count, 1)
            report = json.loads(paths[1].read_text(encoding='utf-8'))
            self.assertEqual(len(report['context_audits']), 3)
            self.assertEqual(len(paths), 3)

    async def test_demo_rejects_remote_execution_options(self):
        with tempfile.TemporaryDirectory(prefix='paper_cli_test_') as tmp:
            args = build_parser().parse_args([
                'run', '--topic', 'RAG', '--mode', 'demo', '--rag', 'pdf',
                '--output-dir', tmp, '--rag-index', str(Path(tmp) / 'index.json'),
            ])
            with self.assertRaisesRegex(SystemExit, 'demo'):
                await run_command(args)

    async def test_cli_failure_exits_without_printing_private_cause(self):
        from paper_agent.core.errors import PublicResearchError

        async def fail(*args, **kwargs):
            try:
                raise RuntimeError('https://example.test?api_key=FAKE_SECRET')
            except RuntimeError as exc:
                raise PublicResearchError('search: RuntimeError') from exc

        args = build_parser().parse_args(['run', '--topic', 'RAG', '--mode', 'demo'])
        with patch.object(ResearchService, 'run', side_effect=fail):
            with self.assertRaises(SystemExit) as caught:
                await run_command(args)
        self.assertEqual(str(caught.exception), 'search: RuntimeError')
        self.assertTrue(caught.exception.__suppress_context__)


if __name__ == '__main__':
    unittest.main()
