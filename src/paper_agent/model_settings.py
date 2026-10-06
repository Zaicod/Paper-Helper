from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from agents import ModelSettings, OpenAIChatCompletionsModel, set_tracing_disabled
from cryptography.fernet import Fernet, InvalidToken
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from paper_agent.agent_team import AgentResearchTeam
from paper_agent.mindmap import ConfiguredMindMapAgent, MindMapGenerator
from paper_agent.storage import AgentModelSettingView, PaperLibrary


AgentRole = Literal["analyst", "synthesizer", "ideator", "mindmap"]
ProviderName = Literal["qwen", "openai", "deepseek"]


@dataclass(frozen=True)
class ProviderDefinition:
    provider: str
    label: str
    default_base_url: str
    env_key: str
    env_base_url: str
    models: tuple[str, ...]


PROVIDERS: dict[str, ProviderDefinition] = {
    "qwen": ProviderDefinition(
        provider="qwen",
        label="阿里云百炼 Qwen",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY",
        env_base_url="DASHSCOPE_BASE_URL",
        models=(
            "qwen3.8-flash",
            "qwen3.7-plus-2026-05-26",
            "qwen3.8-max",
        ),
    ),
    "openai": ProviderDefinition(
        provider="openai",
        label="OpenAI",
        default_base_url="https://api.openai.com/v1",
        env_key="OPENAI_API_KEY",
        env_base_url="OPENAI_BASE_URL",
        models=("gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"),
    ),
    "deepseek": ProviderDefinition(
        provider="deepseek",
        label="DeepSeek",
        default_base_url="https://api.deepseek.com/v1",
        env_key="DEEPSEEK_API_KEY",
        env_base_url="DEEPSEEK_BASE_URL",
        models=("deepseek-v4-flash", "deepseek-v4-pro"),
    ),
}

ROLE_LABELS = {
    "analyst": "文献分析员",
    "synthesizer": "文献总结员",
    "ideator": "研究构思员",
    "mindmap": "思维导图 Agent",
}

DEFAULT_ASSIGNMENTS: dict[str, tuple[str, str]] = {
    "analyst": ("qwen", "qwen3.8-flash"),
    "synthesizer": ("qwen", "qwen3.8-flash"),
    "ideator": ("qwen", "qwen3.7-plus-2026-05-26"),
    "mindmap": ("qwen", "qwen3.8-flash"),
}

PRESETS: dict[str, dict[str, tuple[str, str]]] = {
    "economy": {
        role: ("qwen", "qwen3.8-flash") for role in ROLE_LABELS
    },
    "balanced": {
        "analyst": ("qwen", "qwen3.8-flash"),
        "synthesizer": ("qwen", "qwen3.7-plus-2026-05-26"),
        "ideator": ("qwen", "qwen3.8-max"),
        "mindmap": ("qwen", "qwen3.8-flash"),
    },
    "quality": {
        role: ("qwen", "qwen3.8-max") for role in ROLE_LABELS
    },
}


class ProviderSettingPublic(BaseModel):
    provider: str
    label: str
    base_url: str
    has_api_key: bool
    api_key_hint: str | None = None
    credential_source: Literal["personal", "environment", "missing"]
    models: list[str]


class AgentSettingPublic(BaseModel):
    agent_role: str
    label: str
    provider: str
    model_name: str


class ModelSettingsView(BaseModel):
    providers: list[ProviderSettingPublic]
    agents: list[AgentSettingPublic]
    presets: dict[str, dict[str, dict[str, str]]]


class ProviderUpdate(BaseModel):
    api_key: str = Field(default="", max_length=1000)
    base_url: str | None = Field(default=None, max_length=2000)


class AgentSettingUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    model_name: str = Field(min_length=1, max_length=255)


class ModelConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedProvider:
    provider: str
    base_url: str
    api_key: str


@dataclass(frozen=True)
class ResolvedModel:
    model: OpenAIChatCompletionsModel
    settings: ModelSettings | None
    provider: str
    model_name: str


class SecretCipher:
    """Encrypt personal API keys; the encryption key never enters the DB."""

    def __init__(self, key_path: Path) -> None:
        configured = os.getenv("PAPER_AGENT_SETTINGS_KEY", "").strip()
        if configured:
            key = configured.encode("ascii")
        else:
            key_path = key_path.resolve()
            key_path.parent.mkdir(parents=True, exist_ok=True)
            if key_path.exists():
                key = key_path.read_bytes().strip()
            else:
                key = Fernet.generate_key()
                key_path.write_bytes(key)
        try:
            self._fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("PAPER_AGENT_SETTINGS_KEY 不是有效的 Fernet 密钥") from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ModelConfigurationError("个人 API Key 无法解密，请重新保存") from exc


class PersonalModelSettings:
    def __init__(self, library: PaperLibrary, key_path: Path) -> None:
        self.library = library
        self.cipher = SecretCipher(key_path)

    def view(self, user_id: int) -> ModelSettingsView:
        stored = {
            row.provider: row
            for row in self.library.list_provider_credentials(user_id)
        }
        assignments = self._assignments(user_id)
        providers: list[ProviderSettingPublic] = []
        for name, definition in PROVIDERS.items():
            credential = stored.get(name)
            env_key = os.getenv(definition.env_key, "").strip()
            if credential:
                source = "personal"
                hint = credential.api_key_hint
                base_url = credential.base_url
            elif env_key:
                source = "environment"
                hint = _mask_key(env_key)
                base_url = os.getenv(definition.env_base_url, "").strip() or definition.default_base_url
            else:
                source = "missing"
                hint = None
                base_url = definition.default_base_url
            providers.append(
                ProviderSettingPublic(
                    provider=name,
                    label=definition.label,
                    base_url=base_url,
                    has_api_key=source != "missing",
                    api_key_hint=hint,
                    credential_source=source,
                    models=list(definition.models),
                )
            )
        return ModelSettingsView(
            providers=providers,
            agents=[
                AgentSettingPublic(
                    agent_role=role,
                    label=ROLE_LABELS[role],
                    provider=assignments[role].provider,
                    model_name=assignments[role].model_name,
                )
                for role in ROLE_LABELS
            ],
            presets={
                preset: {
                    role: {"provider": provider, "model_name": model}
                    for role, (provider, model) in values.items()
                }
                for preset, values in PRESETS.items()
            },
        )

    def save_provider(
        self, user_id: int, provider: str, api_key: str, base_url: str | None
    ) -> None:
        definition = self._provider_definition(provider)
        current = self.library.get_provider_credential(user_id, provider)
        clean_key = api_key.strip()
        if not clean_key and current is None:
            raise ValueError("首次保存 Provider 时必须填写 API Key")
        encrypted = (
            self.cipher.encrypt(clean_key)
            if clean_key
            else current.encrypted_api_key
        )
        hint = _mask_key(clean_key) if clean_key else current.api_key_hint
        clean_base = (base_url or "").strip() or (
            current.base_url if current else definition.default_base_url
        )
        if not clean_base.startswith("https://"):
            raise ValueError("Base URL 必须使用 https://")
        self.library.save_provider_credential(
            user_id, provider, clean_base.rstrip("/"), encrypted, hint
        )

    def delete_provider(self, user_id: int, provider: str) -> bool:
        self._provider_definition(provider)
        return self.library.delete_provider_credential(user_id, provider)

    def save_agent(
        self, user_id: int, role: str, provider: str, model_name: str
    ) -> AgentModelSettingView:
        self._validate_role(role)
        self._provider_definition(provider)
        clean_model = model_name.strip()
        if not clean_model:
            raise ValueError("模型 ID 不能为空")
        return self.library.save_agent_model_setting(
            user_id, role, provider, clean_model
        )

    def apply_preset(self, user_id: int, preset: str) -> None:
        if preset not in PRESETS:
            raise ValueError("unknown model preset")
        for role, (provider, model) in PRESETS[preset].items():
            self.save_agent(user_id, role, provider, model)

    def build_research_team(self, user_id: int) -> AgentResearchTeam:
        assignments = self._assignments(user_id)
        analyst = self._resolve_model(user_id, assignments["analyst"])
        synthesizer = self._resolve_model(user_id, assignments["synthesizer"])
        ideator = self._resolve_model(user_id, assignments["ideator"])
        return AgentResearchTeam(
            basemodel=analyst.model,
            analyst_model=analyst.model,
            synthesis_model=synthesizer.model,
            ideator_model=ideator.model,
            analyst_settings=analyst.settings,
            synthesis_settings=synthesizer.settings,
            ideator_settings=ideator.settings,
        )

    def build_mind_map_agent(self, user_id: int) -> MindMapGenerator:
        assignment = self._assignments(user_id)["mindmap"]
        resolved = self._resolve_model(user_id, assignment)
        return ConfiguredMindMapAgent(
            resolved.model,
            resolved.settings,
            f"{resolved.provider}:{resolved.model_name}",
        )

    def _assignments(self, user_id: int) -> dict[str, AgentModelSettingView]:
        stored = {
            row.agent_role: row
            for row in self.library.list_agent_model_settings(user_id)
            if row.agent_role in ROLE_LABELS
        }
        now = datetime.now()
        return {
            role: stored.get(role)
            or AgentModelSettingView(
                agent_role=role,
                provider=DEFAULT_ASSIGNMENTS[role][0],
                model_name=DEFAULT_ASSIGNMENTS[role][1],
                updated_at=now,
            )
            for role in ROLE_LABELS
        }

    def _resolve_model(
        self, user_id: int, assignment: AgentModelSettingView
    ) -> ResolvedModel:
        credential = self._resolve_provider(user_id, assignment.provider)
        client = AsyncOpenAI(
            api_key=credential.api_key,
            base_url=credential.base_url,
        )
        set_tracing_disabled(True)
        model = OpenAIChatCompletionsModel(
            model=assignment.model_name,
            openai_client=client,
            strict_feature_validation=False,
        )
        settings = (
            ModelSettings(extra_body={"enable_thinking": False})
            if assignment.provider == "qwen"
            else None
        )
        return ResolvedModel(
            model=model,
            settings=settings,
            provider=assignment.provider,
            model_name=assignment.model_name,
        )

    def _resolve_provider(self, user_id: int, provider: str) -> ResolvedProvider:
        definition = self._provider_definition(provider)
        stored = self.library.get_provider_credential(user_id, provider)
        if stored is not None:
            return ResolvedProvider(
                provider=provider,
                base_url=stored.base_url,
                api_key=self.cipher.decrypt(stored.encrypted_api_key),
            )
        env_key = os.getenv(definition.env_key, "").strip()
        if not env_key:
            raise ModelConfigurationError(
                f"{definition.label} 尚未配置 API Key，请先进入个人设置"
            )
        return ResolvedProvider(
            provider=provider,
            base_url=os.getenv(definition.env_base_url, "").strip()
            or definition.default_base_url,
            api_key=env_key,
        )

    @staticmethod
    def _provider_definition(provider: str) -> ProviderDefinition:
        try:
            return PROVIDERS[provider]
        except KeyError as exc:
            raise ValueError("unsupported provider") from exc

    @staticmethod
    def _validate_role(role: str) -> None:
        if role not in ROLE_LABELS:
            raise ValueError("unsupported agent role")


def _mask_key(value: str) -> str:
    if len(value) <= 8:
        return "••••" + value[-2:]
    return f"{value[:3]}••••{value[-4:]}"
