"""
preview_frame: Render a single frame of the composition timeline as a PNG.
Uses Pillow for fast compositing (no video encoding).
"""

from __future__ import annotations

import base64
import io
import subprocess
from pathlib import Path
from typing import Any

from .config import BrandingConfig, LibraryConfig
from .timeline import background_at, objects_at


# ─── resolution ──────────────────────────────────────────────────────────────

CANVAS_W = 1920
CANVAS_H = 1080


# ─── helpers ─────────────────────────────────────────────────────────────────

def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _resolve_xy(x: Any, y: Any, obj_w: int = 0, obj_h: int = 0) -> tuple[int, int]:
    """Convert anchor expressions like 'right-20', 'center', 'bottom-120' to pixels."""
    def _axis(val: Any, total: int, obj_size: int) -> int:
        if isinstance(val, int):
            return val
        s = str(val).strip()
        if s == "center":
            return (total - obj_size) // 2
        if s.startswith("right"):
            offset = int(s.split("-")[1]) if "-" in s else 0
            return total - obj_size - offset
        if s.startswith("bottom"):
            offset = int(s.split("-")[1]) if "-" in s else 0
            return total - obj_size - offset
        if s.startswith("left") and "+" in s:
            return int(s.split("+")[1])
        if s.startswith("top") and "+" in s:
            return int(s.split("+")[1])
        try:
            return int(s)
        except ValueError:
            return 0

    px = _axis(x, CANVAS_W, obj_w)
    py = _axis(y, CANVAS_H, obj_h)
    return px, py


def _load_font(size: int, bold: bool = False, mono: bool = False):
    from PIL import ImageFont
    candidates: list[str] = []
    if mono:
        candidates = [
            "C:/Windows/Fonts/cour.ttf",
            "/System/Library/Fonts/Courier New.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        ]
    elif bold:
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _extract_video_frame(video_path: Path, at: float) -> bytes | None:
    """Extract a single frame from a video at `at` seconds using ffmpeg."""
    cmd = [
        "ffmpeg", "-ss", str(at), "-i", str(video_path),
        "-vframes", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1",
        "-loglevel", "error",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except Exception:
        pass
    return None


# ─── main function ───────────────────────────────────────────────────────────

def preview_frame(
    timeline: dict[str, Any],
    at: float,
    project_dir: Path,
    branding: BrandingConfig,
    library: LibraryConfig,
) -> str:
    """
    Render a single frame of the composition at `at` seconds.
    Returns a base64-encoded PNG string.
    """
    from PIL import Image, ImageDraw

    # ── 1. background ───────────────────────────────────────────────────────
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (18, 18, 25))
    bg = background_at(timeline, at)

    if bg:
        btype = bg.get("type", "color")

        if btype == "clip":
            raw_path = project_dir / "captures"
            # find the actual capture file from asset_id - look in assets.json
            # For simplicity, try common paths
            asset_id = bg.get("asset_id", "")
            source_in = bg.get("source_in", 0.0)
            frame_ts = source_in + (at - bg.get("start", 0.0))
            # Search for the file
            for f in (project_dir / "captures").glob("*.mp4"):
                frame_bytes = _extract_video_frame(f, frame_ts)
                if frame_bytes:
                    frame_img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
                    canvas.paste(frame_img.resize((CANVAS_W, CANVAS_H), Image.LANCZOS))
                    break

        elif btype == "color":
            color = bg.get("color", "#121219")
            canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), _hex_rgb(color))

        elif btype == "image":
            asset_id = bg.get("asset_id", "")
            # Search project for this asset
            img_path = _find_asset_file(project_dir, asset_id)
            if img_path:
                try:
                    bg_img = Image.open(img_path).convert("RGB")
                    canvas.paste(bg_img.resize((CANVAS_W, CANVAS_H), Image.LANCZOS))
                except Exception:
                    pass

        elif btype == "cutaway":
            source = bg.get("source", "")
            ref_id = bg.get("ref_id", "")
            if source == "library":
                item = library.get(ref_id)
                if item:
                    lib_path = library.abs_path(item)
                    cutaway_ts = at - bg.get("start", 0.0)
                    frame_bytes = _extract_video_frame(lib_path, cutaway_ts)
                    if frame_bytes:
                        frame_img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
                        canvas.paste(frame_img.resize((CANVAS_W, CANVAS_H), Image.LANCZOS))
            elif source == "branding":
                cut_path = _find_branding_cutaway(branding, ref_id)
                if cut_path:
                    cutaway_ts = at - bg.get("start", 0.0)
                    frame_bytes = _extract_video_frame(Path(cut_path), cutaway_ts)
                    if frame_bytes:
                        frame_img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
                        canvas.paste(frame_img.resize((CANVAS_W, CANVAS_H), Image.LANCZOS))

    draw = ImageDraw.Draw(canvas)

    # ── 2. objects (sorted by z) ────────────────────────────────────────────
    for obj in objects_at(timeline, at):
        _draw_object(canvas, draw, obj, project_dir, branding, library)

    # ── 3. encode to base64 ─────────────────────────────────────────────────
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ─── object renderers ─────────────────────────────────────────────────────────

def _style_to_font(style: str, branding: BrandingConfig):
    key = style.replace("branding.", "")
    fc = branding.font(key)
    bold = key in ("title", "subtitle")
    mono = key == "code"
    return _load_font(fc.size, bold=bold, mono=mono), fc.color


def _draw_object(
    canvas, draw, obj: dict,
    project_dir: Path,
    branding: BrandingConfig,
    library: LibraryConfig,
) -> None:
    from PIL import Image

    t = obj.get("type", "")

    if t == "text":
        text  = obj.get("text", "")
        style = obj.get("style", "branding.body")
        font, color = _style_to_font(style, branding)
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            tw, th = len(text) * 14, 30
        px, py = _resolve_xy(obj.get("x", 60), obj.get("y", 60), tw, th)
        draw.text((px, py), text, fill=color, font=font)

    elif t in ("image", "code_block"):
        asset_id = obj.get("asset_id", "")
        img_path = _find_asset_file(project_dir, asset_id)
        if img_path:
            try:
                overlay = Image.open(img_path).convert("RGBA")
                w = obj.get("width") or overlay.width
                ratio = w / overlay.width
                h = int(overlay.height * ratio)
                overlay = overlay.resize((w, h), Image.LANCZOS)
                px, py = _resolve_xy(obj.get("x", 0), obj.get("y", 0), w, h)
                canvas.paste(overlay, (px, py), mask=overlay.split()[3] if overlay.mode == "RGBA" else None)
            except Exception:
                pass

    elif t == "lower_third":
        title    = obj.get("title", "")
        subtitle = obj.get("subtitle", "")
        # Draw a semi-transparent dark bar at bottom
        bar_h = 100
        bar_y = CANVAS_H - bar_h - 20
        overlay = Image.new("RGBA", (CANVAS_W, bar_h), (0, 0, 0, 180))
        canvas.paste(overlay, (0, bar_y), mask=overlay.split()[3])

        # Re-acquire draw after paste
        draw2 = draw  # same draw object, canvas was mutated
        title_font, _ = _style_to_font("branding.body", branding)
        cap_font, cap_color = _style_to_font("branding.caption", branding)
        draw2.text((60, bar_y + 12), title, fill="#FFFFFF", font=title_font)
        draw2.text((60, bar_y + 52), subtitle, fill=cap_color, font=cap_font)

    elif t == "plate":
        plate_name = obj.get("plate", "")
        text = obj.get("text", "")
        pc = branding.plate(plate_name)
        if pc and Path(pc.asset).exists():
            try:
                plate_img = Image.open(pc.asset).convert("RGBA")
                px, py = _resolve_xy(obj.get("x", 60), obj.get("y", 60),
                                     plate_img.width, plate_img.height)
                canvas.paste(plate_img, (px, py), mask=plate_img.split()[3])
                font, color = _style_to_font(f"branding.{pc.text_style}", branding)
                draw.text((px + pc.text_x, py + pc.text_y), text, fill=color, font=font)
            except Exception:
                _draw_fallback_plate(draw, obj, text, branding)
        else:
            _draw_fallback_plate(draw, obj, text, branding)

    elif t in ("meme", "sticker"):
        lib_id = obj.get("lib_id", "")
        item = library.get(lib_id)
        if item:
            lib_path = library.abs_path(item)
            if lib_path.exists():
                try:
                    meme_img = Image.open(lib_path).convert("RGBA")
                    w = obj.get("width") or int(meme_img.width * obj.get("scale", 1.0))
                    ratio = w / meme_img.width
                    h = int(meme_img.height * ratio)
                    meme_img = meme_img.resize((w, h), Image.LANCZOS)
                    px, py = _resolve_xy(obj.get("x", 0), obj.get("y", 0), w, h)
                    canvas.paste(meme_img, (px, py),
                                 mask=meme_img.split()[3] if meme_img.mode == "RGBA" else None)
                except Exception:
                    pass

    elif t == "progress_bar":
        current = obj.get("current", 1)
        total   = obj.get("total", 1)
        pct     = current / max(total, 1)
        bar_w   = CANVAS_W - 40
        bar_h   = 8
        py      = CANVAS_H - bar_h - 8
        draw.rectangle([20, py, 20 + bar_w, py + bar_h], fill="#333344")
        draw.rectangle([20, py, 20 + int(bar_w * pct), py + bar_h], fill="#5B8DEF")


def _draw_fallback_plate(draw, obj: dict, text: str, branding: BrandingConfig) -> None:
    """Draw a simple coloured rectangle as a plate fallback."""
    px, py = _resolve_xy(obj.get("x", 60), obj.get("y", 60))
    font, _ = _style_to_font("branding.subtitle", branding)
    color = branding.palette.get("primary", "#5B8DEF")
    draw.rectangle([px, py, px + 700, py + 70], fill=color)
    draw.text((px + 20, py + 16), text, fill="#FFFFFF", font=font)


def _find_asset_file(project_dir: Path, asset_id: str) -> Path | None:
    """Look up an asset's file path from assets.json."""
    import json
    assets_path = project_dir / "assets.json"
    if not assets_path.exists():
        return None
    try:
        data = json.loads(assets_path.read_text(encoding="utf-8"))
        for a in data:
            if a.get("asset_id") == asset_id:
                return project_dir / a["path"]
    except Exception:
        pass
    return None


def _find_branding_cutaway(branding: BrandingConfig, ref_id: str) -> str | None:
    for c in branding.cutaways():
        if c.id == ref_id:
            return c.path
    return None
