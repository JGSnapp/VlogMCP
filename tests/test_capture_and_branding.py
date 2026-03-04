from pathlib import Path

from vlog_mcp.capture import ScreenRecorder
from vlog_mcp.renderer import apply_branding


def test_capture_capabilities_shape():
    recorder = ScreenRecorder()
    caps = recorder.list_capture_capabilities()
    assert "platform" in caps
    assert "backends" in caps
    assert isinstance(caps["supports_pause_resume"], bool)


def test_apply_branding_single_clip_copy(monkeypatch, tmp_path):
    src = tmp_path / "in.mp4"
    dst = tmp_path / "out.mp4"
    src.write_bytes(b"video")

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ffmpeg")

    def fail_run(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called when no intro/outro/lower-third")

    monkeypatch.setattr("subprocess.run", fail_run)

    result = apply_branding(str(src), str(dst), intro_clip="", outro_clip="", lower_third_text="")
    assert dst.read_bytes() == b"video"
    assert result["output"] == str(dst)
