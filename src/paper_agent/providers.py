from __future__ import annotations

from agents import ModelSettings, OpenAIChatCompletionsModel, set_tracing_disabled
from openai import AsyncOpenAI


DEFAULT_QWEN_MODEL = "qwen3.8-flash"
DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def build_qwen_model(
    api_key: str,
    model_name: str = DEFAULT_QWEN_MODEL,
    base_url: str = DEFAULT_QWEN_BASE_URL,
) -> OpenAIChatCompletionsModel:
    """Adapt DashScope's OpenAI-compatible Chat Completions API to Agents SDK."""

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    # Agents SDK tracing exports to OpenAI. Disable it when no OpenAI key is used.
    set_tracing_disabled(True)
    return OpenAIChatCompletionsModel(
        model=model_name,
        openai_client=client,
        strict_feature_validation=True,
    )


def qwen_model_settings() -> ModelSettings:
    """Use non-thinking mode to reduce tokens and stabilize JSON Schema output."""

    return ModelSettings(extra_body={"enable_thinking": False})

