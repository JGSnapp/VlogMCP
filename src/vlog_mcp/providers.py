from __future__ import annotations

import base64
import time
from pathlib import Path

import requests


def _post_with_retry(url: str, *, attempts: int = 3, backoff: float = 1.5, **kwargs):
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            response = requests.post(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            last_exc = exc
            if i < attempts - 1:
                time.sleep(backoff**i)
    assert last_exc is not None
    raise last_exc


class TTSService:
    def __init__(self, openai_key: str, elevenlabs_key: str):
        self.openai_key = openai_key
        self.elevenlabs_key = elevenlabs_key

    def generate(self, provider: str, text: str, output_path: str, voice: str = "alloy") -> dict[str, str]:
        if provider == "openai":
            return self._openai_tts(text, output_path, voice)
        if provider == "elevenlabs":
            return self._elevenlabs_tts(text, output_path, voice)
        raise ValueError(f"unsupported tts provider: {provider}")

    def _openai_tts(self, text: str, output_path: str, voice: str) -> dict[str, str]:
        if not self.openai_key:
            raise RuntimeError("OpenAI API key is not configured")
        response = _post_with_retry(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {self.openai_key}"},
            json={"model": "gpt-4o-mini-tts", "voice": voice, "input": text, "format": "mp3"},
            timeout=120,
        )
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return {"provider": "openai", "output_path": str(path)}

    def _elevenlabs_tts(self, text: str, output_path: str, voice: str) -> dict[str, str]:
        if not self.elevenlabs_key:
            raise RuntimeError("ElevenLabs API key is not configured")
        response = _post_with_retry(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            headers={"xi-api-key": self.elevenlabs_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_multilingual_v2"},
            timeout=120,
        )
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return {"provider": "elevenlabs", "output_path": str(path)}


class ImageService:
    def __init__(self, openai_key: str, stability_key: str):
        self.openai_key = openai_key
        self.stability_key = stability_key

    def generate(self, provider: str, prompt: str, output_path: str, size: str = "1024x1024") -> dict[str, str]:
        if provider == "openai":
            return self._openai_image(prompt, output_path, size)
        if provider == "stability":
            return self._stability_image(prompt, output_path)
        raise ValueError(f"unsupported image provider: {provider}")

    def _openai_image(self, prompt: str, output_path: str, size: str) -> dict[str, str]:
        if not self.openai_key:
            raise RuntimeError("OpenAI API key is not configured")
        response = _post_with_retry(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"},
            json={"model": "gpt-image-1", "prompt": prompt, "size": size},
            timeout=120,
        )
        payload = response.json()
        image_b64 = payload["data"][0]["b64_json"]
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(image_b64))
        return {"provider": "openai", "output_path": str(path)}

    def _stability_image(self, prompt: str, output_path: str) -> dict[str, str]:
        if not self.stability_key:
            raise RuntimeError("Stability API key is not configured")
        response = _post_with_retry(
            "https://api.stability.ai/v2beta/stable-image/generate/core",
            headers={"Authorization": f"Bearer {self.stability_key}", "Accept": "image/*"},
            files={"prompt": (None, prompt), "output_format": (None, "png")},
            timeout=120,
        )
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return {"provider": "stability", "output_path": str(path)}
