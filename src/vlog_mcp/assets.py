"""
Asset generation: screenshots, code visuals, TTS, diagrams.
All functions return a Path to the generated file.
"""

from __future__ import annotations

import difflib
import io
import json
import re
import textwrap
from pathlib import Path
from typing import Any

import httpx


# ─── fonts (Pillow, with system fallback) ────────────────────────────────────

def _load_font(size: int, bold: bool = False, mono: bool = False):
    """Load a truetype font with graceful fallback to PIL bitmap default."""
    from PIL import ImageFont

    candidates: list[str] = []
    if mono:
        candidates = [
            "JetBrainsMono-Regular.ttf",
            "C:/Windows/Fonts/cour.ttf",
            "/System/Library/Fonts/Courier New.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/ttf-dejavu/DejaVuSansMono.ttf",
        ]
    elif bold:
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# ─── screenshot ───────────────────────────────────────────────────────────────

def screenshot_take(output_path: Path, monitor: int = 1) -> Path:
    """Capture a screenshot of the specified monitor and save as PNG."""
    import mss
    import mss.tools
    with mss.mss() as sct:
        monitors = sct.monitors
        idx = min(monitor, len(monitors) - 1)
        img = sct.grab(monitors[idx])
        mss.tools.to_png(img.rgb, img.size, output=str(output_path))
    return output_path


# ─── code snapshot ────────────────────────────────────────────────────────────

_MONOKAI: dict[str, str] = {
    "keyword":       "#F92672",
    "keyword.type":  "#66D9EF",
    "string":        "#E6DB74",
    "string.doc":    "#75715E",
    "comment":       "#75715E",
    "name.function": "#A6E22E",
    "name.class":    "#A6E22E",
    "name.builtin":  "#66D9EF",
    "number":        "#AE81FF",
    "operator":      "#F8F8F2",
    "default":       "#F8F8F2",
    "background":    "#272822",
    "line_num":      "#75715E",
}

def _token_color(ttype) -> str:
    from pygments import token as T
    if ttype in T.Keyword:
        return _MONOKAI.get("keyword", _MONOKAI["default"])
    if ttype in T.String:
        return _MONOKAI.get("string", _MONOKAI["default"])
    if ttype in T.Comment:
        return _MONOKAI.get("comment", _MONOKAI["default"])
    if ttype in T.Name.Function or ttype in T.Name.Class:
        return _MONOKAI.get("name.function", _MONOKAI["default"])
    if ttype in T.Name.Builtin:
        return _MONOKAI.get("name.builtin", _MONOKAI["default"])
    if ttype in T.Number:
        return _MONOKAI.get("number", _MONOKAI["default"])
    return _MONOKAI["default"]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))  # type: ignore


def _parse_highlight_lines(
    highlight_lines: "list[int | dict] | None",
) -> "dict[int, dict]":
    """
    Normalise highlight_lines into {line_no: {bg, fg}} mapping.

    Accepts:
      - List[int]          → each int gets default bg=#3D3D2E
      - List[int | dict]   → dict must have 'line'; optional 'bg' and 'fg' keys
    """
    result: dict[int, dict] = {}
    for item in (highlight_lines or []):
        if isinstance(item, int):
            result[item] = {"bg": "#3D3D2E", "fg": None}
        elif isinstance(item, dict):
            line_no = int(item.get("line", 0))
            if line_no:
                result[line_no] = {
                    "bg": item.get("bg", "#3D3D2E"),
                    "fg": item.get("fg"),
                }
    return result


def code_snapshot(
    output_path: Path,
    code: str,
    lang: str = "python",
    highlight_lines: "list[int | dict] | None" = None,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """
    Render syntax-highlighted code to a PNG using Pillow + Pygments.

    highlight_lines accepts:
      - List[int]   — highlight those line numbers with default yellow-tint bg
      - List[dict]  — each dict: {"line": N, "bg": "#hexcolor", "fg": "#hexcolor"}
                      'fg' overrides the text color for that entire line.
    """
    from PIL import Image, ImageDraw
    from pygments import lex
    from pygments.lexers import get_lexer_by_name, TextLexer
    from pygments.util import ClassNotFound

    try:
        lexer = get_lexer_by_name(lang, stripall=True)
    except ClassNotFound:
        lexer = TextLexer()

    font_size = 22
    font = _load_font(font_size, mono=True)
    line_height = font_size + 6
    padding = 40
    line_num_width = 60

    lines = code.split("\n")
    hl_map = _parse_highlight_lines(highlight_lines)

    img = Image.new("RGB", (width, height), _MONOKAI["background"])
    draw = ImageDraw.Draw(img)

    y = padding
    for line_no, line in enumerate(lines, start=1):
        hl = hl_map.get(line_no)
        # Highlight background for marked lines
        if hl:
            draw.rectangle([0, y - 2, width, y + line_height], fill=hl["bg"])

        # Draw line number
        draw.text((padding, y), f"{line_no:>4}", fill=_MONOKAI["line_num"], font=font)

        # Tokenise and draw code (hl fg overrides per-token syntax color)
        x = padding + line_num_width
        for ttype, value in lex(line, lexer):
            color = hl["fg"] if (hl and hl.get("fg")) else _token_color(ttype)
            draw.text((x, y), value, fill=color, font=font)
            try:
                bbox = draw.textbbox((x, y), value, font=font)
                x += bbox[2] - bbox[0]
            except AttributeError:
                x += len(value) * (font_size // 2)

        y += line_height
        if y > height - padding:
            break

    img.save(str(output_path), "PNG")
    return output_path


# ─── code typewriter ──────────────────────────────────────────────────────────

def code_typewriter(
    output_path: Path,
    code: str,
    lang: str = "python",
    chars_per_second: float = 30.0,
    cursor: bool = True,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """
    Render a typewriter-effect code video to MP4.

    The video shows the code being typed character by character.
    Each frame reveals one or more additional characters depending on
    chars_per_second vs fps.  A blinking block cursor can be enabled.

    Returns path to the output .mp4 file.
    """
    import subprocess
    import tempfile
    from PIL import Image, ImageDraw
    from pygments import lex
    from pygments.lexers import get_lexer_by_name, TextLexer
    from pygments.util import ClassNotFound

    try:
        lexer = get_lexer_by_name(lang, stripall=True)
    except ClassNotFound:
        lexer = TextLexer()

    font_size = 22
    font = _load_font(font_size, mono=True)
    line_height = font_size + 6
    padding = 40
    line_num_width = 60
    bg_color = _MONOKAI["background"]

    # ── frame schedule ───────────────────────────────────────────────────────
    total_chars = len(code)
    # How many characters are revealed per frame
    chars_per_frame = max(1, chars_per_second / fps)
    # Total number of frames to generate
    total_frames = max(1, int(total_chars / chars_per_frame) + fps)  # +fps pause at end

    def _render_frame(visible: int, show_cursor: bool) -> Image.Image:
        """Render the code up to `visible` characters as a PIL Image."""
        snippet = code[:visible]
        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        lines = snippet.split("\n")
        y = padding
        for line_no, line in enumerate(lines, start=1):
            # line number
            draw.text((padding, y), f"{line_no:>4}", fill=_MONOKAI["line_num"], font=font)
            # syntax-highlighted tokens
            x = padding + line_num_width
            # Only tokenise the last (incomplete) line for speed; full lines reuse
            for ttype, value in lex(line, lexer):
                color = _token_color(ttype)
                draw.text((x, y), value, fill=color, font=font)
                try:
                    bbox = draw.textbbox((x, y), value, font=font)
                    x += bbox[2] - bbox[0]
                except AttributeError:
                    x += len(value) * (font_size // 2)
            # cursor on the current (last) line
            if show_cursor and line_no == len(lines):
                draw.rectangle([x, y, x + 12, y + font_size], fill="#F8F8F2")
            y += line_height
            if y > height - padding:
                break
        return img

    # ── generate unique frames → temp dir ────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        frame_paths: list[tuple[Path, int]] = []  # (png_path, repeat_count)

        prev_key: tuple | None = None
        for frame_idx in range(total_frames):
            visible = min(total_chars, int(frame_idx * chars_per_frame))
            # Cursor blinks at ~2 Hz: on for first half of each second, off for second half
            show_cursor = cursor and (frame_idx % fps < fps // 2)
            frame_key = (visible, show_cursor)

            if frame_key != prev_key:
                png_path = tmp / f"frame_{frame_idx:06d}.png"
                img = _render_frame(visible, show_cursor)
                img.save(str(png_path), "PNG")
                frame_paths.append((png_path, 1))
                prev_key = frame_key
            else:
                frame_paths[-1] = (frame_paths[-1][0], frame_paths[-1][1] + 1)

        # ── build concat demuxer file ─────────────────────────────────────
        concat_txt = tmp / "frames.txt"
        with concat_txt.open("w") as f:
            for png_path, repeat in frame_paths:
                duration = repeat / fps
                f.write(f"file '{png_path}'\n")
                f.write(f"duration {duration:.6f}\n")
            # ffmpeg concat demuxer needs a final file entry without duration
            if frame_paths:
                f.write(f"file '{frame_paths[-1][0]}'\n")

        # ── encode to mp4 via ffmpeg ──────────────────────────────────────
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_txt),
            "-vf", f"scale={width}:{height}",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg typewriter encode failed:\n{result.stderr[-2000:]}")

    return output_path


# ─── code diff ────────────────────────────────────────────────────────────────

def code_diff(
    output_path: Path,
    before_text: str,
    after_text: str,
    lang: str = "text",
    title: str = "",
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Render a side-by-side diff as a PNG."""
    from PIL import Image, ImageDraw

    BG     = "#1E1E2E"
    ADD_BG = "#1E3A2F"
    DEL_BG = "#3A1E1E"
    ADD_FG = "#4ADE80"
    DEL_FG = "#F87171"
    CTX_FG = "#C0C0C0"
    HDR_FG = "#8899AA"

    font_size = 20
    font = _load_font(font_size, mono=True)
    line_h = font_size + 5
    pad = 30
    title_h = 50 if title else 0

    diff = list(difflib.unified_diff(
        before_text.splitlines(),
        after_text.splitlines(),
        lineterm="",
    ))

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    if title:
        draw.text((pad, pad // 2), title, fill=HDR_FG, font=_load_font(26, bold=True))

    y = pad + title_h
    for raw_line in diff:
        if y > height - pad:
            break
        if raw_line.startswith("+++") or raw_line.startswith("---"):
            draw.text((pad, y), raw_line[:120], fill=HDR_FG, font=font)
        elif raw_line.startswith("@@"):
            draw.text((pad, y), raw_line[:120], fill=HDR_FG, font=font)
        elif raw_line.startswith("+"):
            draw.rectangle([0, y - 1, width, y + line_h], fill=ADD_BG)
            draw.text((pad, y), raw_line[:160], fill=ADD_FG, font=font)
        elif raw_line.startswith("-"):
            draw.rectangle([0, y - 1, width, y + line_h], fill=DEL_BG)
            draw.text((pad, y), raw_line[:160], fill=DEL_FG, font=font)
        else:
            draw.text((pad, y), raw_line[:160], fill=CTX_FG, font=font)
        y += line_h

    img.save(str(output_path), "PNG")
    return output_path


# ─── terminal capture ─────────────────────────────────────────────────────────

def terminal_capture(
    output_path: Path,
    command: str,
    output_text: str,
    theme: str = "dark",
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Render a terminal output screenshot as a PNG."""
    from PIL import Image, ImageDraw

    BG  = "#0D1117" if theme == "dark" else "#FFFFFF"
    FG  = "#C9D1D9" if theme == "dark" else "#24292F"
    PROMPT_FG = "#58A6FF"
    font_size = 22
    font = _load_font(font_size, mono=True)
    bold_font = _load_font(font_size, bold=True, mono=True)
    line_h = font_size + 6
    pad = 40

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # window chrome (dots)
    for i, color in enumerate(["#FF5F57", "#FEBC2E", "#28C840"]):
        draw.ellipse([pad + i * 22, pad, pad + i * 22 + 14, pad + 14], fill=color)

    y = pad + 30
    # prompt line
    prompt = f"$ {command}"
    draw.text((pad, y), prompt, fill=PROMPT_FG, font=bold_font)
    y += line_h + 4

    for line in output_text.split("\n"):
        if y > height - pad:
            break
        draw.text((pad, y), line[:200], fill=FG, font=font)
        y += line_h

    img.save(str(output_path), "PNG")
    return output_path


# ─── TTS ──────────────────────────────────────────────────────────────────────

async def tts_generate(
    output_path: Path,
    text: str,
    voice: str = "nova",
    api_key: str = "",
    provider: str = "openai",
    model: str = "",
    instructions: str = "",
    base_url: str = "",
) -> Path:
    """
    Generate TTS audio via OpenAI-compatible API or ElevenLabs.

    provider='openai'    — OpenAI /v1/audio/speech or any OpenAI-compatible proxy
                           (set base_url to override endpoint).
    provider='elevenlabs' — ElevenLabs /v1/text-to-speech REST API.
    """
    if provider == "openai" or (not provider):
        await _tts_openai(
            output_path, text, voice, api_key,
            model=model, instructions=instructions, base_url=base_url,
        )
    elif provider == "elevenlabs":
        await _tts_elevenlabs(output_path, text, voice, api_key, model=model)
    else:
        raise ValueError(
            f"Unknown TTS provider: '{provider}'. Supported: 'openai', 'elevenlabs'."
        )
    return output_path


# OpenAI-compatible TTS models (as of 2025-2026)
_OPENAI_TTS_MODELS = {
    "tts-1",              # classic — fast, lower quality
    "tts-1-hd",           # classic — slower, higher quality
    "gpt-4o-mini-tts",    # new — fast + instructions support
    "gpt-4o-tts",         # new — best quality + instructions support
}

# All known voices across generations
_OPENAI_TTS_VOICES = {
    # Classic voices (tts-1 / tts-1-hd)
    "alloy", "echo", "fable", "onyx", "nova", "shimmer",
    # New voices (gpt-4o-mini-tts / gpt-4o-tts)
    "coral", "sage", "ash", "ballad", "verse",
}

_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


async def _tts_openai(
    output_path: Path,
    text: str,
    voice: str,
    api_key: str,
    model: str = "",
    instructions: str = "",
    base_url: str = "",
) -> None:
    """
    Call any OpenAI-compatible /audio/speech endpoint.

    base_url — override for proxy services (e.g. 'https://api.proxyapi.ru/openai/v1').
    model    — auto-selected based on voice if omitted:
                 coral/sage/ash/ballad/verse → gpt-4o-mini-tts
                 everything else             → tts-1
    instructions — voice style prompt, e.g. "Speak with an energetic and upbeat tone."
                   Supported by gpt-4o-mini-tts and gpt-4o-tts only; ignored otherwise.
    """
    if not api_key:
        raise RuntimeError("OpenAI API key not set (VLOG_MCP_OPENAI_KEY).")

    endpoint_base = (base_url or _DEFAULT_OPENAI_BASE_URL).rstrip("/")
    endpoint = f"{endpoint_base}/audio/speech"

    # Auto-select model if not specified
    new_voice_set = {"coral", "sage", "ash", "ballad", "verse"}
    if not model:
        model = "gpt-4o-mini-tts" if voice in new_voice_set else "tts-1"

    payload: dict = {
        "model":           model,
        "input":           text,
        "voice":           voice,
        "response_format": "mp3",
    }
    # instructions only sent for models that support it
    if instructions and model in ("gpt-4o-mini-tts", "gpt-4o-tts"):
        payload["instructions"] = instructions

    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        output_path.write_bytes(resp.content)


async def _tts_elevenlabs(
    output_path: Path,
    text: str,
    voice: str,
    api_key: str,
    model: str = "",
) -> None:
    if not api_key:
        raise RuntimeError("ElevenLabs API key not set (VLOG_MCP_ELEVENLABS_KEY).")
    voice_id = voice if len(voice) > 10 else "EXAVITQu4vr4xnSDxMaL"  # default Sarah
    tts_model = model or "eleven_multilingual_v2"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": api_key},
            json={"text": text, "model_id": tts_model},
        )
        resp.raise_for_status()
        output_path.write_bytes(resp.content)


# ─── diagrams ─────────────────────────────────────────────────────────────────

def diagram_create(
    output_path: Path,
    diagram_type: str,
    data: dict[str, Any],
    title: str = "",
    theme: str = "dark",
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Create a diagram PNG using matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    BG   = "#121219" if theme == "dark" else "#FFFFFF"
    FG   = "#FFFFFF"  if theme == "dark" else "#000000"
    GRID = "#2A2A3A" if theme == "dark" else "#CCCCCC"

    dpi = 96
    fig, ax = plt.subplots(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.tick_params(colors=FG)
    ax.spines[:].set_color(GRID)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(FG)

    if diagram_type == "bar_chart":
        labels = data.get("labels", [])
        values = data.get("values", [])
        color  = data.get("color", "#5B8DEF")
        unit   = data.get("unit", "")
        bars = ax.bar(labels, values, color=color, edgecolor=GRID, linewidth=0.5)
        ax.set_ylabel(unit, color=FG)
        ax.yaxis.grid(True, color=GRID, linestyle="--", linewidth=0.5)
        ax.set_axisbelow(True)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.01,
                    str(val), ha="center", va="bottom", color=FG, fontsize=14)

    elif diagram_type == "pie":
        labels = data.get("labels", [])
        values = data.get("values", [])
        colors = data.get("colors", ["#5B8DEF", "#FF5F7E", "#4ADE80", "#FBBF24", "#A78BFA"])
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct="%1.1f%%",
            colors=colors[:len(values)], startangle=90,
        )
        for t in texts + autotexts:
            t.set_color(FG)

    elif diagram_type == "table":
        columns = data.get("columns", [])
        rows    = data.get("rows", [])
        ax.axis("off")
        tbl = ax.table(cellText=rows, colLabels=columns, loc="center", cellLoc="left")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(14)
        tbl.scale(1, 2)
        for (r, c), cell in tbl.get_celld().items():
            cell.set_facecolor("#1E1E2E" if r % 2 == 0 else "#252535")
            cell.set_text_props(color=FG)
            cell.set_edgecolor(GRID)
    else:
        ax.text(0.5, 0.5, f"Diagram type '{diagram_type}' not supported",
                ha="center", va="center", color=FG, fontsize=18, transform=ax.transAxes)

    if title:
        ax.set_title(title, color=FG, fontsize=20, pad=16)

    plt.tight_layout()
    fig.savefig(str(output_path), dpi=dpi, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ─── AI image generation ──────────────────────────────────────────────────────

async def image_generate(
    output_path: Path,
    prompt: str,
    provider: str = "openai",
    api_key: str = "",
    size: str = "1792x1024",
    quality: str = "standard",
    style: str = "vivid",
    negative_prompt: str = "",
    model: str = "",
) -> Path:
    """
    Generate an image from a text prompt using an AI provider.

    Supported providers:
      • openai     — DALL-E 3 via OpenAI API. Sizes: 1024x1024 | 1792x1024 | 1024x1792.
                     quality: standard | hd.  style: vivid | natural.
                     Requires VLOG_MCP_OPENAI_KEY.

      • stability  — Stability AI (Stable Diffusion 3 / SDXL) via stability.ai REST API.
                     size is used to select aspect_ratio (1792x1024 → 16:9).
                     model defaults to 'stable-diffusion-3-large'.
                     Supports negative_prompt.
                     Requires VLOG_MCP_STABILITY_KEY.

    Returns the path to the saved PNG file.
    """
    if provider in ("openai", ""):
        await _imggen_openai(output_path, prompt, api_key, size, quality, style)
    elif provider == "stability":
        await _imggen_stability(output_path, prompt, api_key, size, negative_prompt, model)
    else:
        raise ValueError(
            f"Unknown image generation provider: '{provider}'. "
            f"Supported: 'openai', 'stability'."
        )
    return output_path


async def _imggen_openai(
    output_path: Path,
    prompt: str,
    api_key: str,
    size: str,
    quality: str,
    style: str,
) -> None:
    """Generate an image with DALL-E 3."""
    if not api_key:
        raise RuntimeError(
            "OpenAI API key not set. Add VLOG_MCP_OPENAI_KEY to your environment."
        )

    # DALL-E 3 supported sizes
    valid_sizes = {"1024x1024", "1792x1024", "1024x1792"}
    if size not in valid_sizes:
        size = "1792x1024"   # landscape default

    payload = {
        "model":   "dall-e-3",
        "prompt":  prompt,
        "n":       1,
        "size":    size,
        "quality": quality if quality in ("standard", "hd") else "standard",
        "style":   style   if style   in ("vivid", "natural") else "vivid",
        "response_format": "url",
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        image_url = data["data"][0]["url"]

        # Download the image
        img_resp = await client.get(image_url, timeout=60.0)
        img_resp.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(img_resp.content)


async def _imggen_stability(
    output_path: Path,
    prompt: str,
    api_key: str,
    size: str,
    negative_prompt: str,
    model: str,
) -> None:
    """Generate an image with Stability AI (SD3 / SDXL)."""
    if not api_key:
        raise RuntimeError(
            "Stability AI API key not set. Add VLOG_MCP_STABILITY_KEY to your environment."
        )

    # Map size string to aspect_ratio
    aspect_map = {
        "1024x1024": "1:1",
        "1792x1024": "16:9",
        "1024x1792": "9:16",
        "1280x720":  "16:9",
        "720x1280":  "9:16",
        "1216x832":  "3:2",
        "832x1216":  "2:3",
    }
    aspect_ratio = aspect_map.get(size, "16:9")
    engine = model or "stable-diffusion-3-large"

    form_data: dict[str, str] = {
        "prompt":       prompt,
        "aspect_ratio": aspect_ratio,
        "output_format": "png",
    }
    if negative_prompt:
        form_data["negative_prompt"] = negative_prompt

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"https://api.stability.ai/v2beta/stable-image/generate/sd3",
            headers={
                "authorization": f"Bearer {api_key}",
                "accept":        "image/*",
            },
            data=form_data,
        )
        resp.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(resp.content)


# ─── asset trim / fade ────────────────────────────────────────────────────────

def asset_trim(
    input_path: Path,
    output_path: Path,
    start: float = 0.0,
    end: float | None = None,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    fade_type: str = "linear",      # linear | exponential (audio only)
) -> Path:
    """
    Trim a media file and apply fade in / fade out using ffmpeg.

    start / end   — trim window in seconds (end=None means until EOF).
    fade_in       — fade-in duration in seconds (0 = no fade).
    fade_out      — fade-out duration in seconds (0 = no fade).
    fade_type     — 'linear' (default) or 'exponential' (audio only, softer tail).

    Works with audio (.mp3/.wav/.aac) and video (.mp4/.mov).
    Returns the output_path.
    """
    import subprocess

    suffix = input_path.suffix.lower()
    is_video = suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi"}
    is_audio = suffix in {".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4a"}

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = ["ffmpeg", "-y", "-i", str(input_path)]
    if start:
        cmd += ["-ss", str(start)]
    if end is not None:
        duration = end - start
        cmd += ["-t", str(duration)]

    # Determine fade-out start relative to trimmed clip start
    if end is not None and fade_out > 0:
        clip_dur = (end - start)
        fade_out_start = max(0.0, clip_dur - fade_out)
    else:
        fade_out_start = None   # applied from EOF backwards — ffmpeg handles it

    audio_filters: list[str] = []
    video_filters: list[str] = []

    if is_audio or is_video:
        curve = "exp" if fade_type == "exponential" else "tri"
        if fade_in > 0:
            audio_filters.append(f"afade=t=in:d={fade_in}:curve={curve}")
        if fade_out > 0:
            fos = f":st={fade_out_start}" if fade_out_start is not None else ""
            audio_filters.append(f"afade=t=out{fos}:d={fade_out}:curve={curve}")

    if is_video:
        if fade_in > 0:
            video_filters.append(f"fade=t=in:d={fade_in}")
        if fade_out > 0:
            fos = f":st={fade_out_start}" if fade_out_start is not None else ""
            video_filters.append(f"fade=t=out{fos}:d={fade_out}")

    if video_filters:
        cmd += ["-vf", ",".join(video_filters)]
    if audio_filters:
        cmd += ["-af", ",".join(audio_filters)]

    if is_video:
        cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-c:a", "aac", "-b:a", "192k"]
    elif is_audio:
        cmd += ["-c:a", "libmp3lame", "-b:a", "192k"]

    cmd.append(str(output_path))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg trim failed:\n{result.stderr[-2000:]}")

    return output_path


# ─── AI video generation ──────────────────────────────────────────────────────

async def video_generate(
    output_path: Path,
    prompt: str,
    provider: str,
    api_key: str,
    duration: float = 5.0,
    aspect_ratio: str = "16:9",
    negative_prompt: str = "",
    model: str = "",
    poll_interval: float = 5.0,
    timeout: float = 600.0,
) -> Path:
    """
    Generate a video from a text prompt using an AI provider.

    Supported providers:

      runway     — Runway Gen-4 Turbo (or Gen-3 Alpha).
                   duration: 5 or 10 seconds.
                   Requires VLOG_MCP_RUNWAY_KEY.

      luma       — Luma AI Dream Machine.
                   duration: 5 or 9 seconds.
                   Requires VLOG_MCP_LUMA_KEY.

      kling      — Kling AI (kling-v2-master).
                   duration: 5 or 10 seconds.
                   Requires VLOG_MCP_KLING_KEY.

    Returns path to downloaded .mp4 file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    p = provider.lower()
    if p == "runway":
        await _videogen_runway(output_path, prompt, api_key, duration,
                               aspect_ratio, negative_prompt, model,
                               poll_interval, timeout)
    elif p == "luma":
        await _videogen_luma(output_path, prompt, api_key, duration,
                              aspect_ratio, poll_interval, timeout)
    elif p == "kling":
        await _videogen_kling(output_path, prompt, api_key, duration,
                               aspect_ratio, negative_prompt, model,
                               poll_interval, timeout)
    else:
        raise ValueError(
            f"Unknown video generation provider: '{provider}'. "
            f"Supported: 'runway', 'luma', 'kling'."
        )
    return output_path


async def _videogen_runway(
    output_path: Path, prompt: str, api_key: str, duration: float,
    aspect_ratio: str, negative_prompt: str, model: str,
    poll_interval: float, timeout: float,
) -> None:
    import asyncio
    if not api_key:
        raise RuntimeError("Runway API key not set (video_gen.runway_api_key in vlog-mcp.json).")

    # Runway accepts 5 or 10 seconds only
    dur_sec = 10 if duration >= 8 else 5
    # Aspect ratio mapping
    ratio_map = {"16:9": "1280:768", "9:16": "768:1280", "1:1": "960:960", "4:3": "1024:768"}
    ratio = ratio_map.get(aspect_ratio, "1280:768")
    engine = model or "gen4_turbo"

    payload: dict = {
        "model":       engine,
        "promptText":  prompt,
        "duration":    dur_sec,
        "ratio":       ratio,
    }
    if negative_prompt:
        payload["promptTextNegative"] = negative_prompt

    headers = {
        "Authorization":  f"Bearer {api_key}",
        "X-Runway-Version": "2024-11-06",
        "Content-Type":   "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.runwayml.com/v1/image_to_video",
            headers=headers, json=payload,
        )
        resp.raise_for_status()
        task_id = resp.json()["id"]

    # Poll for completion
    elapsed = 0.0
    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            r = await client.get(
                f"https://api.runwayml.com/v1/tasks/{task_id}",
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("status", "")
            if status == "SUCCEEDED":
                video_url = data["output"][0]
                dl = await client.get(video_url, timeout=120.0)
                dl.raise_for_status()
                output_path.write_bytes(dl.content)
                return
            if status in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"Runway task {task_id} failed: {data.get('failure', '')}")

    raise TimeoutError(f"Runway task {task_id} did not finish within {timeout}s.")


async def _videogen_luma(
    output_path: Path, prompt: str, api_key: str, duration: float,
    aspect_ratio: str, poll_interval: float, timeout: float,
) -> None:
    import asyncio
    if not api_key:
        raise RuntimeError("Luma API key not set (video_gen.luma_api_key in vlog-mcp.json).")

    dur_str = "9s" if duration >= 7 else "5s"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "prompt":       prompt,
        "aspect_ratio": aspect_ratio,
        "duration":     dur_str,
        "loop":         False,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.lumalabs.ai/dream-machine/v1/generations",
            headers=headers, json=payload,
        )
        resp.raise_for_status()
        gen_id = resp.json()["id"]

    elapsed = 0.0
    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            r = await client.get(
                f"https://api.lumalabs.ai/dream-machine/v1/generations/{gen_id}",
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            state = data.get("state", "")
            if state == "completed":
                video_url = data["assets"]["video"]
                dl = await client.get(video_url, timeout=120.0)
                dl.raise_for_status()
                output_path.write_bytes(dl.content)
                return
            if state == "failed":
                raise RuntimeError(f"Luma generation {gen_id} failed: {data.get('failure_reason','')}")

    raise TimeoutError(f"Luma generation {gen_id} did not finish within {timeout}s.")


async def _videogen_kling(
    output_path: Path, prompt: str, api_key: str, duration: float,
    aspect_ratio: str, negative_prompt: str, model: str,
    poll_interval: float, timeout: float,
) -> None:
    import asyncio
    if not api_key:
        raise RuntimeError("Kling API key not set (video_gen.kling_api_key in vlog-mcp.json).")

    dur_str = "10" if duration >= 8 else "5"
    engine = model or "kling-v2-master"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: dict = {
        "model_name":    engine,
        "prompt":        prompt,
        "aspect_ratio":  aspect_ratio,
        "duration":      dur_str,
        "cfg_scale":     0.5,
        "mode":          "std",
    }
    if negative_prompt:
        payload["negative_prompt"] = negative_prompt

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.klingai.com/v1/videos/text2video",
            headers=headers, json=payload,
        )
        resp.raise_for_status()
        task_id = resp.json()["data"]["task_id"]

    elapsed = 0.0
    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            r = await client.get(
                f"https://api.klingai.com/v1/videos/text2video/{task_id}",
                headers=headers,
            )
            r.raise_for_status()
            data = r.json().get("data", {})
            status = data.get("task_status", "")
            if status == "succeed":
                video_url = data["task_result"]["videos"][0]["url"]
                dl = await client.get(video_url, timeout=120.0)
                dl.raise_for_status()
                output_path.write_bytes(dl.content)
                return
            if status == "failed":
                raise RuntimeError(f"Kling task {task_id} failed.")

    raise TimeoutError(f"Kling task {task_id} did not finish within {timeout}s.")


# ─── AI music generation ──────────────────────────────────────────────────────

async def music_generate(
    output_path: Path,
    prompt: str,
    provider: str,
    api_key: str,
    duration: float = 30.0,
    model: str = "",
    poll_interval: float = 5.0,
    timeout: float = 300.0,
) -> Path:
    """
    Generate music / audio from a text prompt using an AI provider.

    Supported providers:

      stability  — Stability AI Stable Audio.
                   duration: 0.5–180 seconds.
                   Requires VLOG_MCP_STABILITY_KEY (same key as image gen).

      replicate  — Replicate.com — hosts MusicGen (Meta), Riffusion, etc.
                   model: Replicate model version string (defaults to MusicGen stereo-large).
                   Requires VLOG_MCP_REPLICATE_KEY.

    Returns path to generated .mp3 file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    p = provider.lower()
    if p == "stability":
        await _musicgen_stability(output_path, prompt, api_key, duration)
    elif p == "replicate":
        await _musicgen_replicate(output_path, prompt, api_key, duration,
                                   model, poll_interval, timeout)
    else:
        raise ValueError(
            f"Unknown music generation provider: '{provider}'. "
            f"Supported: 'stability', 'replicate'."
        )
    return output_path


async def _musicgen_stability(
    output_path: Path, prompt: str, api_key: str, duration: float,
) -> None:
    if not api_key:
        raise RuntimeError(
            "Stability API key not set (stability.api_key in vlog-mcp.json)."
        )
    duration = min(max(duration, 0.5), 180.0)
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.stability.ai/v2beta/audio/stable-audio/generate",
            headers={
                "authorization": f"Bearer {api_key}",
                "accept":        "audio/*",
            },
            data={
                "prompt":        prompt,
                "output_format": "mp3",
                "duration":      str(duration),
                "steps":         "50",
            },
        )
        resp.raise_for_status()
    output_path.write_bytes(resp.content)


# MusicGen stereo-large version on Replicate (pinned; update if needed)
_REPLICATE_MUSICGEN_VERSION = (
    "671ac645ce5e552cc63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb"
)


async def _musicgen_replicate(
    output_path: Path, prompt: str, api_key: str, duration: float,
    model: str, poll_interval: float, timeout: float,
) -> None:
    import asyncio
    if not api_key:
        raise RuntimeError(
            "Replicate API key not set (music_gen.replicate_api_key in vlog-mcp.json)."
        )
    version = model or _REPLICATE_MUSICGEN_VERSION
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "version": version,
        "input": {
            "prompt":         prompt,
            "duration":       int(duration),
            "model_version":  "stereo-large",
            "output_format":  "mp3",
            "normalization_strategy": "peak",
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers, json=payload,
        )
        resp.raise_for_status()
        pred_id = resp.json()["id"]

    elapsed = 0.0
    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            r = await client.get(
                f"https://api.replicate.com/v1/predictions/{pred_id}",
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("status", "")
            if status == "succeeded":
                audio_url = data["output"]
                if isinstance(audio_url, list):
                    audio_url = audio_url[0]
                dl = await client.get(audio_url, timeout=120.0)
                dl.raise_for_status()
                output_path.write_bytes(dl.content)
                return
            if status in ("failed", "canceled"):
                raise RuntimeError(
                    f"Replicate prediction {pred_id} failed: {data.get('error','')}"
                )

    raise TimeoutError(f"Replicate prediction {pred_id} did not finish within {timeout}s.")
