"""Task-local model credentials; never change environment or SDK default keys."""
from __future__ import annotations

import asyncio
from typing import Literal
import httpx

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, AuthenticationError, PermissionDeniedError, RateLimitError
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr, field_validator

from paper_agent.core.errors import PublicResearchError

QWEN_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
OPENAI_URL = 'https://api.openai.com/v1'


class RuntimeCredentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider: Literal['qwen', 'openai']
    api_key: SecretStr = Field(repr=False)
    _clients: list = PrivateAttr(default_factory=list)

    @field_validator('api_key', mode='before')
    @classmethod
    def valid_key(cls, value):
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 4096 or any(ord(c) < 32 for c in value):
            raise ValueError('Invalid model credentials')
        return value.strip()


class ModelProbe(RuntimeCredentials):
    model: str = Field(min_length=1, max_length=128)

    @field_validator('model')
    @classmethod
    def model_not_blank(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('Invalid model name')
        return value.strip()


def require_personal_credentials(options) -> RuntimeCredentials:
    credentials = options.runtime_credentials
    if credentials is None or credentials.provider != options.provider:
        raise PublicResearchError('个人模型凭证不可用，请到“模型设置”重新配置并提交任务。')
    return credentials


def build_personal_model(options):
    """One explicit SDK client per task; the same client serves its specialist agents."""
    from agents import OpenAIChatCompletionsModel
    from paper_agent.agents.providers import DEFAULT_QWEN_MODEL, qwen_model_settings
    credentials = require_personal_credentials(options)
    client = AsyncOpenAI(api_key=credentials.api_key.get_secret_value(),
        base_url=QWEN_URL if credentials.provider == 'qwen' else OPENAI_URL,
        timeout=120.0, max_retries=1,
        http_client=httpx.AsyncClient(follow_redirects=False))
    credentials._clients.append(client)
    model = OpenAIChatCompletionsModel(
        model=options.model or (DEFAULT_QWEN_MODEL if credentials.provider == 'qwen' else 'gpt-5.6-luna'),
        openai_client=client, strict_feature_validation=True)
    return model, qwen_model_settings() if credentials.provider == 'qwen' else None


async def close_runtime_credentials(credentials: RuntimeCredentials | None):
    if credentials is not None:
        clients, credentials._clients = credentials._clients, []
        for client in clients:
            try:
                async with asyncio.timeout(5):
                    await client.close()
            except Exception:
                pass


async def probe_model(credentials: RuntimeCredentials, model: str) -> None:
    """A small billed completion; fixed origins, no redirects, bounded retry/output/time."""
    async with AsyncOpenAI(api_key=credentials.api_key.get_secret_value(),
        base_url=QWEN_URL if credentials.provider == 'qwen' else OPENAI_URL,
        timeout=12.0, max_retries=0,
        http_client=httpx.AsyncClient(follow_redirects=False)) as client:
        async with asyncio.timeout(15):
            response = await client.chat.completions.create(model=model,
                messages=[{'role': 'user', 'content': 'Reply with OK.'}],
                **({'max_tokens': 16, 'extra_body': {'enable_thinking': False}}
                   if credentials.provider == 'qwen' else {'max_completion_tokens': 16}))
            if not response.choices:
                raise PublicResearchError('模型没有返回有效响应，请检查模型名称与权限。')


def probe_error_message(error: Exception) -> str:
    # Never render the upstream body, request, exception string, or a supplied key.
    if isinstance(error, (AuthenticationError, PermissionDeniedError)):
        return '密钥无效或没有该模型的权限，请检查密钥及模型名称。'
    if isinstance(error, RateLimitError):
        return '模型请求受限或额度不足，请检查额度后稍后重试。'
    if isinstance(error, (TimeoutError, APITimeoutError, APIConnectionError)):
        return '连接模型服务超时或网络不可用，请稍后重试。'
    return '模型连接测试失败，请检查密钥、模型名称和账号权限。'
