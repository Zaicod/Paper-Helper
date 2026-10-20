import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openai import AsyncOpenAI

from paper_agent.services.model_routing import PROVIDERS, PersonalModelSettings
from paper_agent.storage.library import PaperLibrary


class PersonalModelOverrideTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="paper_model_override_")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.library = PaperLibrary.sqlite(root / "library.sqlite")
        self.addCleanup(self.library.close)
        self.user = self.library.create_user("learner", "learner@example.com", "unused")
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.settings = PersonalModelSettings(self.library, root / "settings.key")
        self.saved = {
            "analyst": ("qwen", "saved-analyst"),
            "synthesizer": ("openai", "saved-synthesizer"),
            "ideator": ("qwen", "saved-ideator"),
        }
        for role, (provider, model) in self.saved.items():
            self.settings.save_agent(self.user.id, role, provider, model)
        for provider in ("qwen", "openai"):
            self.settings.save_provider(
                self.user.id, provider, f"test-personal-{provider}",
                f"https://{provider}.example.com/v1",
            )

    def build_and_capture(self, **overrides):
        with patch.object(
            self.settings, "_resolve_model", wraps=self.settings._resolve_model
        ) as resolve, patch(
            "paper_agent.services.model_routing.AgentResearchTeam",
            side_effect=lambda **models: models,
        ) as team:
            result = self.settings.build_research_team(self.user.id, **overrides)
        assignments = [call.args[1] for call in resolve.call_args_list]
        self.assertEqual(
            [item.agent_role for item in assignments],
            ["analyst", "synthesizer", "ideator"],
        )
        team.assert_called_once()
        self.assertEqual(result["analyst_model"].model, assignments[0].model_name)
        self.assertEqual(result["synthesis_model"].model, assignments[1].model_name)
        self.assertEqual(result["ideator_model"].model, assignments[2].model_name)
        return {item.agent_role: (item.provider, item.model_name) for item in assignments}

    def test_no_override_preserves_saved_per_role_models(self):
        self.assertEqual(self.build_and_capture(), self.saved)

    def test_provider_and_model_override_all_roles_without_persisting(self):
        before = self.library.list_agent_model_settings(self.user.id)
        captured = self.build_and_capture(provider="openai", model_name="request-model")
        self.assertEqual(captured, {role: ("openai", "request-model") for role in self.saved})
        self.assertEqual(self.library.list_agent_model_settings(self.user.id), before)

    def test_provider_only_keeps_matching_model_and_defaults_changed_provider(self):
        captured = self.build_and_capture(provider="openai")
        self.assertEqual(captured, {
            "analyst": ("openai", PROVIDERS["openai"].models[0]),
            "synthesizer": ("openai", "saved-synthesizer"),
            "ideator": ("openai", PROVIDERS["openai"].models[0]),
        })

    def test_model_only_preserves_role_providers(self):
        captured = self.build_and_capture(model_name=" shared-model ")
        self.assertEqual(captured, {
            role: (provider, "shared-model")
            for role, (provider, _) in self.saved.items()
        })

    def test_requested_provider_uses_personal_credentials(self):
        with patch(
            "paper_agent.services.model_routing.AsyncOpenAI", wraps=AsyncOpenAI
        ) as client:
            self.build_and_capture(provider="openai", model_name="request-model")
        self.assertEqual(client.call_count, 3)
        for call in client.call_args_list:
            self.assertEqual(call.kwargs["api_key"], "test-personal-openai")
            self.assertEqual(call.kwargs["base_url"], "https://openai.example.com/v1")

    def test_unsupported_provider_is_rejected_before_model_construction(self):
        with patch.object(self.settings, "_resolve_model") as resolve:
            with self.assertRaisesRegex(ValueError, "unsupported provider"):
                self.settings.build_research_team(self.user.id, provider="unknown")
        resolve.assert_not_called()

    def test_blank_model_override_is_rejected(self):
        with patch.object(self.settings, "_resolve_model") as resolve:
            with self.assertRaises(ValueError):
                self.settings.build_research_team(self.user.id, model_name="   ")
        resolve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
