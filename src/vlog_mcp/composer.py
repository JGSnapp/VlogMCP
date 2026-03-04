from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any


IMAGE_EVENT_TYPES = {"screenshot", "slide_image", "generated_image", "media_insert"}
TEXT_EVENT_TYPES = {"section", "subtitle", "window_switched", "code_snippet", "code_diff"}


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _asset_map(assets: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    data = assets or []
    return {item.get("asset_id", ""): item for item in data if item.get("asset_id")}


def build_composition_plan(timeline: dict[str, Any], assets: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    events = timeline.get("events", [])
    amap = _asset_map(assets)

    draw_filters: list[str] = []
    image_overlays: list[dict[str, Any]] = []
    audio_overlays: list[dict[str, Any]] = []

    for event in events:
        et = event.get("type")
        at = float(event.get("at_seconds", 0))
        payload = event.get("payload", {})

        if et in TEXT_EVENT_TYPES:
            if et == "section":
                text = _esc(payload.get("title", ""))
                end = at + 4
                draw_filters.append(
                    f"drawtext=text='{text}':x=40:y=40:fontsize=38:fontcolor=white:enable='between(t,{at},{end})'"
                )
            elif et == "subtitle":
                text = _esc(payload.get("text", ""))
                end = float(payload.get("end_seconds", at + 2))
                draw_filters.append(
                    f"drawtext=text='{text}':x=(w-text_w)/2:y=h-120:fontsize=30:fontcolor=white:enable='between(t,{at},{end})'"
                )
            elif et == "window_switched":
                text = _esc(f"Window: {payload.get('window_name', '')}")
                draw_filters.append(
                    f"drawtext=text='{text}':x=40:y=90:fontsize=26:fontcolor=yellow:enable='between(t,{at},{at+3})'"
                )
            elif et == "code_snippet":
                code = payload.get("code", "")
                line = _esc(code.splitlines()[0][:80] if code else "code snippet")
                draw_filters.append(
                    f"drawtext=text='Code: {line}':x=40:y=h-180:fontsize=24:fontcolor=cyan:enable='between(t,{at},{at+4})'"
                )
            elif et == "code_diff":
                draw_filters.append(
                    f"drawtext=text='Code diff shown':x=40:y=h-220:fontsize=24:fontcolor=orange:enable='between(t,{at},{at+4})'"
                )

        asset_id = payload.get("asset_id", "")
        asset = amap.get(asset_id)
        if et in IMAGE_EVENT_TYPES and asset and Path(asset.get("path", "")).exists():
            image_overlays.append({
                "path": asset["path"],
                "start": at,
                "end": at + 4,
                "x": 20,
                "y": 20,
            })

        if et == "tts" and asset and Path(asset.get("path", "")).exists():
            audio_overlays.append({"path": asset["path"], "start": at})

    return {
        "draw_filters": draw_filters,
        "image_overlays": image_overlays,
        "audio_overlays": audio_overlays,
    }


def compose_with_timeline(
    input_video: str,
    timeline: dict[str, Any],
    output_video: str,
    assets: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    plan = build_composition_plan(timeline, assets=assets)
    output = Path(output_video)
    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [ffmpeg, "-y", "-i", input_video]
    for image in plan["image_overlays"]:
        cmd += ["-i", image["path"]]
    for audio in plan["audio_overlays"]:
        cmd += ["-i", audio["path"]]

    filter_parts: list[str] = []
    current_video = "[0:v]"

    if plan["draw_filters"]:
        draw_expr = ",".join(plan["draw_filters"])
        filter_parts.append(f"{current_video}{draw_expr}[vtxt]")
        current_video = "[vtxt]"

    img_count = len(plan["image_overlays"])
    for idx, image in enumerate(plan["image_overlays"], start=1):
        out_label = f"[vimg{idx}]"
        filter_parts.append(
            f"{current_video}[{idx}:v]overlay={image['x']}:{image['y']}:enable='between(t,{image['start']},{image['end']})'{out_label}"
        )
        current_video = out_label

    audio_count = len(plan["audio_overlays"])
    if audio_count:
        audio_labels = ["[0:a]"]
        for aidx, audio in enumerate(plan["audio_overlays"], start=1):
            input_index = 1 + img_count + (aidx - 1)
            label = f"[aud{aidx}]"
            ms = int(audio["start"] * 1000)
            filter_parts.append(f"[{input_index}:a]adelay={ms}|{ms}{label}")
            audio_labels.append(label)
        filter_parts.append(f"{''.join(audio_labels)}amix=inputs={len(audio_labels)}:duration=longest[aout]")

    if filter_parts:
        cmd += ["-filter_complex", ";".join(filter_parts), "-map", current_video]
        if audio_count:
            cmd += ["-map", "[aout]"]
        else:
            cmd += ["-map", "0:a?"]
        cmd += ["-c:v", "libx264", "-c:a", "aac", str(output)]
    else:
        cmd += ["-c:v", "libx264", "-c:a", "copy", str(output)]

    subprocess.run(cmd, check=True)
    return {"output": str(output), "command": " ".join(shlex.quote(x) for x in cmd)}
