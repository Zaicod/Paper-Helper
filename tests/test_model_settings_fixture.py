"""The isolated browser boundary must reject lost or crossed credentials."""
import unittest
from types import SimpleNamespace
from pydantic import SecretStr

from scripts import paper_search_fixture as fixture


class ModelSettingsFixtureTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_rejects_wrong_provider_key_without_echoing_it(self):
        bad = 'wrong-sensitive-value'
        credentials = SimpleNamespace(provider='qwen', api_key=SecretStr(bad))
        with self.assertRaisesRegex(ValueError, 'Controlled model credentials mismatch') as caught:
            await fixture.controlled_model_test(credentials, 'fixture-qwen-updated')
        self.assertNotIn(bad, str(caught.exception))

    async def test_probe_accepts_saved_fake_key(self):
        credentials = SimpleNamespace(provider='openai', api_key=SecretStr('fixture-personal-openai-5678'))
        await fixture.controlled_model_test(credentials, 'fixture-openai-updated')

    def test_study_factory_rejects_personal_task_without_credential(self):
        options = SimpleNamespace(credential_source='personal', runtime_credentials=None, provider='openai', model='fixture-openai-updated')
        with self.assertRaisesRegex(ValueError, 'Controlled model credentials mismatch'):
            fixture.controlled_study_factory(options)

    def test_study_factory_checks_selected_provider_and_model(self):
        from paper_agent.services.research import ResearchOptions
        from paper_agent.services.model_runtime import RuntimeCredentials
        options = ResearchOptions(mode='live', provider='openai', model='fixture-openai-updated',
                                  credential_source='personal', runtime_credentials=RuntimeCredentials(provider='openai', api_key='fixture-personal-openai-5678'))
        self.assertEqual(fixture.controlled_study_factory(options).options.provider, 'openai')

