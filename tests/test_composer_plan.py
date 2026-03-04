from vlog_mcp.composer import build_composition_plan


def test_build_composition_plan_supports_multiple_event_types(tmp_path):
    image = tmp_path / "img.png"
    audio = tmp_path / "tts.mp3"
    image.write_bytes(b"x")
    audio.write_bytes(b"y")

    assets = [
        {"asset_id": "a1", "path": str(image)},
        {"asset_id": "a2", "path": str(audio)},
    ]
    timeline = {
        "events": [
            {"type": "section", "at_seconds": 1, "payload": {"title": "Intro"}},
            {"type": "subtitle", "at_seconds": 2, "payload": {"text": "Hello", "end_seconds": 3}},
            {"type": "window_switched", "at_seconds": 3, "payload": {"window_name": "IDE"}},
            {"type": "code_snippet", "at_seconds": 4, "payload": {"code": "print('ok')"}},
            {"type": "code_diff", "at_seconds": 5, "payload": {}},
            {"type": "slide_image", "at_seconds": 6, "payload": {"asset_id": "a1"}},
            {"type": "tts", "at_seconds": 7, "payload": {"asset_id": "a2"}},
        ]
    }

    plan = build_composition_plan(timeline, assets=assets)
    assert len(plan["draw_filters"]) >= 5
    assert len(plan["image_overlays"]) == 1
    assert len(plan["audio_overlays"]) == 1
