from pathlib import Path

from vlog_mcp.slides import render_slide_to_image
from vlog_mcp.storage import SessionStore
from vlog_mcp.worker import JobWorker


def test_slide_renderer_creates_png(tmp_path):
    md = tmp_path / "slide.md"
    md.write_text("# Title\n- Bullet", encoding="utf-8")
    out = tmp_path / "slide.png"
    path = render_slide_to_image(str(md), str(out))
    assert Path(path).exists()


def test_worker_handles_missing_handler(tmp_path):
    store = SessionStore(str(tmp_path / "sessions"))
    session = store.create_session("x", "devlog")
    store.add_job(session["session_id"], "unknown.job", {"k": "v"})

    worker = JobWorker(store)
    result = worker.run_pending(session["session_id"])
    assert result[0]["status"] == "failed"


def test_worker_executes_handler(tmp_path):
    store = SessionStore(str(tmp_path / "sessions"))
    session = store.create_session("x", "devlog")
    job = store.add_job(session["session_id"], "ok.job", {"v": 1})

    worker = JobWorker(store)
    worker.register("ok.job", lambda j: {"done": j["payload"]["v"]})
    result = worker.run_pending(session["session_id"])
    assert result[0]["job_id"] == job["job_id"]
    assert result[0]["status"] == "completed"


def test_worker_run_daemon(tmp_path):
    store = SessionStore(str(tmp_path / "sessions"))
    session = store.create_session("x", "devlog")
    store.add_job(session["session_id"], "ok.job", {"v": 1})

    worker = JobWorker(store)
    worker.register("ok.job", lambda j: {"done": j["payload"]["v"]})
    result = worker.run_daemon(session["session_id"], interval_sec=0.01, max_cycles=2, per_cycle_limit=5)
    assert result and result[0]["status"] == "completed"
