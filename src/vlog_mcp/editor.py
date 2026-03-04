from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def trim_video(input_path: str, output_path: str, start: float, end: float) -> dict[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    duration = max(0.1, end - start)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(start),
        "-i",
        input_path,
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        output_path,
    ]
    subprocess.run(cmd, check=True)
    return {"operation": "trim", "output_path": output_path, "command": " ".join(cmd)}


def concat_videos(inputs: list[str], output_path: str, reencode: bool = False) -> dict[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    if not inputs:
        raise ValueError("inputs must not be empty")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output.parent / "concat_input.txt"
    concat_file.write_text("\n".join(f"file '{Path(x).resolve()}'" for x in inputs), encoding="utf-8")

    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]
    if reencode:
        cmd += ["-c:v", "libx264", "-c:a", "aac"]
    else:
        cmd += ["-c", "copy"]
    cmd += [output_path]

    subprocess.run(cmd, check=True)
    return {"operation": "concat", "output_path": output_path, "command": " ".join(cmd)}


def overlay_image(input_video: str, image_path: str, output_path: str, x: int = 20, y: int = 20) -> dict[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        input_video,
        "-i",
        image_path,
        "-filter_complex",
        f"overlay={x}:{y}",
        "-c:v",
        "libx264",
        "-c:a",
        "copy",
        output_path,
    ]
    subprocess.run(cmd, check=True)
    return {"operation": "overlay_image", "output_path": output_path, "command": " ".join(cmd)}
