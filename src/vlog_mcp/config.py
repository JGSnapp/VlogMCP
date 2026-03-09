"""
Configuration loading: app settings, branding, and media library.
All configuration is read-only for the AI agent.

Configuration is loaded from a JSON file (vlog-mcp.json by default).
Location lookup order:
  1. Explicit path passed to AppConfig.load(config_path=...)
  2. VLOG_MCP_CONFIG environment variable
  3. ./vlog-mcp.json  (next to the working directory)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default config file name, resolved relative to CWD at startup
_DEFAULT_CONFIG_FILE = "vlog-mcp.json"


# ─── app config ──────────────────────────────────────────────────────────────

@dataclass
class AppConfig:
    workspace_path: Path
    branding_path: Path
    library_path: Path
    # TTS / LLM — OpenAI or compatible proxy
    openai_api_key: str
    openai_base_url: str            # custom base URL for proxy (e.g. proxyapi.ru)
    elevenlabs_api_key: str
    # Image / video generation
    stability_api_key: str          # Stability AI (SDXL / SD3 / Stable Audio)
    runway_api_key: str             # Runway Gen-3/Gen-4 video generation
    luma_api_key: str               # Luma AI Dream Machine video generation
    kling_api_key: str              # Kling AI video generation
    # Music generation
    replicate_api_key: str          # Replicate (MusicGen, Riffusion, etc.)
    # Publishing
    telegram_bot_token: str
    telegram_default_chat_id: str

    @classmethod
    def load(cls, config_path: Path | None = None) -> "AppConfig":
        """
        Load configuration from a JSON file.

        config_path — explicit override; if None, the file is located via:
          1. VLOG_MCP_CONFIG env var
          2. ./vlog-mcp.json

        The JSON file uses a nested structure (see vlog-mcp.example.json).
        Any key that is missing or empty falls back to its old env-var name
        so that CI/CD pipelines that set env vars keep working.
        """
        if config_path is None:
            env_cfg = os.environ.get("VLOG_MCP_CONFIG", "")
            config_path = Path(env_cfg) if env_cfg else Path(_DEFAULT_CONFIG_FILE)

        raw: dict[str, Any] = {}
        if config_path.exists():
            raw = json.loads(config_path.read_text(encoding="utf-8"))

        def _str(keys: list[str], env_var: str, default: str = "") -> str:
            """
            Navigate *keys* as a path through the nested raw dict.
            Falls back to *env_var*, then *default*.
            """
            node: Any = raw
            for k in keys:
                if not isinstance(node, dict):
                    node = None
                    break
                node = node.get(k)
            if node is not None and str(node).strip():
                return str(node).strip()
            return os.environ.get(env_var, default)

        workspace = Path(_str(["workspace"],    "VLOG_MCP_WORKSPACE",    "./vlog-workspace"))
        branding  = Path(_str(["branding_path"],"VLOG_MCP_BRANDING_PATH","./branding/branding.json"))
        library   = Path(_str(["library_path"], "VLOG_MCP_LIBRARY_PATH", "./library/index.json"))

        return cls(
            workspace_path=workspace.resolve(),
            branding_path=branding.resolve(),
            library_path=library.resolve(),
            openai_api_key=_str(["openai",       "api_key"],   "VLOG_MCP_OPENAI_KEY"),
            openai_base_url=_str(["openai",      "base_url"],  "VLOG_MCP_OPENAI_BASE_URL"),
            elevenlabs_api_key=_str(["elevenlabs","api_key"],  "VLOG_MCP_ELEVENLABS_KEY"),
            stability_api_key=_str(["stability",  "api_key"],  "VLOG_MCP_STABILITY_KEY"),
            runway_api_key=_str(["video_gen",     "runway_api_key"], "VLOG_MCP_RUNWAY_KEY"),
            luma_api_key=_str(["video_gen",       "luma_api_key"],   "VLOG_MCP_LUMA_KEY"),
            kling_api_key=_str(["video_gen",      "kling_api_key"],  "VLOG_MCP_KLING_KEY"),
            replicate_api_key=_str(["music_gen",  "replicate_api_key"], "VLOG_MCP_REPLICATE_KEY"),
            telegram_bot_token=_str(["telegram",  "bot_token"], "VLOG_MCP_TELEGRAM_TOKEN"),
            telegram_default_chat_id=_str(["telegram","chat_id"],"VLOG_MCP_TELEGRAM_CHAT_ID"),
        )

    # Keep the old name as an alias so nothing breaks if someone calls it
    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls.load()


# ─── branding config ─────────────────────────────────────────────────────────

@dataclass
class FontConfig:
    family: str
    size: int
    color: str = "#FFFFFF"


@dataclass
class WatermarkConfig:
    asset: str
    position: str
    margin_x: int
    margin_y: int
    opacity: float
    scale: float


@dataclass
class PlateConfig:
    asset: str
    text_x: int
    text_y: int
    text_style: str
    description: str = ""


@dataclass
class CutawayEntry:
    id: str
    path: str
    duration: float
    tags: list[str] = field(default_factory=list)


@dataclass
class BrandingConfig:
    branding_id: str
    palette: dict[str, str]
    fonts: dict[str, FontConfig]
    watermark: WatermarkConfig | None
    clips: dict[str, Any]       # intro, outro, cutaways
    plates: dict[str, PlateConfig]
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def cutaways(self) -> list[CutawayEntry]:
        entries = []
        for c in self.clips.get("cutaways", []):
            entries.append(CutawayEntry(
                id=c["id"], path=c["path"],
                duration=c.get("duration", 3.0),
                tags=c.get("tags", []),
            ))
        return entries

    def plate(self, name: str) -> PlateConfig | None:
        return self.plates.get(name)

    def font(self, style_key: str) -> FontConfig:
        """style_key: title | subtitle | body | code | caption"""
        return self.fonts.get(style_key, FontConfig("", 28, "#FFFFFF"))

    def to_dict(self) -> dict[str, Any]:
        return self._raw

    @classmethod
    def load(cls, path: Path) -> "BrandingConfig":
        if not path.exists():
            return cls._default()

        raw = json.loads(path.read_text(encoding="utf-8"))

        fonts = {}
        for k, v in raw.get("fonts", {}).items():
            fonts[k] = FontConfig(
                family=v.get("family", ""),
                size=v.get("size", 28),
                color=v.get("color", "#FFFFFF"),
            )

        wm_raw = raw.get("watermark")
        watermark = None
        if wm_raw:
            watermark = WatermarkConfig(
                asset=wm_raw.get("asset", ""),
                position=wm_raw.get("position", "bottom_right"),
                margin_x=wm_raw.get("margin_x", 24),
                margin_y=wm_raw.get("margin_y", 24),
                opacity=wm_raw.get("opacity", 0.6),
                scale=wm_raw.get("scale", 0.07),
            )

        plates = {}
        for k, v in raw.get("plates", {}).items():
            plates[k] = PlateConfig(
                asset=v.get("asset", ""),
                text_x=v.get("text_x", 60),
                text_y=v.get("text_y", 40),
                text_style=v.get("text_style", "body"),
                description=v.get("description", ""),
            )

        return cls(
            branding_id=raw.get("branding_id", "default"),
            palette=raw.get("palette", {}),
            fonts=fonts,
            watermark=watermark,
            clips=raw.get("clips", {}),
            plates=plates,
            _raw=raw,
        )

    @classmethod
    def _default(cls) -> "BrandingConfig":
        return cls(
            branding_id="default",
            palette={
                "primary": "#5B8DEF", "accent": "#FF5F7E",
                "background": "#121219", "text": "#FFFFFF",
                "muted": "#8899AA",
            },
            fonts={
                "title":    FontConfig("", 64, "#FFFFFF"),
                "subtitle": FontConfig("", 42, "#FFFFFF"),
                "body":     FontConfig("", 28, "#E2E8F0"),
                "code":     FontConfig("", 24, "#A3E635"),
                "caption":  FontConfig("", 22, "#8899AA"),
            },
            watermark=None,
            clips={},
            plates={},
        )


# ─── library config ──────────────────────────────────────────────────────────

@dataclass
class LibraryItem:
    id: str
    path: str
    kind: str           # image | gif | mp3 | mp4
    category: str       # meme | sfx | sticker | cutaway | music
    tags: list[str]
    description: str
    duration: float | None
    bpm: int | None
    mood: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "kind": self.kind,
            "category": self.category,
            "tags": self.tags,
            "description": self.description,
            "duration": self.duration,
            "bpm": self.bpm,
            "mood": self.mood,
        }


@dataclass
class LibraryConfig:
    items: list[LibraryItem]
    library_dir: Path

    def search(self, query: str, category: str | None = None) -> list[LibraryItem]:
        q = query.lower()
        results = []
        for item in self.items:
            if category and item.category != category:
                continue
            text = " ".join([item.id, item.description] + item.tags).lower()
            if any(word in text for word in q.split()):
                results.append(item)
        return results

    def list_by_category(self, category: str | None = None) -> list[LibraryItem]:
        if category is None:
            return self.items
        return [i for i in self.items if i.category == category]

    def get(self, lib_id: str) -> LibraryItem | None:
        for item in self.items:
            if item.id == lib_id:
                return item
        return None

    def abs_path(self, item: LibraryItem) -> Path:
        return self.library_dir / item.path

    @classmethod
    def load(cls, path: Path) -> "LibraryConfig":
        library_dir = path.parent
        if not path.exists():
            return cls(items=[], library_dir=library_dir)

        raw = json.loads(path.read_text(encoding="utf-8"))
        items: list[LibraryItem] = []

        category_map = {
            "memes": "meme",
            "sfx": "sfx",
            "stickers": "sticker",
            "cutaways": "cutaway",
            "music": "music",
        }

        kind_map = {
            "meme": "image",
            "sfx": "audio",
            "sticker": "gif",
            "cutaway": "video",
            "music": "audio",
        }

        for cat_key, cat_name in category_map.items():
            for entry in raw.get(cat_key, []):
                item_path = library_dir / entry["path"]
                # Use index.json value if present; otherwise probe the actual file
                duration = entry.get("duration")
                if duration is None and item_path.exists():
                    duration = _probe_duration(item_path)
                items.append(LibraryItem(
                    id=entry["id"],
                    path=entry["path"],
                    kind=entry.get("kind", kind_map.get(cat_name, "file")),
                    category=cat_name,
                    tags=entry.get("tags", []),
                    description=entry.get("description", ""),
                    duration=duration,
                    bpm=entry.get("bpm"),       # optional, may be None
                    mood=entry.get("mood"),
                ))

        return cls(items=items, library_dir=library_dir)


def _probe_duration(path: Path) -> float | None:
    """
    Probe media duration in seconds.
    Uses ffprobe for audio/video; Pillow for GIFs.
    Returns None if probing fails.
    """
    suffix = path.suffix.lower()
    if suffix == ".gif":
        return _probe_gif_duration(path)
    return _probe_ffprobe_duration(path)


def _probe_ffprobe_duration(path: Path) -> float | None:
    import subprocess
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            dur = stream.get("duration")
            if dur:
                return round(float(dur), 3)
    except Exception:
        pass
    return None


def _probe_gif_duration(path: Path) -> float | None:
    try:
        from PIL import Image
        img = Image.open(path)
        total_ms = 0
        try:
            while True:
                total_ms += img.info.get("duration", 100)  # 100ms default per frame
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        return round(total_ms / 1000.0, 3)
    except Exception:
        return None
