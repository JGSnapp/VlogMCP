import pytest

from vlog_mcp.config import TokensConfig, VlogConfig
from vlog_mcp.providers import ImageService, TTSService


def test_config_masks_tokens():
    config = VlogConfig(tokens=TokensConfig(telegram_bot_token="t", openai_api_key="o", elevenlabs_api_key="e", stability_api_key="s"))
    data = config.to_dict()
    assert data["tokens"]["telegram_bot_token"] == "***"
    assert data["tokens"]["openai_api_key"] == "***"
    assert data["tokens"]["elevenlabs_api_key"] == "***"
    assert data["tokens"]["stability_api_key"] == "***"


def test_tts_unsupported_provider():
    service = TTSService("", "")
    with pytest.raises(ValueError):
        service.generate("unknown", "hello", "/tmp/out.mp3")


def test_image_unsupported_provider():
    service = ImageService("", "")
    with pytest.raises(ValueError):
        service.generate("unknown", "cat", "/tmp/img.png")
