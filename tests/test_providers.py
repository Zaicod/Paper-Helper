from agents import OpenAIChatCompletionsModel

from paper_agent.providers import (
    DEFAULT_QWEN_BASE_URL,
    DEFAULT_QWEN_MODEL,
    build_qwen_model,
    qwen_model_settings,
)


def test_build_qwen_model_uses_chat_completions_adapter() -> None:
    model = build_qwen_model(api_key="test-key")

    assert isinstance(model, OpenAIChatCompletionsModel)
    assert model.model == DEFAULT_QWEN_MODEL
    assert str(model._client.base_url) == DEFAULT_QWEN_BASE_URL + "/"


def test_qwen_disables_thinking_mode() -> None:
    settings = qwen_model_settings()

    assert settings.extra_body == {"enable_thinking": False}
