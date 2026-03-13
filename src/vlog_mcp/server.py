"""
VlogMCP – MCP server for AI-driven video production.

Tools are organised by the pipeline phase:
  0. Project management
  1. Recording
  2. Event log
  3. Asset generation (code, TTS, diagrams)
  4. Library & branding (read-only)
  5. Composition timeline
  6. Preview
  7. Render
  8. Publish
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from . import capture, assets as asset_gen, timeline as tl_ops
from .config import AppConfig, BrandingConfig, LibraryConfig
from .models import Asset, EventLogEntry, new_id, now_ts
from .publisher import publish_telegram
from .renderer import render as do_render
from .storage import ProjectStorage


# ─── global state (initialised at import time) ──────────────────────────────

_cfg     = AppConfig.load()
_branding = BrandingConfig.load(_cfg.branding_path)
_library  = LibraryConfig.load(_cfg.library_path)
_store    = ProjectStorage(_cfg.workspace_path)

mcp = FastMCP("vlog_mcp")


# ─── shared helpers ───────────────────────────────────────────────────────────

def _project_dir(project_id: str) -> Path:
    return _cfg.workspace_path / "projects" / project_id


def _assets_map(project_id: str) -> dict[str, str]:
    """Return {asset_id: absolute_file_path} for all assets in a project."""
    proj_dir = _project_dir(project_id)
    result = {}
    for a in _store.get_assets(project_id):
        result[a.asset_id] = str(proj_dir / a.path)
    # Also index by lib_id for library items
    for item in _library.items:
        result[item.id] = str(_library.abs_path(item))
    return result


def _require_timeline(project_id: str) -> dict:
    tl = _store.get_timeline(project_id)
    if tl is None:
        raise ValueError(
            f"No timeline for project '{project_id}'. "
            "Call timeline_create first."
        )
    return tl


def _save_tl(project_id: str, tl: dict) -> None:
    _store.save_timeline(project_id, tl)


def _ok(msg: str) -> str:
    return json.dumps({"ok": True, "message": msg}, ensure_ascii=False)


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# 0. PROJECT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

class ProjectCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Human-readable project name, e.g. 'Fixing auth bug'",
                      min_length=1, max_length=200)


@mcp.tool(
    name="vlog_project_create",
    annotations={"title": "Create Project", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_project_create(params: ProjectCreateInput) -> str:
    """
    Create a new VlogMCP project.

    Initialises a project directory with captures/, screenshots/, audio/,
    generated/, and exports/ sub-folders plus an empty event log, assets
    registry and project manifest.

    Returns:
        JSON: { project_id, name, status, dir }
    """
    try:
        project = _store.create_project(params.name)
        return json.dumps(project.to_dict(), ensure_ascii=False, indent=2)
    except Exception as exc:
        return _err(str(exc))


class ProjectGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Project ID returned by vlog_project_create")


@mcp.tool(
    name="vlog_project_get",
    annotations={"title": "Get Project", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_project_get(params: ProjectGetInput) -> str:
    """
    Get the current state of a project (status, name, branding_id, timestamps).

    Returns:
        JSON: full project manifest, or error if not found.
    """
    try:
        return json.dumps(_store.get_project(params.project_id).to_dict(),
                          ensure_ascii=False, indent=2)
    except FileNotFoundError as exc:
        return _err(str(exc))


class ProjectListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Optional[str] = Field(
        default=None,
        description="Filter by status: created | recording | recorded | "
                    "composing | rendered | published. Omit for all.")


@mcp.tool(
    name="vlog_project_list",
    annotations={"title": "List Projects", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_project_list(params: ProjectListInput) -> str:
    """
    List all projects, newest first.

    Returns:
        JSON list of project manifests.
    """
    projects = _store.list_projects(status=params.status)
    return json.dumps([p.to_dict() for p in projects], ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. RECORDING
# ═══════════════════════════════════════════════════════════════════════════════

class RecordStartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    source: str = Field(
        default="desktop",
        description="Capture source: 'desktop', 'window:<title>', or 'region:<x,y,w,h>'")
    fps: int = Field(default=30, ge=1, le=60, description="Frames per second")
    with_audio: bool = Field(default=False, description="Also capture system audio")


@mcp.tool(
    name="vlog_record_start",
    annotations={"title": "Start Recording", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_record_start(params: RecordStartInput) -> str:
    """
    Start screen recording for a project using ffmpeg.

    The recording is saved as a raw_clip asset. Automatically logs a
    'recording_started' event to the project event log.

    Returns:
        JSON: { ok, recording_id, asset_id }
    """
    try:
        proj = _store.get_project(params.project_id)
        if capture.is_recording(params.project_id):
            return _err("Recording is already active for this project.")

        rec_id   = new_id("rec")
        filename = f"{rec_id}.mp4"
        out_path = _project_dir(params.project_id) / "captures" / filename

        capture.start(params.project_id, out_path, params.source, params.fps, params.with_audio)

        # register asset (file will grow as recording proceeds)
        asset = Asset(
            asset_id=new_id("ast"),
            kind="raw_clip",
            path=f"captures/{filename}",
            created_at=now_ts(),
            metadata={"recording_id": rec_id, "fps": params.fps,
                      "source": params.source, "has_audio": params.with_audio},
        )
        _store.add_asset(params.project_id, asset)

        event = EventLogEntry(
            event_id=new_id("evt"), type="recording_started",
            ts=0.0, created_at=now_ts(),
            payload={"recording_id": rec_id, "source": params.source, "asset_id": asset.asset_id},
        )
        _store.append_event(params.project_id, event)
        _store.update_project(params.project_id, status="recording")

        return json.dumps({"ok": True, "recording_id": rec_id, "asset_id": asset.asset_id})
    except Exception as exc:
        return _err(str(exc))


class ProjectIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")


@mcp.tool(
    name="vlog_record_pause",
    annotations={"title": "Pause Recording", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_record_pause(params: ProjectIdInput) -> str:
    """Pause an active screen recording (Unix only). Logs 'recording_paused'."""
    try:
        capture.pause(params.project_id)
        _store.append_event(params.project_id, EventLogEntry(
            event_id=new_id("evt"), type="recording_paused",
            ts=0.0, created_at=now_ts(), payload={},
        ))
        return _ok("Recording paused.")
    except Exception as exc:
        return _err(str(exc))


@mcp.tool(
    name="vlog_record_resume",
    annotations={"title": "Resume Recording", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_record_resume(params: ProjectIdInput) -> str:
    """Resume a paused screen recording (Unix only). Logs 'recording_resumed'."""
    try:
        capture.resume(params.project_id)
        _store.append_event(params.project_id, EventLogEntry(
            event_id=new_id("evt"), type="recording_resumed",
            ts=0.0, created_at=now_ts(), payload={},
        ))
        return _ok("Recording resumed.")
    except Exception as exc:
        return _err(str(exc))


class RecordStopInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    duration: Optional[float] = Field(
        default=None, description="Known recording duration in seconds (optional)")


@mcp.tool(
    name="vlog_record_stop",
    annotations={"title": "Stop Recording", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_record_stop(params: RecordStopInput) -> str:
    """
    Stop the active screen recording. Finalises the MP4 file.
    Logs 'recording_stopped'. Project status → 'recorded'.

    Returns:
        JSON: { ok, message }
    """
    try:
        capture.stop(params.project_id)
        _store.append_event(params.project_id, EventLogEntry(
            event_id=new_id("evt"), type="recording_stopped",
            ts=params.duration or 0.0, created_at=now_ts(),
            payload={"duration": params.duration},
        ))
        _store.update_project(params.project_id, status="recorded")
        return _ok("Recording stopped. Project status → 'recorded'.")
    except Exception as exc:
        return _err(str(exc))


class LogEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    ts: float = Field(..., ge=0, description="Timestamp within the recording (seconds)")
    type: str = Field(
        ...,
        description="Event type: section | note | window_switch | screenshot | code_snippet")
    label: str = Field(default="", description="Human-readable label for this event")
    payload: Optional[dict] = Field(default_factory=dict,
                                    description="Additional event-specific data")


@mcp.tool(
    name="vlog_log_event",
    annotations={"title": "Log Recording Event", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_log_event(params: LogEventInput) -> str:
    """
    Append an event to the recording event log.
    Call this during recording to mark sections, notes, or window switches.

    Returns:
        JSON: { ok, event_id }
    """
    try:
        payload = dict(params.payload or {})
        if params.label:
            payload["label"] = params.label
        event = EventLogEntry(
            event_id=new_id("evt"), type=params.type,
            ts=params.ts, created_at=now_ts(), payload=payload,
        )
        _store.append_event(params.project_id, event)
        return json.dumps({"ok": True, "event_id": event.event_id})
    except Exception as exc:
        return _err(str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# 2. EVENT LOG
# ═══════════════════════════════════════════════════════════════════════════════

class EventLogGetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    from_ts: Optional[float] = Field(default=None, description="Filter from this timestamp (seconds)")
    to_ts: Optional[float] = Field(default=None, description="Filter to this timestamp (seconds)")
    types: Optional[List[str]] = Field(default=None,
                                       description="Filter by event types, e.g. ['section', 'note']")


@mcp.tool(
    name="vlog_event_log_get",
    annotations={"title": "Get Event Log", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_event_log_get(params: EventLogGetInput) -> str:
    """
    Read the recording event log.
    Use this after recording to understand the structure of the session
    before building the composition timeline.

    Returns:
        JSON list of events, each with: event_id, type, ts, payload.
    """
    try:
        events = _store.get_events(
            params.project_id,
            from_ts=params.from_ts,
            to_ts=params.to_ts,
            types=params.types,
        )
        return json.dumps([e.to_dict() for e in events], ensure_ascii=False, indent=2)
    except Exception as exc:
        return _err(str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ASSET GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

class ScreenshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    monitor: int = Field(default=1, ge=1, description="Monitor index (1-based)")


@mcp.tool(
    name="vlog_screenshot_take",
    annotations={"title": "Take Screenshot", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_screenshot_take(params: ScreenshotInput) -> str:
    """
    Capture a screenshot of the specified monitor and register it as an asset.

    Returns:
        JSON: { ok, asset_id, path }
    """
    try:
        asset_id = new_id("ast")
        filename = f"screenshot_{asset_id}.png"
        out_path = _project_dir(params.project_id) / "screenshots" / filename
        asset_gen.screenshot_take(out_path, params.monitor)
        asset = Asset(asset_id=asset_id, kind="screenshot",
                      path=f"screenshots/{filename}",
                      created_at=now_ts(), metadata={"monitor": params.monitor})
        _store.add_asset(params.project_id, asset)
        return json.dumps({"ok": True, "asset_id": asset_id, "path": str(out_path)})
    except Exception as exc:
        return _err(str(exc))


class CodeSnapshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    code: str = Field(..., description="Source code text to render")
    lang: str = Field(default="python", description="Programming language for syntax highlighting")
    start_line: int = Field(default=1, ge=1, description="First line number to display")
    highlight_lines: Optional[List[Any]] = Field(
        default=None,
        description=(
            "Lines to highlight. Two formats accepted:\n"
            "  • List[int]  — highlight those lines with default yellow-tint background\n"
            "  • List[dict] — each dict: {\"line\": N, \"bg\": \"#hexcolor\", \"fg\": \"#hexcolor\"}\n"
            "    'bg' sets highlight background color; 'fg' overrides all text on that line.\n"
            "Example: [1, {\"line\": 3, \"bg\": \"#1e3a2f\", \"fg\": \"#4ade80\"}, 7]"
        ))
    title: Optional[str] = Field(default=None, description="Optional title shown in metadata")


@mcp.tool(
    name="vlog_code_snapshot",
    annotations={"title": "Code Snapshot", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_code_snapshot(params: CodeSnapshotInput) -> str:
    """
    Render a syntax-highlighted code snippet to a PNG (Monokai dark theme).
    Useful for showing specific code segments on screen.

    Returns:
        JSON: { ok, asset_id, path }
    """
    try:
        asset_id = new_id("ast")
        filename = f"code_snapshot_{asset_id}.png"
        out_path = _project_dir(params.project_id) / "generated" / filename
        asset_gen.code_snapshot(
            out_path, params.code, params.lang,
            highlight_lines=params.highlight_lines,
        )
        asset = Asset(asset_id=asset_id, kind="code_snapshot",
                      path=f"generated/{filename}", created_at=now_ts(),
                      metadata={"lang": params.lang, "title": params.title or ""})
        _store.add_asset(params.project_id, asset)
        return json.dumps({"ok": True, "asset_id": asset_id, "path": str(out_path)})
    except Exception as exc:
        return _err(str(exc))


class CodeTypewriterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    code: str = Field(..., description="Source code to animate character by character")
    lang: str = Field(default="python", description="Language for syntax highlighting")
    chars_per_second: float = Field(
        default=30.0, ge=1.0, le=500.0,
        description="How many characters are revealed per second. 30 = natural typing speed.")
    cursor: bool = Field(
        default=True,
        description="Show a blinking block cursor at the insertion point")
    fps: int = Field(default=30, ge=12, le=60, description="Video frame rate")


@mcp.tool(
    name="vlog_code_typewriter",
    annotations={"title": "Code Typewriter", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_code_typewriter(params: CodeTypewriterInput) -> str:
    """
    Generate a video (MP4) of code appearing character by character — typewriter effect.

    The resulting clip can be added to the timeline as a background clip via
    vlog_timeline_add_clip.  Syntax highlighting uses Monokai dark theme.

    Returns:
        JSON: { ok, asset_id, path, duration_seconds }
    """
    try:
        asset_id = new_id("ast")
        filename = f"code_typewriter_{asset_id}.mp4"
        out_path = _project_dir(params.project_id) / "generated" / filename
        asset_gen.code_typewriter(
            out_path, params.code, params.lang,
            chars_per_second=params.chars_per_second,
            cursor=params.cursor,
            fps=params.fps,
        )
        total_chars = len(params.code)
        duration = total_chars / params.chars_per_second + 1.0  # +1s pause at end
        asset = Asset(
            asset_id=asset_id, kind="code_typewriter",
            path=f"generated/{filename}", created_at=now_ts(),
            metadata={
                "lang": params.lang,
                "chars_per_second": params.chars_per_second,
                "duration": round(duration, 2),
            },
        )
        _store.add_asset(params.project_id, asset)
        return json.dumps({
            "ok": True,
            "asset_id": asset_id,
            "path": str(out_path),
            "duration_seconds": round(duration, 2),
        })
    except Exception as exc:
        return _err(str(exc))


class CodeDiffInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    before: str = Field(..., description="Original text or file path (if it ends with a known extension)")
    after: str = Field(..., description="Modified text or file path")
    lang: str = Field(default="python", description="Language for context")
    title: Optional[str] = Field(default=None, description="Title shown at top of diff card")


@mcp.tool(
    name="vlog_code_diff",
    annotations={"title": "Code Diff", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_code_diff(params: CodeDiffInput) -> str:
    """
    Render a unified diff of two code snippets or files to a PNG.
    Red lines = removed, green lines = added.

    Returns:
        JSON: { ok, asset_id, path }
    """
    try:
        before_text = params.before
        after_text  = params.after
        # If it looks like a file path, try reading it
        for attr in ("before", "after"):
            val = getattr(params, attr)
            p = Path(val)
            if p.exists() and p.is_file():
                if attr == "before":
                    before_text = p.read_text(encoding="utf-8")
                else:
                    after_text = p.read_text(encoding="utf-8")

        asset_id = new_id("ast")
        filename = f"diff_{asset_id}.png"
        out_path = _project_dir(params.project_id) / "generated" / filename
        asset_gen.code_diff(out_path, before_text, after_text,
                            lang=params.lang, title=params.title or "")
        asset = Asset(asset_id=asset_id, kind="code_diff",
                      path=f"generated/{filename}", created_at=now_ts(),
                      metadata={"lang": params.lang, "title": params.title or ""})
        _store.add_asset(params.project_id, asset)
        return json.dumps({"ok": True, "asset_id": asset_id, "path": str(out_path)})
    except Exception as exc:
        return _err(str(exc))


class TerminalCaptureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    command: str = Field(..., description="Command string shown in the terminal prompt")
    output: str = Field(..., description="Terminal output text to display")
    theme: str = Field(default="dark", description="'dark' or 'light' terminal theme")


@mcp.tool(
    name="vlog_terminal_capture",
    annotations={"title": "Terminal Capture", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_terminal_capture(params: TerminalCaptureInput) -> str:
    """
    Render a terminal screenshot as a PNG (dark background, monospace font).
    Useful for showing test results, build output, or CLI commands.

    Returns:
        JSON: { ok, asset_id, path }
    """
    try:
        asset_id = new_id("ast")
        filename = f"terminal_{asset_id}.png"
        out_path = _project_dir(params.project_id) / "generated" / filename
        asset_gen.terminal_capture(out_path, params.command, params.output, params.theme)
        asset = Asset(asset_id=asset_id, kind="terminal_capture",
                      path=f"generated/{filename}", created_at=now_ts(),
                      metadata={"command": params.command, "theme": params.theme})
        _store.add_asset(params.project_id, asset)
        return json.dumps({"ok": True, "asset_id": asset_id, "path": str(out_path)})
    except Exception as exc:
        return _err(str(exc))


class TTSInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    text: str = Field(..., description="Text to convert to speech", min_length=1, max_length=4096)
    provider: str = Field(
        default="openai",
        description="TTS provider: 'openai' (or any OpenAI-compatible API) | 'elevenlabs'",
    )
    voice: str = Field(
        default="nova",
        description=(
            "Voice name.\n"
            "OpenAI classic (tts-1 / tts-1-hd): alloy | echo | fable | onyx | nova | shimmer\n"
            "OpenAI new (gpt-4o-mini-tts / gpt-4o-tts): coral | sage | ash | ballad | verse\n"
            "ElevenLabs: voice_id string (20+ chars) from your ElevenLabs account"
        ),
    )
    model: str = Field(
        default="",
        description=(
            "TTS model to use. Leave empty for auto-selection.\n"
            "OpenAI: tts-1 | tts-1-hd | gpt-4o-mini-tts | gpt-4o-tts\n"
            "  • Auto-rule: new voices (coral/sage/ash/ballad/verse) → gpt-4o-mini-tts\n"
            "  •            classic voices → tts-1\n"
            "ElevenLabs: eleven_multilingual_v2 | eleven_turbo_v2_5 | eleven_flash_v2_5"
        ),
    )
    instructions: str = Field(
        default="",
        description=(
            "Voice style instruction (OpenAI gpt-4o-mini-tts / gpt-4o-tts only). "
            "Ignored for other models. "
            "Example: 'Speak with an energetic and upbeat tone, like a tech conference presenter.'"
        ),
    )
    base_url: str = Field(
        default="",
        description=(
            "Override the OpenAI API base URL. Use for any OpenAI-compatible proxy.\n"
            "Examples: 'https://api.proxyapi.ru/openai/v1', 'https://your-proxy.com/v1'\n"
            "Defaults to VLOG_MCP_OPENAI_BASE_URL env var, then 'https://api.openai.com/v1'.\n"
            "Ignored for provider='elevenlabs'."
        ),
    )


@mcp.tool(
    name="vlog_tts_generate",
    annotations={"title": "Generate TTS", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_tts_generate(params: TTSInput) -> str:
    """
    Generate text-to-speech audio (MP3).

    Provider 'openai' (default):
      Works with the official OpenAI API and any OpenAI-compatible proxy.
      Set base_url to point at a different endpoint (e.g. a Russian proxy like proxyapi.ru).
      Supports new-generation models with the 'instructions' voice-style parameter.

    Provider 'elevenlabs':
      Works with ElevenLabs REST API. Voice must be a voice_id from your account.

    Returns:
        JSON: { ok, asset_id, path, provider, model, voice }
    """
    try:
        asset_id = new_id("ast")
        filename = f"tts_{asset_id}.mp3"
        out_path = _project_dir(params.project_id) / "audio" / filename

        if params.provider in ("openai", ""):
            api_key = _cfg.openai_api_key
            # base_url: explicit param > env var > default (empty = OpenAI official)
            base_url = params.base_url or _cfg.openai_base_url
        else:
            api_key = _cfg.elevenlabs_api_key
            base_url = ""

        await asset_gen.tts_generate(
            out_path,
            text=params.text,
            voice=params.voice,
            api_key=api_key,
            provider=params.provider,
            model=params.model,
            instructions=params.instructions,
            base_url=base_url,
        )
        asset = Asset(
            asset_id=asset_id,
            kind="tts",
            path=f"audio/{filename}",
            created_at=now_ts(),
            metadata={
                "text":         params.text,
                "voice":        params.voice,
                "provider":     params.provider,
                "model":        params.model,
                "instructions": params.instructions,
                "base_url":     base_url,
            },
        )
        _store.add_asset(params.project_id, asset)
        return json.dumps({
            "ok":       True,
            "asset_id": asset_id,
            "path":     str(out_path),
            "provider": params.provider,
            "model":    params.model or "auto",
            "voice":    params.voice,
        })
    except Exception as exc:
        return _err(str(exc))


class DiagramInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    type: str = Field(..., description="Diagram type: bar_chart | pie | table")
    data: dict = Field(..., description=(
        "Data for the diagram. "
        "bar_chart: {labels:[], values:[], unit?:'', color?:'#hex'}. "
        "pie: {labels:[], values:[], colors?:[]}. "
        "table: {columns:[], rows:[[...]]}."
    ))
    title: str = Field(default="", description="Optional chart title")
    theme: str = Field(default="dark", description="'dark' or 'light'")


@mcp.tool(
    name="vlog_diagram_create",
    annotations={"title": "Create Diagram", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_diagram_create(params: DiagramInput) -> str:
    """
    Create a data visualisation as a PNG (bar_chart, pie, or table).

    Returns:
        JSON: { ok, asset_id, path }
    """
    try:
        asset_id = new_id("ast")
        filename = f"diagram_{asset_id}.png"
        out_path = _project_dir(params.project_id) / "generated" / filename
        asset_gen.diagram_create(out_path, params.type, params.data,
                                 params.title, params.theme)
        asset = Asset(asset_id=asset_id, kind="diagram",
                      path=f"generated/{filename}", created_at=now_ts(),
                      metadata={"diagram_type": params.type, "title": params.title})
        _store.add_asset(params.project_id, asset)
        return json.dumps({"ok": True, "asset_id": asset_id, "path": str(out_path)})
    except Exception as exc:
        return _err(str(exc))


class ImageGenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    prompt: str = Field(..., description="Text prompt describing the image to generate", min_length=3)
    provider: str = Field(
        default="openai",
        description=(
            "Image generation provider:\n"
            "  • 'openai'    — DALL-E 3. Requires VLOG_MCP_OPENAI_KEY.\n"
            "  • 'stability' — Stability AI SD3/SDXL. Requires VLOG_MCP_STABILITY_KEY."
        ),
    )
    size: str = Field(
        default="1792x1024",
        description=(
            "Image size / aspect ratio.\n"
            "OpenAI:    1024x1024 | 1792x1024 (16:9 landscape) | 1024x1792 (9:16 portrait).\n"
            "Stability: 1024x1024 | 1792x1024 | 1280x720 | 1216x832 | 832x1216 | 720x1280."
        ),
    )
    quality: str = Field(
        default="standard",
        description="OpenAI only — 'standard' (faster/cheaper) or 'hd' (more detailed).",
    )
    style: str = Field(
        default="vivid",
        description="OpenAI only — 'vivid' (dramatic/hyper-real) or 'natural' (realistic/subtle).",
    )
    negative_prompt: str = Field(
        default="",
        description="Stability AI only — what to avoid in the generated image.",
    )
    model: str = Field(
        default="",
        description=(
            "Override the model name.\n"
            "Stability AI defaults: 'stable-diffusion-3-large'.\n"
            "OpenAI always uses 'dall-e-3' (no override)."
        ),
    )


@mcp.tool(
    name="vlog_image_generate",
    annotations={"title": "Generate AI Image", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_image_generate(params: ImageGenInput) -> str:
    """
    Generate an image from a text prompt using an AI image generation provider.

    Supported providers:

      openai (default) — DALL-E 3
        • Best quality for illustrations, diagrams, concept art
        • Sizes: 1792x1024 (landscape 16:9), 1024x1024 (square), 1024x1792 (portrait)
        • quality: standard | hd
        • style: vivid | natural
        • Key: VLOG_MCP_OPENAI_KEY

      stability — Stability AI (Stable Diffusion 3 / SDXL)
        • Best for photorealistic images, detailed scenes, custom styles
        • Supports negative_prompt to exclude unwanted elements
        • Key: VLOG_MCP_STABILITY_KEY

    The generated PNG is saved as a project asset and can be added to the
    timeline with vlog_timeline_add_image.

    Returns:
        JSON: { ok, asset_id, path, provider, prompt }
    """
    try:
        asset_id = new_id("ast")
        filename = f"imggen_{asset_id}.png"
        out_path = _project_dir(params.project_id) / "generated" / filename
        api_key = (
            _cfg.openai_api_key if params.provider in ("openai", "")
            else _cfg.stability_api_key
        )
        await asset_gen.image_generate(
            out_path,
            prompt=params.prompt,
            provider=params.provider,
            api_key=api_key,
            size=params.size,
            quality=params.quality,
            style=params.style,
            negative_prompt=params.negative_prompt,
            model=params.model,
        )
        asset = Asset(
            asset_id=asset_id,
            kind="image",
            path=f"generated/{filename}",
            created_at=now_ts(),
            metadata={
                "source":          "ai_generated",
                "provider":        params.provider,
                "prompt":          params.prompt,
                "negative_prompt": params.negative_prompt,
                "size":            params.size,
                "quality":         params.quality,
                "style":           params.style,
                "model":           params.model,
            },
        )
        _store.add_asset(params.project_id, asset)
        return json.dumps({
            "ok":       True,
            "asset_id": asset_id,
            "path":     str(out_path),
            "provider": params.provider,
            "prompt":   params.prompt,
        })
    except Exception as exc:
        return _err(str(exc))


class AssetTrimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    asset_id: str = Field(..., description="Asset ID to trim")
    start: float = Field(default=0.0, ge=0, description="Trim start in seconds")
    end: Optional[float] = Field(default=None, gt=0, description="Trim end in seconds (omit = until EOF)")
    fade_in: float = Field(default=0.0, ge=0, description="Fade-in duration in seconds (0 = hard cut)")
    fade_out: float = Field(default=0.0, ge=0, description="Fade-out duration in seconds (0 = hard cut)")
    fade_type: str = Field(
        default="linear",
        description="Fade curve: 'linear' (default) or 'exponential' (softer tail, audio only)",
    )


@mcp.tool(
    name="vlog_asset_trim",
    annotations={"title": "Trim Asset", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_asset_trim(params: AssetTrimInput) -> str:
    """
    Trim an audio or video asset and apply fade in / fade out.

    Creates a new trimmed asset (does not modify the original).
    Works with: audio (.mp3, .wav, .aac) and video (.mp4, .mov) assets.

    fade_in / fade_out = 0  → hard cut (instant, no transition)
    fade_in / fade_out > 0  → smooth fade (duration in seconds)
    fade_type = 'exponential' → softer trailing fade for music (audio only)

    Returns:
        JSON: { ok, asset_id, path }
    """
    try:
        src_asset = _store.get_asset(params.project_id, params.asset_id)
        if not src_asset:
            return _err(f"Asset '{params.asset_id}' not found.")
        src_path = _project_dir(params.project_id) / src_asset.path
        suffix = src_path.suffix
        new_id_val = new_id("ast")
        out_name = f"trimmed_{new_id_val}{suffix}"
        out_path = _project_dir(params.project_id) / "audio" / out_name

        asset_gen.asset_trim(
            src_path, out_path,
            start=params.start,
            end=params.end,
            fade_in=params.fade_in,
            fade_out=params.fade_out,
            fade_type=params.fade_type,
        )
        asset = Asset(
            asset_id=new_id_val,
            kind=src_asset.kind,
            path=f"audio/{out_name}",
            created_at=now_ts(),
            metadata={
                "source_asset_id": params.asset_id,
                "trim_start":      params.start,
                "trim_end":        params.end,
                "fade_in":         params.fade_in,
                "fade_out":        params.fade_out,
            },
        )
        _store.add_asset(params.project_id, asset)
        return json.dumps({"ok": True, "asset_id": new_id_val, "path": str(out_path)})
    except Exception as exc:
        return _err(str(exc))


class VideoGenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    prompt: str = Field(..., description="Text prompt describing the video to generate", min_length=3)
    provider: str = Field(
        ...,
        description=(
            "Video generation provider:\n"
            "  • 'runway'  — Runway Gen-4 Turbo. 5 or 10 sec. Key: video_gen.runway_api_key\n"
            "  • 'luma'    — Luma AI Dream Machine. 5 or 9 sec. Key: video_gen.luma_api_key\n"
            "  • 'kling'   — Kling AI v2. 5 or 10 sec. Key: video_gen.kling_api_key"
        ),
    )
    duration: float = Field(default=5.0, gt=0, description="Desired duration in seconds (5 or 10; provider may round)")
    aspect_ratio: str = Field(
        default="16:9",
        description="Aspect ratio: '16:9' | '9:16' | '1:1' | '4:3'",
    )
    negative_prompt: str = Field(
        default="",
        description="Elements to avoid (Runway and Kling only)",
    )
    model: str = Field(
        default="",
        description="Override model name (e.g. 'gen4_turbo' for Runway, 'kling-v2-master' for Kling)",
    )


@mcp.tool(
    name="vlog_video_generate",
    annotations={"title": "Generate AI Video", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_video_generate(params: VideoGenInput) -> str:
    """
    Generate a short video clip from a text prompt using an AI provider.

    The generated .mp4 is saved as a project asset and can be used as:
      • background clip   → vlog_timeline_add_clip(asset_id=...)
      • cutaway overlay   → vlog_timeline_add_cutaway(source='asset', ...)

    Providers:
      runway  — Best cinematic quality. 5 or 10 sec.
      luma    — Good motion quality. 5 or 9 sec.
      kling   — Fast + detailed. 5 or 10 sec.

    This is an async operation (generation takes 30–120 sec typically).

    Returns:
        JSON: { ok, asset_id, path, provider, duration }
    """
    try:
        api_key_map = {
            "runway": _cfg.runway_api_key,
            "luma":   _cfg.luma_api_key,
            "kling":  _cfg.kling_api_key,
        }
        api_key = api_key_map.get(params.provider, "")
        asset_id_val = new_id("ast")
        out_path = _project_dir(params.project_id) / "generated" / f"videogen_{asset_id_val}.mp4"
        await asset_gen.video_generate(
            out_path,
            prompt=params.prompt,
            provider=params.provider,
            api_key=api_key,
            duration=params.duration,
            aspect_ratio=params.aspect_ratio,
            negative_prompt=params.negative_prompt,
            model=params.model,
        )
        asset = Asset(
            asset_id=asset_id_val,
            kind="video",
            path=f"generated/videogen_{asset_id_val}.mp4",
            created_at=now_ts(),
            metadata={
                "source":         "ai_generated",
                "provider":       params.provider,
                "prompt":         params.prompt,
                "duration":       params.duration,
                "aspect_ratio":   params.aspect_ratio,
                "negative_prompt":params.negative_prompt,
                "model":          params.model,
            },
        )
        _store.add_asset(params.project_id, asset)
        return json.dumps({
            "ok":          True,
            "asset_id":    asset_id_val,
            "path":        str(out_path),
            "provider":    params.provider,
            "duration":    params.duration,
        })
    except Exception as exc:
        return _err(str(exc))


class MusicGenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    prompt: str = Field(..., description="Text prompt describing the music to generate", min_length=3)
    provider: str = Field(
        ...,
        description=(
            "Music generation provider:\n"
            "  • 'stability' — Stability AI Stable Audio. 0.5–180 sec. Key: stability.api_key\n"
            "  • 'replicate' — Replicate MusicGen (Meta). Any duration. Key: music_gen.replicate_api_key"
        ),
    )
    duration: float = Field(default=30.0, gt=0, description="Desired music duration in seconds")
    model: str = Field(
        default="",
        description=(
            "Override model. Replicate: full version hash or leave empty for MusicGen stereo-large. "
            "Stability: ignored (uses Stable Audio)."
        ),
    )


@mcp.tool(
    name="vlog_music_generate",
    annotations={"title": "Generate AI Music", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_music_generate(params: MusicGenInput) -> str:
    """
    Generate music or a background audio track from a text prompt.

    The generated .mp3 is saved as a project asset and can be added to
    the timeline with vlog_timeline_add_music(asset_id=...).

    Providers:
      stability — Stable Audio: great for ambient/atmospheric tracks.
      replicate — MusicGen: great for structured music with clear style.

    Returns:
        JSON: { ok, asset_id, path, provider, duration }
    """
    try:
        api_key = (
            _cfg.stability_api_key if params.provider == "stability"
            else _cfg.replicate_api_key
        )
        asset_id_val = new_id("ast")
        out_path = _project_dir(params.project_id) / "audio" / f"musicgen_{asset_id_val}.mp3"
        await asset_gen.music_generate(
            out_path,
            prompt=params.prompt,
            provider=params.provider,
            api_key=api_key,
            duration=params.duration,
            model=params.model,
        )
        asset = Asset(
            asset_id=asset_id_val,
            kind="music",
            path=f"audio/musicgen_{asset_id_val}.mp3",
            created_at=now_ts(),
            metadata={
                "source":   "ai_generated",
                "provider": params.provider,
                "prompt":   params.prompt,
                "duration": params.duration,
                "model":    params.model,
            },
        )
        _store.add_asset(params.project_id, asset)
        return json.dumps({
            "ok":       True,
            "asset_id": asset_id_val,
            "path":     str(out_path),
            "provider": params.provider,
            "duration": params.duration,
        })
    except Exception as exc:
        return _err(str(exc))


class AssetListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    kind: Optional[str] = Field(
        default=None,
        description="Filter by kind: raw_clip | screenshot | code_diff | "
                    "code_snapshot | terminal_capture | tts | diagram | image_ai")


@mcp.tool(
    name="vlog_asset_list",
    annotations={"title": "List Assets", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_asset_list(params: AssetListInput) -> str:
    """
    List all assets registered for a project.

    Returns:
        JSON list of assets with asset_id, kind, path, metadata.
    """
    try:
        assets = _store.get_assets(params.project_id, kind=params.kind)
        return json.dumps([a.to_dict() for a in assets], ensure_ascii=False, indent=2)
    except Exception as exc:
        return _err(str(exc))


class AssetPreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    asset_id: str = Field(..., description="Asset ID to preview")


@mcp.tool(
    name="vlog_asset_preview",
    annotations={"title": "Asset Preview", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_asset_preview(params: AssetPreviewInput) -> str:
    """
    Preview an asset.
    For images/code/diagrams: returns base64-encoded PNG thumbnail.
    For audio/video: returns metadata only.

    Returns:
        JSON: { asset_id, kind, base64_png? } or { asset_id, kind, metadata }
    """
    try:
        import base64, io
        from PIL import Image

        asset = _store.get_asset(params.project_id, params.asset_id)
        if not asset:
            return _err(f"Asset '{params.asset_id}' not found.")

        abs_path = _store.asset_abs_path(params.project_id, asset)
        if asset.kind in ("screenshot", "code_snapshot", "code_diff",
                          "terminal_capture", "diagram", "image_ai"):
            if abs_path.exists():
                img = Image.open(abs_path)
                img.thumbnail((640, 360))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                return json.dumps({"asset_id": asset.asset_id, "kind": asset.kind,
                                   "base64_png": b64})
        return json.dumps({"asset_id": asset.asset_id, "kind": asset.kind,
                           "metadata": asset.metadata, "path": str(abs_path)})
    except Exception as exc:
        return _err(str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# 4. LIBRARY & BRANDING (read-only)
# ═══════════════════════════════════════════════════════════════════════════════

class LibraryListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Optional[str] = Field(
        default=None,
        description="Category filter: meme | sfx | sticker | cutaway | music")
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags")


@mcp.tool(
    name="vlog_library_list",
    annotations={"title": "List Library", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_library_list(params: LibraryListInput) -> str:
    """
    List all items in the media library (memes, SFX, stickers, cutaways, music).

    Returns:
        JSON list of library items with id, category, tags, description.
    """
    items = _library.list_by_category(params.kind)
    if params.tags:
        tags_lower = [t.lower() for t in params.tags]
        items = [i for i in items
                 if any(tg in " ".join(i.tags).lower() for tg in tags_lower)]
    return json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2)


class LibrarySearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., description="Text query, matched against id/tags/description",
                       min_length=1)
    kind: Optional[str] = Field(
        default=None,
        description="Category filter: meme | sfx | sticker | cutaway | music")


@mcp.tool(
    name="vlog_library_search",
    annotations={"title": "Search Library", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_library_search(params: LibrarySearchInput) -> str:
    """
    Search the media library by text query.
    Example: 'баг пожар' → [this_is_fine, error_boop, ...]

    Returns:
        JSON list of matching library items.
    """
    results = _library.search(params.query, category=params.kind)
    return json.dumps([i.to_dict() for i in results], ensure_ascii=False, indent=2)


class LibraryPreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lib_id: str = Field(..., description="Library item ID")


@mcp.tool(
    name="vlog_library_preview",
    annotations={"title": "Library Preview", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_library_preview(params: LibraryPreviewInput) -> str:
    """
    Preview a library item. For images/GIFs returns base64 PNG thumbnail.
    For audio/video returns metadata.

    Returns:
        JSON: { id, category, base64_png? } or { id, category, metadata }
    """
    try:
        import base64, io
        from PIL import Image

        item = _library.get(params.lib_id)
        if not item:
            return _err(f"Library item '{params.lib_id}' not found.")
        lib_path = _library.abs_path(item)
        if item.kind in ("image", "gif") and lib_path.exists():
            img = Image.open(lib_path).convert("RGBA")
            img.thumbnail((320, 320))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return json.dumps({**item.to_dict(), "base64_png": b64})
        return json.dumps(item.to_dict())
    except Exception as exc:
        return _err(str(exc))


@mcp.tool(
    name="vlog_branding_get",
    annotations={"title": "Get Branding Config", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_branding_get() -> str:
    """
    Return the current branding configuration (read-only).
    Includes palette, fonts, plates, clips (intro/outro/cutaways), watermark.
    AI agents MUST read this first to know available styles and assets.

    Returns:
        JSON: branding configuration.
    """
    return json.dumps(_branding.to_dict(), ensure_ascii=False, indent=2)


@mcp.tool(
    name="vlog_branding_list_plates",
    annotations={"title": "List Branding Plates", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_branding_list_plates() -> str:
    """
    List all available branding plate templates (section_card, quote_card, etc.).

    Returns:
        JSON list of { name, description, text_style }.
    """
    result = []
    for name, pc in _branding.plates.items():
        result.append({"name": name, "description": pc.description,
                        "text_style": pc.text_style, "asset": pc.asset})
    return json.dumps(result, ensure_ascii=False, indent=2)


class BrandingPlatePreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plate: str = Field(..., description="Plate name, e.g. 'section_card'")


@mcp.tool(
    name="vlog_branding_preview_plate",
    annotations={"title": "Preview Branding Plate", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_branding_preview_plate(params: BrandingPlatePreviewInput) -> str:
    """
    Preview a branding plate as a base64 PNG thumbnail.

    Returns:
        JSON: { plate, base64_png? } or metadata if file not found.
    """
    try:
        import base64, io
        from PIL import Image

        pc = _branding.plate(params.plate)
        if not pc:
            return _err(f"Plate '{params.plate}' not found in branding config.")
        plate_path = Path(pc.asset)
        if plate_path.exists():
            img = Image.open(plate_path)
            img.thumbnail((640, 360))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return json.dumps({"plate": params.plate, "base64_png": b64})
        return json.dumps({"plate": params.plate, "asset": pc.asset,
                           "message": "Plate file not found – place PNG at the path above."})
    except Exception as exc:
        return _err(str(exc))


@mcp.tool(
    name="vlog_branding_list_cutaways",
    annotations={"title": "List Branding Cutaways", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_branding_list_cutaways() -> str:
    """
    List all branded cutaway video clips available for use in the timeline.

    Returns:
        JSON list of { id, path, duration, tags }.
    """
    cuts = [{"id": c.id, "path": c.path, "duration": c.duration, "tags": c.tags}
            for c in _branding.cutaways()]
    return json.dumps(cuts, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. COMPOSITION TIMELINE
# ═══════════════════════════════════════════════════════════════════════════════

class TimelineCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    duration: float = Field(..., gt=0, description="Total duration of the final video in seconds")


@mcp.tool(
    name="vlog_timeline_create",
    annotations={"title": "Create Timeline", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_create(params: TimelineCreateInput) -> str:
    """
    Create a new composition timeline for a project.
    This replaces any existing timeline.

    Returns:
        JSON: { ok, timeline_id, duration }
    """
    try:
        tl = tl_ops.create_timeline(params.project_id, params.duration)
        _save_tl(params.project_id, tl)
        _store.update_project(params.project_id, status="composing")
        return json.dumps({"ok": True, "timeline_id": tl["timeline_id"],
                           "duration": tl["duration"]})
    except Exception as exc:
        return _err(str(exc))


# ── background ───────────────────────────────────────────────────────────────

class AddClipInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    asset_id: str = Field(..., description="asset_id of the raw_clip to use")
    start: float = Field(..., ge=0, description="Start second in the FINAL video")
    duration: float = Field(..., gt=0, description="Duration in the final video (seconds)")
    source_in: float = Field(..., ge=0, description="Start second in the RAW recording to cut from")
    source_out: float = Field(..., gt=0, description="End second in the RAW recording")


@mcp.tool(
    name="vlog_timeline_add_clip",
    annotations={"title": "Add Video Clip", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_clip(params: AddClipInput) -> str:
    """
    Add a clip from a raw recording as a background layer element.
    source_in/source_out define which portion of the raw clip to use.

    Returns:
        JSON: { ok, element_id }
    """
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_clip(tl, params.asset_id, params.start, params.duration,
                               params.source_in, params.source_out)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddColorBgInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    color: str = Field(..., description="Hex color, e.g. '#121219'")
    start: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)


@mcp.tool(
    name="vlog_timeline_add_color_bg",
    annotations={"title": "Add Color Background", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_color_bg(params: AddColorBgInput) -> str:
    """Add a solid color background layer. Useful for 'presentation' segments."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_color_bg(tl, params.color, params.start, params.duration)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddImageBgInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    asset_id: str = Field(..., description="asset_id of image to use as background")
    start: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)


@mcp.tool(
    name="vlog_timeline_add_image_bg",
    annotations={"title": "Add Image Background", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_image_bg(params: AddImageBgInput) -> str:
    """Add a full-screen image as background layer (e.g. diagram or screenshot)."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_image_bg(tl, params.asset_id, params.start, params.duration)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddCutawayInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    source: str = Field(..., description="'library' or 'branding'")
    id: str = Field(..., description="lib_id or branding cutaway id")
    start: float = Field(..., ge=0)
    duration: Optional[float] = Field(default=None, gt=0, description="Duration (uses clip length if omitted)")


@mcp.tool(
    name="vlog_timeline_add_cutaway",
    annotations={"title": "Add Cutaway", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_cutaway(params: AddCutawayInput) -> str:
    """Add a cutaway clip (transition footage) as a background layer."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_cutaway(tl, params.source, params.id, params.start, params.duration)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


# ── objects ───────────────────────────────────────────────────────────────────

_EFFECT_FIELD = Field(
    default=None,
    description=(
        'Appear/disappear effect. Examples:\n'
        '  {"effect": "fade", "duration": 0.4}  — smooth opacity transition\n'
        '  {"effect": "none"}                   — instant cut (default)'
    ),
)


class AddTextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    text: str = Field(..., description="Text content to display")
    style: str = Field(
        default="branding.body",
        description="Text style: branding.title | branding.subtitle | "
                    "branding.body | branding.code | branding.caption")
    x: Any = Field(default=60, description="X position: int pixels or 'center'/'right-N'")
    y: Any = Field(default=60, description="Y position: int pixels or 'center'/'bottom-N'")
    z: int = Field(default=1, ge=0, le=100, description="Z-index (higher = in front)")
    start: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)
    appear: Optional[dict] = _EFFECT_FIELD
    disappear: Optional[dict] = _EFFECT_FIELD


@mcp.tool(
    name="vlog_timeline_add_text",
    annotations={"title": "Add Text Object", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_text(params: AddTextInput) -> str:
    """Add a text overlay to the composition timeline."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_text(tl, params.text, params.style,
                               params.x, params.y, params.z,
                               params.start, params.duration,
                               params.appear, params.disappear)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddImageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    asset_id: str = Field(..., description="Asset ID of the image")
    x: Any = Field(default=60)
    y: Any = Field(default=60)
    z: int = Field(default=1, ge=0)
    start: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)
    width: Optional[int] = Field(default=None, gt=0, description="Resize to this width (px), keeping aspect ratio")
    appear: Optional[dict] = _EFFECT_FIELD
    disappear: Optional[dict] = _EFFECT_FIELD


@mcp.tool(
    name="vlog_timeline_add_image",
    annotations={"title": "Add Image Object", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_image(params: AddImageInput) -> str:
    """Add an image overlay (screenshot, diagram, AI image) to the timeline."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_image(tl, params.asset_id, params.x, params.y, params.z,
                                params.start, params.duration, params.width,
                                params.appear, params.disappear)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddCodeBlockInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    asset_id: str = Field(..., description="Asset ID of a code_snapshot, code_diff, or terminal_capture")
    x: Any = Field(default=40)
    y: Any = Field(default=200)
    z: int = Field(default=2, ge=0)
    start: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)
    width: Optional[int] = Field(default=None, description="Optional resize width in pixels")
    appear: Optional[dict] = _EFFECT_FIELD
    disappear: Optional[dict] = _EFFECT_FIELD


@mcp.tool(
    name="vlog_timeline_add_code_block",
    annotations={"title": "Add Code Block Object", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_code_block(params: AddCodeBlockInput) -> str:
    """Add a code/diff/terminal image as an overlay object on the timeline."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_code_block(tl, params.asset_id, params.x, params.y,
                                     params.z, params.start, params.duration,
                                     params.width, params.appear, params.disappear)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddLowerThirdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    title: str = Field(..., description="Main line, e.g. 'Kirill Kostenko'")
    subtitle: str = Field(..., description="Second line, e.g. 'Backend Engineer'")
    start: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)
    z: int = Field(default=10, ge=0)
    appear: Optional[dict] = _EFFECT_FIELD
    disappear: Optional[dict] = _EFFECT_FIELD


@mcp.tool(
    name="vlog_timeline_add_lower_third",
    annotations={"title": "Add Lower Third", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_lower_third(params: AddLowerThirdInput) -> str:
    """
    Add a branded lower-third (author name + title) overlay.
    Styled using branding configuration. Always use a high z-index (≥10).
    """
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_lower_third(tl, params.title, params.subtitle,
                                      params.start, params.duration, params.z,
                                      params.appear, params.disappear)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddPlateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    plate: str = Field(..., description="Plate name from branding: section_card | quote_card | fact_card | cta_card")
    text: str = Field(..., description="Text to render on the plate")
    x: Any = Field(default=60)
    y: Any = Field(default=60)
    z: int = Field(default=5, ge=0)
    start: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)
    appear: Optional[dict] = _EFFECT_FIELD
    disappear: Optional[dict] = _EFFECT_FIELD


@mcp.tool(
    name="vlog_timeline_add_plate",
    annotations={"title": "Add Branding Plate", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_plate(params: AddPlateInput) -> str:
    """Add a pre-designed branding card (plate) with custom text."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_plate(tl, params.plate, params.text,
                                params.x, params.y, params.z,
                                params.start, params.duration,
                                params.appear, params.disappear)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddMemeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    lib_id: str = Field(..., description="Library item ID (from vlog_library_search)")
    x: Any = Field(default="right-160")
    y: Any = Field(default="bottom-160")
    z: int = Field(default=2, ge=0)
    start: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)
    width: Optional[int] = Field(default=140, description="Width in pixels")
    appear: Optional[dict] = _EFFECT_FIELD
    disappear: Optional[dict] = _EFFECT_FIELD


@mcp.tool(
    name="vlog_timeline_add_meme",
    annotations={"title": "Add Meme", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_meme(params: AddMemeInput) -> str:
    """Add a meme image/GIF from the library as an overlay object."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_meme(tl, params.lib_id, params.x, params.y, params.z,
                               params.start, params.duration, params.width,
                               params.appear, params.disappear)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddStickerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    lib_id: str = Field(..., description="Library sticker item ID")
    x: Any = Field(default="center")
    y: Any = Field(default="center")
    z: int = Field(default=3, ge=0)
    start: float = Field(..., ge=0)
    duration: Optional[float] = Field(default=None, description="Duration (auto-detected from GIF if omitted)")
    scale: float = Field(default=1.0, gt=0, description="Scale multiplier")
    appear: Optional[dict] = _EFFECT_FIELD
    disappear: Optional[dict] = _EFFECT_FIELD


@mcp.tool(
    name="vlog_timeline_add_sticker",
    annotations={"title": "Add Sticker", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_sticker(params: AddStickerInput) -> str:
    """Add an animated sticker (GIF) from the library as an overlay."""
    try:
        tl = _require_timeline(params.project_id)
        dur = params.duration
        if dur is None:
            item = _library.get(params.lib_id)
            dur = item.duration or 2.0 if item else 2.0
        eid = tl_ops.add_sticker(tl, params.lib_id, params.x, params.y, params.z,
                                  params.start, dur, params.scale,
                                  params.appear, params.disappear)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddProgressBarInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    current: int = Field(..., ge=1, description="Current step number")
    total: int = Field(..., ge=1, description="Total number of steps")
    x: Any = Field(default=0)
    y: Any = Field(default="bottom-8")
    z: int = Field(default=8, ge=0)
    start: float = Field(..., ge=0)
    duration: float = Field(..., gt=0)
    appear: Optional[dict] = _EFFECT_FIELD
    disappear: Optional[dict] = _EFFECT_FIELD


@mcp.tool(
    name="vlog_timeline_add_progress_bar",
    annotations={"title": "Add Progress Bar", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_progress_bar(params: AddProgressBarInput) -> str:
    """Add a step progress bar (e.g. Step 2 of 4) at the bottom of the frame."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_progress_bar(tl, params.current, params.total,
                                       params.x, params.y, params.z,
                                       params.start, params.duration,
                                       params.appear, params.disappear)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


# ── audio ─────────────────────────────────────────────────────────────────────

class AddAudioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    asset_id: str = Field(..., description="Asset ID of a TTS or imported audio file")
    start: float = Field(..., ge=0)
    volume: float = Field(default=1.0, gt=0, le=2.0)
    mix: str = Field(default="duck_main",
                     description="Mixing mode: duck_main | add | replace")


@mcp.tool(
    name="vlog_timeline_add_audio",
    annotations={"title": "Add Audio", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_audio(params: AddAudioInput) -> str:
    """Add a TTS or audio asset to the audio track."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_audio(tl, params.asset_id, params.start, params.volume, params.mix)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddSFXInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    lib_id: str = Field(..., description="Library SFX item ID")
    start: float = Field(..., ge=0)
    volume: float = Field(default=0.7, gt=0, le=2.0)


@mcp.tool(
    name="vlog_timeline_add_sfx",
    annotations={"title": "Add Sound Effect", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_sfx(params: AddSFXInput) -> str:
    """Add a sound effect from the library at a specific point in the timeline."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_sfx(tl, params.lib_id, params.start, params.volume)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddMusicInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    lib_id: str = Field(..., description="Library music item ID")
    start: float = Field(default=0.0, ge=0)
    volume: float = Field(default=0.15, gt=0, le=1.0)
    loop: bool = Field(default=True, description="Loop the track if it ends before the video")


@mcp.tool(
    name="vlog_timeline_add_music",
    annotations={"title": "Add Background Music", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_music(params: AddMusicInput) -> str:
    """Add background music from the library. Recommended volume: 0.10–0.20."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_music(tl, params.lib_id, params.start, params.volume, params.loop)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class AddTransitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    after_bg_id: str = Field(..., description="Element ID of the background element BEFORE the transition")
    type: str = Field(..., description="Transition type: fade | wipeleft | wiperight | slideleft | slideright | circleopen | pixelize")
    duration: float = Field(default=0.5, gt=0, le=3.0)


@mcp.tool(
    name="vlog_timeline_add_transition",
    annotations={"title": "Add Transition", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_timeline_add_transition(params: AddTransitionInput) -> str:
    """Add a transition effect between two consecutive background elements."""
    try:
        tl = _require_timeline(params.project_id)
        eid = tl_ops.add_transition(tl, params.after_bg_id, params.type, params.duration)
        _save_tl(params.project_id, tl)
        return json.dumps({"ok": True, "element_id": eid})
    except Exception as exc:
        return _err(str(exc))


class RemoveElementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    element_id: str = Field(..., description="ID of the element to remove")


@mcp.tool(
    name="vlog_timeline_remove",
    annotations={"title": "Remove Timeline Element", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_timeline_remove(params: RemoveElementInput) -> str:
    """Remove any element (background, object, audio, or transition) from the timeline."""
    try:
        tl = _require_timeline(params.project_id)
        found = tl_ops.remove_element(tl, params.element_id)
        if not found:
            return _err(f"Element '{params.element_id}' not found in timeline.")
        _save_tl(params.project_id, tl)
        return _ok(f"Element '{params.element_id}' removed.")
    except Exception as exc:
        return _err(str(exc))


# ── inspect ───────────────────────────────────────────────────────────────────

class TimelineInspectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    from_sec: Optional[float] = Field(default=None, description="Start of time window to inspect")
    to_sec: Optional[float] = Field(default=None, description="End of time window")


@mcp.tool(
    name="vlog_timeline_inspect",
    annotations={"title": "Inspect Timeline", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_timeline_inspect(params: TimelineInspectInput) -> str:
    """
    Return a human-readable text layout of the composition timeline.
    Shows all background elements, objects, audio, and transitions
    with their positions and time ranges.

    Use this to review the current state of the timeline before rendering.
    """
    try:
        tl = _require_timeline(params.project_id)
        return tl_ops.inspect(tl, params.from_sec, params.to_sec)
    except Exception as exc:
        return _err(str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PREVIEW
# ═══════════════════════════════════════════════════════════════════════════════

class PreviewFrameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    at_seconds: float = Field(..., ge=0, description="Time position in the final video to preview")


@mcp.tool(
    name="vlog_preview_frame",
    annotations={"title": "Preview Frame", "readOnlyHint": True,
                 "destructiveHint": False, "idempotentHint": True}
)
async def vlog_preview_frame(params: PreviewFrameInput) -> str:
    """
    Render a single frame of the composition timeline at the given time position.
    Returns a base64-encoded PNG. Fast operation (~200ms) – use iteratively
    after each timeline change to verify the result visually.

    Returns:
        JSON: { ok, at_seconds, base64_png }
    """
    try:
        from .preview import preview_frame as _preview

        tl = _require_timeline(params.project_id)
        proj_dir = _project_dir(params.project_id)
        b64 = _preview(tl, params.at_seconds, proj_dir, _branding, _library)
        return json.dumps({"ok": True, "at_seconds": params.at_seconds, "base64_png": b64})
    except Exception as exc:
        return _err(str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# 7. RENDER
# ═══════════════════════════════════════════════════════════════════════════════

class RenderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    quality: str = Field(default="1080p", description="Output quality: 720p | 1080p | 4k")
    apply_branding: bool = Field(
        default=True,
        description=(
            "Apply branding from branding.json: prepend intro clip, append outro clip, "
            "stamp watermark. Set to false to export a clean/raw video without any branding "
            "(useful for drafts, internal reviews, or projects without a branding config)."
        ),
    )


@mcp.tool(
    name="vlog_render",
    annotations={"title": "Render Video", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_render(params: RenderInput) -> str:
    """
    Render the composition timeline to a final MP4 video.

    Pipeline: background track → object overlays → audio mixing → [branding].

    Branding (apply_branding=true, default):
      • Prepends intro clip from branding.json
      • Appends outro clip from branding.json
      • Stamps watermark from branding.json

    No branding (apply_branding=false):
      • Outputs clean video with no intro/outro/watermark
      • Useful for drafts, internal reviews, or brandingless projects

    This is a blocking operation. For long videos, expect several minutes.
    Requires ffmpeg in PATH.

    Returns:
        JSON: { ok, output_path, branding_applied }
    """
    try:
        tl = _require_timeline(params.project_id)
        proj_dir = _project_dir(params.project_id)
        am = _assets_map(params.project_id)
        output_path = do_render(
            tl, proj_dir, am, _branding, params.quality,
            apply_branding=params.apply_branding,
        )
        _store.update_project(params.project_id, status="rendered")
        return json.dumps({
            "ok": True,
            "output_path": str(output_path),
            "branding_applied": params.apply_branding,
        })
    except Exception as exc:
        return _err(str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# 8. PUBLISH
# ═══════════════════════════════════════════════════════════════════════════════

class PublishInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(..., description="Target project ID")
    platform: str = Field(..., description="Publishing platform: telegram")
    caption: str = Field(default="", description="Caption / description for the post")
    video_path: Optional[str] = Field(
        default=None,
        description="Absolute path to video file. If omitted, uses the latest render.")
    chat_id: Optional[str] = Field(
        default=None,
        description="Telegram chat/channel ID. Falls back to VLOG_MCP_TELEGRAM_CHAT_ID.")


@mcp.tool(
    name="vlog_publish",
    annotations={"title": "Publish Video", "readOnlyHint": False,
                 "destructiveHint": False, "idempotentHint": False}
)
async def vlog_publish(params: PublishInput) -> str:
    """
    Publish the rendered video to Telegram (or other configured platforms).
    Requires bot token and chat ID in env vars or as parameters.

    Returns:
        JSON: { ok, platform, message_id? }
    """
    try:
        # Resolve video path
        if params.video_path:
            video_path = Path(params.video_path)
        else:
            exports_dir = _project_dir(params.project_id) / "exports"
            mp4_files = sorted(exports_dir.glob("*.mp4"),
                               key=lambda p: p.stat().st_mtime, reverse=True)
            if not mp4_files:
                return _err("No rendered video found. Call vlog_render first.")
            video_path = mp4_files[0]

        chat_id = params.chat_id or _cfg.telegram_default_chat_id

        if params.platform == "telegram":
            result = await publish_telegram(
                video_path, _cfg.telegram_bot_token, chat_id, params.caption
            )
            _store.update_project(params.project_id, status="published")
            return json.dumps({"ok": True, "platform": "telegram",
                               "message_id": result.get("result", {}).get("message_id")})
        else:
            return _err(f"Unsupported platform: '{params.platform}'. Supported: telegram")
    except Exception as exc:
        return _err(str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
