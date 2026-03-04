from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


def build_render_job(session_dir: str, profile: str = "16:9", quality: str = "1080p") -> dict[str, Any]:
    root = Path(session_dir)
    output_name = f"final_{profile.replace(':', 'x')}_{quality}.mp4"
    output_path = root / "exports" / output_name

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(root / "timeline.concat.txt"),
        "-vf",
        "scale=1920:1080" if profile == "16:9" else "scale=1080:1920",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(output_path),
    ]

    return {
        "profile": profile,
        "quality": quality,
        "output": str(output_path),
        "concat_file": str(root / "timeline.concat.txt"),
        "ffmpeg_command": " ".join(ffmpeg_cmd),
    }


def write_concat_file(concat_path: str, media_files: list[str]) -> str:
    if not media_files:
        raise ValueError("media_files is empty")
    path = Path(concat_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"file '{Path(item).resolve()}'" for item in media_files]
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def execute_render_job(render_payload: dict[str, Any]) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    output = Path(render_payload["output"])
    output.parent.mkdir(parents=True, exist_ok=True)

    profile = render_payload["profile"]
    concat_file = render_payload["concat_file"]

    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_file,
        "-vf",
        "scale=1920:1080" if profile == "16:9" else "scale=1080:1920",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(output),
    ]
    subprocess.run(cmd, check=True)
    return {"output": str(output), "command": " ".join(cmd)}


def apply_branding(
    input_video: str,
    output_video: str,
    *,
    intro_clip: str = "",
    outro_clip: str = "",
    lower_third_text: str = "",
    primary_color: str = "#5B8DEF",
) -> dict[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    work = Path(output_video).parent
    work.mkdir(parents=True, exist_ok=True)

    branded_source = Path(input_video)
    if lower_third_text:
        lower_third_out = work / f"lower_third_{Path(input_video).name}"
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            input_video,
            "-vf",
            f"drawbox=x=20:y=h-110:w=w-40:h=80:color={primary_color}@0.55:t=fill,drawtext=text='{lower_third_text}':x=40:y=h-65:fontsize=30:fontcolor=white",
            "-c:v",
            "libx264",
            "-c:a",
            "copy",
            str(lower_third_out),
        ]
        subprocess.run(cmd, check=True)
        branded_source = lower_third_out

    clips: list[str] = []
    if intro_clip and Path(intro_clip).exists():
        clips.append(str(Path(intro_clip).resolve()))
    clips.append(str(branded_source.resolve()))
    if outro_clip and Path(outro_clip).exists():
        clips.append(str(Path(outro_clip).resolve()))

    if len(clips) == 1:
        Path(output_video).write_bytes(Path(clips[0]).read_bytes())
        return {"output": output_video, "command": "branding skipped (single clip)"}

    concat_file = work / "branding.concat.txt"
    concat_file.write_text("\n".join(f"file '{c}'" for c in clips), encoding="utf-8")

    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", output_video]
    subprocess.run(cmd, check=True)
    return {"output": output_video, "command": " ".join(cmd)}
