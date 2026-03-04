from vlog_mcp.planner import build_video_plan
from vlog_mcp.storage import SessionStore


def test_create_session_and_add_event(tmp_path):
    store = SessionStore(str(tmp_path / "sessions"))
    store.init_workspace()
    session = store.create_session("Test", "devlog")

    assert session["title"] == "Test"
    assert (tmp_path / "sessions" / session["session_id"] / "manifest.json").exists()


def test_plan_generation_contains_formats():
    plan = build_video_plan("bugfix-report", "Fix crash", "engineers", "youtube", include_vertical_variant=True)
    assert "16:9" in plan["formats"]
    assert "9:16" in plan["formats"]
    assert len(plan["sections"]) > 0
