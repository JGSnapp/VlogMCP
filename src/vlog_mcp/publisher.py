"""
Video publishing: Telegram Bot API.
"""

from __future__ import annotations

from pathlib import Path

import httpx


async def publish_telegram(
    video_path: Path,
    bot_token: str,
    chat_id: str,
    caption: str = "",
) -> dict:
    """
    Upload and send a video to a Telegram chat.
    Returns the Telegram API response dict.
    Raises RuntimeError on failure.
    """
    if not bot_token:
        raise RuntimeError("Telegram bot token not set (VLOG_MCP_TELEGRAM_TOKEN).")
    if not chat_id:
        raise RuntimeError("Telegram chat ID not set (VLOG_MCP_TELEGRAM_CHAT_ID).")
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                with video_path.open("rb") as f:
                    data = {"chat_id": chat_id, "caption": caption}
                    files = {"video": (video_path.name, f, "video/mp4")}
                    resp = await client.post(url, data=data, files=files)
                    resp.raise_for_status()
                    return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 413 and attempt == 1:
                raise RuntimeError(
                    f"Video too large for Telegram ({video_path.stat().st_size // 1024 // 1024} MB). "
                    "Telegram limit is 50 MB. Re-render with lower quality or compress first."
                )
            if attempt == max_attempts:
                raise RuntimeError(f"Telegram upload failed after {max_attempts} attempts: {exc}")
        except httpx.TimeoutException:
            if attempt == max_attempts:
                raise RuntimeError("Telegram upload timed out.")

    return {}
