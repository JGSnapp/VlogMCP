"""
Screen recording via ffmpeg.
Manages running ffmpeg processes per project.
"""

from __future__ import annotations

import platform
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any


_processes: dict[str, subprocess.Popen] = {}   # project_id → process


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def get_capabilities() -> dict[str, Any]:
    """Return platform capabilities for screen recording."""
    os_name = platform.system()
    has_ffmpeg = _ffmpeg_available()

    if os_name == "Windows":
        backend = "gdigrab"
        audio_backend = "dshow"
        pause_resume = False
    elif os_name == "Darwin":
        backend = "avfoundation"
        audio_backend = "avfoundation"
        pause_resume = True
    else:
        backend = "x11grab"
        audio_backend = "pulse"
        pause_resume = True

    return {
        "platform": os_name,
        "ffmpeg_available": has_ffmpeg,
        "video_backend": backend,
        "audio_backend": audio_backend,
        "pause_resume_supported": pause_resume,
        "sources": ["desktop", "window:<title>", "region:<x,y,w,h>"],
    }


def _build_ffmpeg_cmd(
    output_path: Path,
    source: str,
    fps: int,
    with_audio: bool,
) -> list[str]:
    os_name = platform.system()
    cmd: list[str] = ["ffmpeg", "-y"]

    if os_name == "Windows":
        if source.startswith("window:"):
            title = source.split(":", 1)[1]
            cmd += ["-f", "gdigrab", "-framerate", str(fps), "-i", f"title={title}"]
        elif source.startswith("region:"):
            coords = source.split(":", 1)[1]   # x,y,w,h
            x, y, w, h = coords.split(",")
            cmd += ["-f", "gdigrab", "-framerate", str(fps),
                    "-offset_x", x, "-offset_y", y,
                    "-video_size", f"{w}x{h}", "-i", "desktop"]
        else:
            cmd += ["-f", "gdigrab", "-framerate", str(fps), "-i", "desktop"]
        if with_audio:
            cmd += ["-f", "dshow", "-i", "audio=virtual-audio-capturer"]

    elif os_name == "Darwin":
        cmd += ["-f", "avfoundation", "-framerate", str(fps),
                "-i", "1:0" if with_audio else "1:none"]

    else:   # Linux
        display = ":0"
        if source.startswith("region:"):
            coords = source.split(":", 1)[1]
            x, y, w, h = coords.split(",")
            cmd += ["-f", "x11grab", "-framerate", str(fps),
                    "-video_size", f"{w}x{h}", "-i", f"{display}+{x},{y}"]
        else:
            cmd += ["-f", "x11grab", "-framerate", str(fps), "-i", display]
        if with_audio:
            cmd += ["-f", "pulse", "-i", "default"]

    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k"]

    cmd.append(str(output_path))
    return cmd


def start(
    project_id: str,
    output_path: Path,
    source: str = "desktop",
    fps: int = 30,
    with_audio: bool = False,
) -> None:
    """Start screen recording. Raises if already recording or ffmpeg unavailable."""
    if project_id in _processes:
        raise RuntimeError(f"Recording already active for project '{project_id}'.")
    if not _ffmpeg_available():
        raise RuntimeError("ffmpeg not found in PATH. Install ffmpeg to record.")

    cmd = _build_ffmpeg_cmd(output_path, source, fps, with_audio)
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _processes[project_id] = proc


def pause(project_id: str) -> None:
    """Pause recording (SIGSTOP on Unix only)."""
    proc = _processes.get(project_id)
    if proc is None:
        raise RuntimeError(f"No active recording for project '{project_id}'.")
    if sys.platform == "win32":
        raise RuntimeError("Pause/resume is not supported on Windows.")
    proc.send_signal(signal.SIGSTOP)


def resume(project_id: str) -> None:
    """Resume paused recording (SIGCONT on Unix only)."""
    proc = _processes.get(project_id)
    if proc is None:
        raise RuntimeError(f"No active recording for project '{project_id}'.")
    if sys.platform == "win32":
        raise RuntimeError("Pause/resume is not supported on Windows.")
    proc.send_signal(signal.SIGCONT)


def stop(project_id: str) -> None:
    """Stop recording gracefully by sending 'q' to ffmpeg stdin."""
    proc = _processes.pop(project_id, None)
    if proc is None:
        raise RuntimeError(f"No active recording for project '{project_id}'.")
    try:
        proc.stdin.write(b"q")
        proc.stdin.flush()
        proc.wait(timeout=15)
    except Exception:
        proc.kill()


def is_recording(project_id: str) -> bool:
    return project_id in _processes
