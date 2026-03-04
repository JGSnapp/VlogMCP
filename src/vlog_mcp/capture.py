from __future__ import annotations

import platform
import re
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any


class ScreenRecorder:
    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen] = {}

    @staticmethod
    def _ffmpeg_path() -> str:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg not found")
        return ffmpeg

    def list_capture_capabilities(self) -> dict[str, Any]:
        system = platform.system().lower()
        payload: dict[str, Any] = {
            "platform": system,
            "ffmpeg_available": bool(shutil.which("ffmpeg")),
            "backends": [],
            "supports_pause_resume": True,
            "notes": [],
        }
        if system == "windows":
            payload["backends"] = ["gdigrab", "dshow"]
            payload["notes"].append("window capture uses gdigrab title=<window>")
        elif system == "darwin":
            payload["backends"] = ["avfoundation"]
            payload["notes"].append("audio device selection for avfoundation may require manual ffmpeg index mapping")
        else:
            payload["backends"] = ["x11grab", "pulse"]
            payload["notes"].append("X11 DISPLAY is required for screen capture")
        return payload

    def list_capture_devices(self) -> dict[str, list[str]]:
        ffmpeg = self._ffmpeg_path()
        system = platform.system().lower()

        cmd: list[str]
        if system == "windows":
            cmd = [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
        elif system == "darwin":
            cmd = [ffmpeg, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""]
        else:
            cmd = [ffmpeg, "-hide_banner", "-sources", "x11grab"]

        process = subprocess.run(cmd, capture_output=True, text=True)
        output = (process.stdout or "") + "\n" + (process.stderr or "")

        devices = []
        for line in output.splitlines():
            if "[" in line and "]" in line and any(x in line.lower() for x in ["device", "screen", "audio", "video"]):
                devices.append(line.strip())

        # fallback parser for quoted dshow/avfoundation names
        if not devices:
            devices = [m.group(1) for m in re.finditer(r'"([^"]+)"', output)]

        return {"raw": output.splitlines()[-120:], "devices": devices}

    def start(
        self,
        session_id: str,
        output_path: str,
        fps: int = 30,
        display: str = ":0.0",
        region: dict | None = None,
        window_title: str | None = None,
        with_audio: bool = False,
    ) -> dict[str, str]:
        ffmpeg = self._ffmpeg_path()

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        system = platform.system().lower()
        if system == "windows":
            grab_input = "desktop" if not window_title else f"title={window_title}"
            cmd = [ffmpeg, "-y", "-f", "gdigrab", "-framerate", str(fps), "-i", grab_input]
            if with_audio:
                cmd += ["-f", "dshow", "-i", "audio=virtual-audio-capturer"]
        elif system == "darwin":
            cmd = [ffmpeg, "-y", "-f", "avfoundation", "-framerate", str(fps), "-i", "1:none"]
        else:
            cmd = [ffmpeg, "-y", "-f", "x11grab", "-framerate", str(fps), "-i", display]
            if with_audio:
                cmd += ["-f", "pulse", "-i", "default"]

        if region and system in {"linux", "windows"}:
            w = int(region.get("width", 0))
            h = int(region.get("height", 0))
            x = int(region.get("x", 0))
            y = int(region.get("y", 0))
            if w > 0 and h > 0:
                if system == "windows":
                    cmd += ["-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}"]
                else:
                    cmd[cmd.index(display)] = f"{display}+{x},{y}"
                    cmd += ["-video_size", f"{w}x{h}"]

        cmd += ["-pix_fmt", "yuv420p", str(output)]

        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._processes[session_id] = process
        return {
            "session_id": session_id,
            "output_path": str(output),
            "pid": str(process.pid),
            "command": " ".join(cmd),
        }

    def pause(self, session_id: str) -> dict[str, str]:
        process = self._processes.get(session_id)
        if not process:
            raise ValueError(f"recorder for session {session_id} not running")

        # ffmpeg interactive command toggles pause cross-platform when stdin is attached
        if not process.stdin:
            raise RuntimeError("recorder stdin is not available")
        process.stdin.write(b"p")
        process.stdin.flush()
        return {"session_id": session_id, "status": "paused"}

    def resume(self, session_id: str) -> dict[str, str]:
        process = self._processes.get(session_id)
        if not process:
            raise ValueError(f"recorder for session {session_id} not running")

        if not process.stdin:
            raise RuntimeError("recorder stdin is not available")
        process.stdin.write(b"p")
        process.stdin.flush()
        return {"session_id": session_id, "status": "resumed"}

    def stop(self, session_id: str) -> dict[str, str]:
        process = self._processes.pop(session_id, None)
        if not process:
            raise ValueError(f"recorder for session {session_id} not running")

        try:
            if process.stdin:
                process.stdin.write(b"q")
                process.stdin.flush()
        except Exception:
            pass

        try:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
        except Exception:
            process.terminate()
            process.wait(timeout=10)

        return {"session_id": session_id, "status": "stopped", "returncode": str(process.returncode)}
