from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class SessionManifest:
    session_id: str
    title: str
    kind: str
    status: str = "created"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    tags: list[str] = field(default_factory=list)
    objectives: list[str] = field(default_factory=list)
    branding_profile: str = "default"
    distribution_targets: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TimelineEvent:
    event_id: str
    type: str
    at_seconds: float
    created_at: str = field(default_factory=utc_now)
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, event_type: str, at_seconds: float, payload: dict[str, Any]) -> "TimelineEvent":
        return cls(event_id=new_id("evt"), type=event_type, at_seconds=at_seconds, payload=payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssetRecord:
    asset_id: str
    kind: str
    path: str
    created_at: str = field(default_factory=utc_now)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        kind: str,
        path: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "AssetRecord":
        return cls(asset_id=new_id("asset"), kind=kind, path=path, tags=tags or [], metadata=metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
