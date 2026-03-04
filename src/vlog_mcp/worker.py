from __future__ import annotations

import time
from typing import Any, Callable

from .observability import log_event
from .storage import SessionStore

JobHandler = Callable[[dict[str, Any]], dict[str, Any]]


class JobWorker:
    def __init__(self, store: SessionStore):
        self.store = store
        self.handlers: dict[str, JobHandler] = {}

    def register(self, kind: str, handler: JobHandler) -> None:
        self.handlers[kind] = handler

    def run_pending(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        queued = self.store.list_jobs(session_id, status="queued")[:limit]
        results: list[dict[str, Any]] = []
        for job in queued:
            job_id = job["job_id"]
            kind = job["kind"]
            handler = self.handlers.get(kind)
            if not handler:
                updated = self.store.update_job(session_id, job_id, status="failed", last_error=f"no handler for {kind}")
                results.append(updated)
                continue

            self.store.update_job(session_id, job_id, status="in_progress", attempts=job.get("attempts", 0) + 1)
            try:
                out = handler(job)
                updated = self.store.update_job(session_id, job_id, status="completed", result=out, last_error="")
                log_event("job.completed", session_id=session_id, job_id=job_id, kind=kind)
                results.append(updated)
            except Exception as exc:
                updated = self.store.update_job(session_id, job_id, status="failed", last_error=str(exc))
                log_event("job.failed", session_id=session_id, job_id=job_id, kind=kind, error=str(exc))
                results.append(updated)
        return results

    def run_daemon(self, session_id: str, *, interval_sec: float = 2.0, max_cycles: int = 30, per_cycle_limit: int = 20) -> list[dict[str, Any]]:
        handled: list[dict[str, Any]] = []
        for _ in range(max_cycles):
            batch = self.run_pending(session_id, limit=per_cycle_limit)
            handled.extend(batch)
            if not self.store.list_jobs(session_id, status="queued"):
                break
            time.sleep(interval_sec)
        return handled
