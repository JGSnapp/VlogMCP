"""
JSON-based persistence layer.
Each project has its own directory with:
  project.json   – manifest
  event_log.jsonl – append-only recording events
  timeline.json  – composition timeline
  assets.json    – asset registry
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    Asset, EventLogEntry, Project,
    new_id, now_ts,
)


class ProjectStorage:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        workspace.mkdir(parents=True, exist_ok=True)

    # ── private helpers ───────────────────────────────────────────────────────

    def _project_dir(self, project_id: str) -> Path:
        return self.workspace / "projects" / project_id

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _assets_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "assets.json"

    def _timeline_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "timeline.json"

    def _event_log_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "event_log.jsonl"

    def _project_manifest_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "project.json"

    # ── project ───────────────────────────────────────────────────────────────

    def create_project(self, name: str) -> Project:
        project_id = new_id("proj")
        proj_dir = self._project_dir(project_id)
        proj_dir.mkdir(parents=True, exist_ok=True)

        # sub-directories
        for sub in ("captures", "screenshots", "audio", "generated", "exports"):
            (proj_dir / sub).mkdir(exist_ok=True)

        ts = now_ts()
        project = Project(
            project_id=project_id,
            name=name,
            status="created",
            branding_id="default",
            created_at=ts,
            updated_at=ts,
            dir=str(proj_dir),
        )
        self._write_json(self._project_manifest_path(project_id), project.to_dict())

        # initialise empty stores
        self._write_json(self._assets_path(project_id), [])
        self._event_log_path(project_id).write_text("", encoding="utf-8")
        return project

    def get_project(self, project_id: str) -> Project:
        path = self._project_manifest_path(project_id)
        if not path.exists():
            raise FileNotFoundError(f"Project '{project_id}' not found.")
        return Project.from_dict(self._read_json(path))

    def update_project(self, project_id: str, **fields: Any) -> Project:
        proj = self.get_project(project_id)
        for k, v in fields.items():
            setattr(proj, k, v)
        proj.updated_at = now_ts()
        self._write_json(self._project_manifest_path(project_id), proj.to_dict())
        return proj

    def list_projects(self, status: str | None = None) -> list[Project]:
        projects_dir = self.workspace / "projects"
        if not projects_dir.exists():
            return []
        projects = []
        for child in sorted(projects_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            manifest = child / "project.json"
            if manifest.exists():
                try:
                    p = Project.from_dict(self._read_json(manifest))
                    if status is None or p.status == status:
                        projects.append(p)
                except Exception:
                    pass
        return projects

    # ── event log ─────────────────────────────────────────────────────────────

    def append_event(self, project_id: str, event: EventLogEntry) -> None:
        path = self._event_log_path(project_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def get_events(
        self,
        project_id: str,
        from_ts: float | None = None,
        to_ts: float | None = None,
        types: list[str] | None = None,
    ) -> list[EventLogEntry]:
        path = self._event_log_path(project_id)
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                e = EventLogEntry.from_dict(d)
                if from_ts is not None and e.ts < from_ts:
                    continue
                if to_ts is not None and e.ts > to_ts:
                    continue
                if types is not None and e.type not in types:
                    continue
                events.append(e)
            except Exception:
                pass
        return events

    # ── assets ────────────────────────────────────────────────────────────────

    def add_asset(self, project_id: str, asset: Asset) -> Asset:
        path = self._assets_path(project_id)
        data: list[dict] = self._read_json(path) if path.exists() else []
        data.append(asset.to_dict())
        self._write_json(path, data)
        return asset

    def get_assets(self, project_id: str, kind: str | None = None) -> list[Asset]:
        path = self._assets_path(project_id)
        if not path.exists():
            return []
        data = self._read_json(path)
        assets = [Asset.from_dict(d) for d in data]
        if kind:
            assets = [a for a in assets if a.kind == kind]
        return assets

    def get_asset(self, project_id: str, asset_id: str) -> Asset | None:
        for a in self.get_assets(project_id):
            if a.asset_id == asset_id:
                return a
        return None

    def asset_abs_path(self, project_id: str, asset: Asset) -> Path:
        return self._project_dir(project_id) / asset.path

    # ── timeline ──────────────────────────────────────────────────────────────

    def get_timeline(self, project_id: str) -> dict[str, Any] | None:
        path = self._timeline_path(project_id)
        if not path.exists():
            return None
        return self._read_json(path)

    def save_timeline(self, project_id: str, timeline: dict[str, Any]) -> None:
        self._write_json(self._timeline_path(project_id), timeline)

    # ── render jobs (lightweight) ─────────────────────────────────────────────

    def _jobs_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "jobs.json"

    def save_job(self, project_id: str, job: dict[str, Any]) -> None:
        path = self._jobs_path(project_id)
        jobs: list[dict] = self._read_json(path) if path.exists() else []
        existing = next((j for j in jobs if j["job_id"] == job["job_id"]), None)
        if existing:
            jobs[jobs.index(existing)] = job
        else:
            jobs.append(job)
        self._write_json(path, jobs)

    def get_job(self, project_id: str, job_id: str) -> dict[str, Any] | None:
        path = self._jobs_path(project_id)
        if not path.exists():
            return None
        for j in self._read_json(path):
            if j["job_id"] == job_id:
                return j
        return None
