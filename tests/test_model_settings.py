from pathlib import Path

from paper_agent.model_settings import PersonalModelSettings
from paper_agent.storage import PaperLibrary


def test_personal_model_settings_encrypt_keys_and_route_each_agent(
    tmp_path: Path, monkeypatch
) -> None:
    for name in ("DASHSCOPE_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    user = library.create_user("settings-user", "settings@example.com", "hash")
    service = PersonalModelSettings(library, tmp_path / "settings.key")

    initial = service.view(user.id)
    assert all(not provider.has_api_key for provider in initial.providers)

    service.save_provider(
        user.id,
        "qwen",
        "sk-personal-secret-1234",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    service.save_agent(user.id, "analyst", "qwen", "qwen3.8-flash")
    service.save_agent(
        user.id, "synthesizer", "qwen", "qwen3.7-plus-2026-05-26"
    )

    stored = library.get_provider_credential(user.id, "qwen")
    view = service.view(user.id)
    agents = {agent.agent_role: agent for agent in view.agents}

    assert stored is not None
    assert "sk-personal-secret-1234" not in stored.encrypted_api_key
    qwen = next(provider for provider in view.providers if provider.provider == "qwen")
    assert qwen.credential_source == "personal"
    assert qwen.api_key_hint is not None
    assert "personal-secret" not in qwen.api_key_hint
    assert agents["analyst"].model_name == "qwen3.8-flash"
    assert agents["synthesizer"].model_name == "qwen3.7-plus-2026-05-26"
    library.close()


def test_model_preset_is_scoped_to_one_user(tmp_path: Path) -> None:
    library = PaperLibrary.sqlite(tmp_path / "library.db")
    first = library.create_user("first-user", "first@example.com", "hash")
    second = library.create_user("second-user", "second@example.com", "hash")
    service = PersonalModelSettings(library, tmp_path / "settings.key")

    service.apply_preset(first.id, "quality")
    first_models = {item.model_name for item in service.view(first.id).agents}
    second_models = {item.model_name for item in service.view(second.id).agents}

    assert first_models == {"qwen3.8-max"}
    assert "qwen3.8-flash" in second_models
    library.close()
