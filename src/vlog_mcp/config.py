from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BrandingConfig:
    intro_clip: str = ""
    outro_clip: str = ""
    lower_third_template: str = "minimal"
    color_palette: dict[str, str] = field(default_factory=lambda: {"primary": "#5B8DEF", "accent": "#FF5F7E"})


@dataclass
class TokensConfig:
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    stability_api_key: str = ""


@dataclass
class ProvidersConfig:
    default_tts_provider: str = "openai"
    default_image_provider: str = "openai"


@dataclass
class VlogConfig:
    workspace_root: str = "./sessions"
    default_language: str = "ru"
    branding: BrandingConfig = field(default_factory=BrandingConfig)
    tokens: TokensConfig = field(default_factory=TokensConfig)
    providers: ProvidersConfig = field(default_factory=ProvidersConfig)
    media_library_paths: list[str] = field(default_factory=lambda: ["./libraries/memes", "./libraries/sfx"])

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "VlogConfig":
        branding = BrandingConfig(**raw.get("branding", {}))
        tokens = TokensConfig(**raw.get("tokens", {}))
        providers = ProvidersConfig(**raw.get("providers", {}))
        return cls(
            workspace_root=raw.get("workspace_root", "./sessions"),
            default_language=raw.get("default_language", "ru"),
            branding=branding,
            tokens=tokens,
            providers=providers,
            media_library_paths=raw.get("media_library_paths", ["./libraries/memes", "./libraries/sfx"]),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ["telegram_bot_token", "openai_api_key", "elevenlabs_api_key", "stability_api_key"]:
            data["tokens"][key] = "***" if data["tokens"].get(key) else ""
        return data


def _env_override(config: VlogConfig) -> VlogConfig:
    config.tokens.telegram_bot_token = os.getenv("VLOG_MCP_TELEGRAM_BOT_TOKEN", config.tokens.telegram_bot_token)
    config.tokens.telegram_chat_id = os.getenv("VLOG_MCP_TELEGRAM_CHAT_ID", config.tokens.telegram_chat_id)
    config.tokens.openai_api_key = os.getenv("VLOG_MCP_OPENAI_API_KEY", config.tokens.openai_api_key)
    config.tokens.elevenlabs_api_key = os.getenv("VLOG_MCP_ELEVENLABS_API_KEY", config.tokens.elevenlabs_api_key)
    config.tokens.stability_api_key = os.getenv("VLOG_MCP_STABILITY_API_KEY", config.tokens.stability_api_key)
    config.workspace_root = os.getenv("VLOG_MCP_WORKSPACE_ROOT", config.workspace_root)
    config.providers.default_tts_provider = os.getenv("VLOG_MCP_DEFAULT_TTS_PROVIDER", config.providers.default_tts_provider)
    config.providers.default_image_provider = os.getenv("VLOG_MCP_DEFAULT_IMAGE_PROVIDER", config.providers.default_image_provider)
    return config


def load_config(path: str | None = None) -> VlogConfig:
    config_path = Path(path or os.getenv("VLOG_MCP_CONFIG", "vlog-mcp.config.json"))
    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        return _env_override(VlogConfig.from_dict(raw))
    return _env_override(VlogConfig())
