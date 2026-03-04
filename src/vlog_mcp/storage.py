from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import AssetRecord, SessionManifest, TimelineEvent, new_id, utc_now


class SessionStore:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def init_workspace(self) -> dict[str, Any]:
        folders = [
            self.root,
            self.root / "exports",
            self.root / "libraries",
            self.root / "templates",
        ]
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
        return {"workspace": str(self.root), "folders": [str(x) for x in folders]}

    def _session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def _path(self, session_id: str, name: str) -> Path:
        return self._session_dir(session_id) / name

    def create_session(self, title: str, kind: str, tags: list[str] | None = None) -> dict[str, Any]:
        session = SessionManifest(session_id=new_id("session"), title=title, kind=kind, tags=tags or [])
        session_dir = self._session_dir(session.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "captures").mkdir(exist_ok=True)
        (session_dir / "images").mkdir(exist_ok=True)
        (session_dir / "audio").mkdir(exist_ok=True)
        (session_dir / "exports").mkdir(exist_ok=True)
        (session_dir / "slides").mkdir(exist_ok=True)

        self._write_json(self._path(session.session_id, "manifest.json"), session.to_dict())
        self._write_json(self._path(session.session_id, "timeline.json"), {"events": []})
        self._write_json(self._path(session.session_id, "assets.json"), {"assets": []})
        self._write_json(self._path(session.session_id, "plan.json"), {"plan": {}, "updated_at": utc_now()})
        self._write_json(self._path(session.session_id, "jobs.json"), {"jobs": []})
        return session.to_dict()

    def list_sessions(self, status: str | None = None) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for manifest in self.root.glob("session_*/manifest.json"):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if status and data.get("status") != status:
                continue
            sessions.append(data)
        sessions.sort(key=lambda x: x["created_at"], reverse=True)
        return sessions

    def load_manifest(self, session_id: str) -> dict[str, Any]:
        return self._read_json(self._path(session_id, "manifest.json"))

    def update_manifest(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        manifest = self.load_manifest(session_id)
        manifest.update(updates)
        manifest["updated_at"] = utc_now()
        self._write_json(self._path(session_id, "manifest.json"), manifest)
        return manifest

    def load_timeline(self, session_id: str) -> dict[str, Any]:
        return self._read_json(self._path(session_id, "timeline.json"))

    def append_event(self, session_id: str, event: TimelineEvent) -> dict[str, Any]:
        timeline = self.load_timeline(session_id)
        timeline.setdefault("events", []).append(event.to_dict())
        self._write_json(self._path(session_id, "timeline.json"), timeline)
        return event.to_dict()

    def update_event(self, session_id: str, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        timeline = self.load_timeline(session_id)
        for event in timeline.get("events", []):
            if event["event_id"] == event_id:
                event["payload"].update(payload)
                self._write_json(self._path(session_id, "timeline.json"), timeline)
                return event
        raise ValueError(f"event {event_id} not found")

    def add_asset(self, session_id: str, asset: AssetRecord) -> dict[str, Any]:
        payload = self._read_json(self._path(session_id, "assets.json"))
        payload.setdefault("assets", []).append(asset.to_dict())
        self._write_json(self._path(session_id, "assets.json"), payload)
        return asset.to_dict()

    def list_assets(self, session_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        assets = self._read_json(self._path(session_id, "assets.json")).get("assets", [])
        if kind:
            assets = [asset for asset in assets if asset.get("kind") == kind]
        return assets

    def save_plan(self, session_id: str, plan: dict[str, Any]) -> dict[str, Any]:
        payload = {"plan": plan, "updated_at": utc_now()}
        self._write_json(self._path(session_id, "plan.json"), payload)
        return payload

    def add_job(self, session_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        jobs = self._read_json(self._path(session_id, "jobs.json"))
        item = {
            "job_id": new_id("job"),
            "kind": kind,
            "payload": payload,
            "status": "queued",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "attempts": 0,
            "last_error": "",
        }
        jobs.setdefault("jobs", []).append(item)
        self._write_json(self._path(session_id, "jobs.json"), jobs)
        return item

    def list_jobs(self, session_id: str, status: str | None = None) -> list[dict[str, Any]]:
        jobs = self._read_json(self._path(session_id, "jobs.json")).get("jobs", [])
        if status:
            jobs = [j for j in jobs if j.get("status") == status]
        return jobs

    def update_job(self, session_id: str, job_id: str, **updates: Any) -> dict[str, Any]:
        payload = self._read_json(self._path(session_id, "jobs.json"))
        for job in payload.get("jobs", []):
            if job.get("job_id") == job_id:
                job.update(updates)
                job["updated_at"] = utc_now()
                self._write_json(self._path(session_id, "jobs.json"), payload)
                return job
        raise ValueError(f"job {job_id} not found")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
