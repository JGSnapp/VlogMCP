from __future__ import annotations

import time
from pathlib import Path

import requests


def send_video(bot_token: str, chat_id: str, video_path: str, caption: str = "", attempts: int = 3) -> dict:
    if not bot_token:
        raise RuntimeError("Telegram bot token is not configured")
    if not chat_id:
        raise RuntimeError("Telegram chat id is not configured")

    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"video not found: {video_path}")

    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            with path.open("rb") as f:
                response = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption},
                    files={"video": (path.name, f, "video/mp4")},
                    timeout=300,
                )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_exc = exc
            if i < attempts - 1:
                time.sleep(1.5**i)
    assert last_exc is not None
    raise last_exc
