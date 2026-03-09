"""
Core data models for VlogMCP.
All timeline data is stored as plain dicts for JSON serialization;
only project and asset metadata use dataclasses.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


# ─── helpers ────────────────────────────────────────────────────────────────

def new_id(prefix: str) -> str:
    """Generate a short unique ID with a readable prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def now_ts() -> float:
    return time.time()


# ─── project ────────────────────────────────────────────────────────────────

PROJECT_STATUSES = [
    "created", "recording", "recorded", "composing", "rendered", "published"
]


@dataclass
class Project:
    project_id: str
    name: str
    status: str
    branding_id: str
    created_at: float
    updated_at: float
    dir: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "status": self.status,
            "branding_id": self.branding_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "dir": self.dir,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Project":
        return cls(**d)


# ─── event log ──────────────────────────────────────────────────────────────

EVENT_TYPES = [
    "recording_started", "recording_paused", "recording_resumed", "recording_stopped",
    "section", "screenshot", "window_switch", "code_snippet", "note",
]


@dataclass
class EventLogEntry:
    event_id: str
    type: str
    ts: float           # seconds within raw recording
    created_at: float
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "ts": self.ts,
            "created_at": self.created_at,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EventLogEntry":
        return cls(**d)


# ─── assets ─────────────────────────────────────────────────────────────────

ASSET_KINDS = [
    "raw_clip", "screenshot", "code_diff", "code_snapshot",
    "terminal_capture", "tts", "diagram", "image_ai", "imported",
]


@dataclass
class Asset:
    asset_id: str
    kind: str
    path: str           # relative to project dir
    created_at: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "kind": self.kind,
            "path": self.path,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Asset":
        return cls(**d)


# ─── timeline element constants ──────────────────────────────────────────────

BG_TYPES = ["clip", "color", "image", "cutaway"]

OBJECT_TYPES = [
    "text", "image", "code_block", "lower_third",
    "plate", "meme", "sticker", "shape", "progress_bar",
]

AUDIO_TYPES = ["asset", "lib"]
AUDIO_MIX = ["duck_main", "add", "replace"]

TRANSITION_TYPES = [
    "fade", "wipeleft", "wiperight", "slideleft", "slideright",
    "circleopen", "pixelize",
]

ANIMATE_TYPES = [
    "fade", "slide_left", "slide_right", "slide_up", "slide_down",
    "zoom_in", "zoom_out",
]

TEXT_STYLES = [
    "branding.title", "branding.subtitle", "branding.body",
    "branding.code", "branding.caption",
]
