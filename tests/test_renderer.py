from pathlib import Path

import pytest

from vlog_mcp.renderer import build_render_job, write_concat_file


def test_build_render_job_has_concat_file(tmp_path):
    payload = build_render_job(str(tmp_path), profile="16:9", quality="1080p")
    assert payload["concat_file"].endswith("timeline.concat.txt")
    assert payload["output"].endswith("final_16x9_1080p.mp4")


def test_write_concat_file(tmp_path):
    v1 = tmp_path / "a.mp4"
    v2 = tmp_path / "b.mp4"
    v1.write_bytes(b"1")
    v2.write_bytes(b"2")

    concat = write_concat_file(str(tmp_path / "timeline.concat.txt"), [str(v1), str(v2)])
    text = Path(concat).read_text(encoding="utf-8")
    assert "file '" in text
    assert str(v1.resolve()) in text


def test_write_concat_file_empty_raises(tmp_path):
    with pytest.raises(ValueError):
        write_concat_file(str(tmp_path / "timeline.concat.txt"), [])
