"""
Video renderer: converts a composition timeline into a final MP4 via ffmpeg.

Pipeline:
  1. Build background video track (concat clips/images/colors with xfade transitions)
  2. Apply object overlays (drawtext, overlay filters) via filter_complex
  3. Mix audio tracks (amix + adelay)
  4. Apply branding: prepend intro, append outro, stamp watermark
"""

from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import BrandingConfig
from .models import now_ts


# ─── appear / disappear helpers ──────────────────────────────────────────────

def _alpha_expr(s: float, e: float, appear: dict | None, disappear: dict | None) -> str:
    """
    Build an ffmpeg expression for drawtext 'alpha' that implements
    fade-in and/or fade-out within the [s, e] window.
    Returns '1' if no fading is requested.
    """
    fi = 0.0
    fo = 0.0
    if appear and appear.get("effect") == "fade":
        fi = float(appear.get("duration", 0.3))
    if disappear and disappear.get("effect") == "fade":
        fo = float(disappear.get("duration", 0.3))
    if not fi and not fo:
        return "1"

    # Build nested ternary: if(cond, true_val, false_val)
    expr = "1"
    if fo:
        fo_start = e - fo
        expr = f"if(gt(t,{fo_start:.4f}),({e:.4f}-t)/{fo:.4f},{expr})"
    if fi:
        expr = f"if(lt(t-{s:.4f},{fi:.4f}),(t-{s:.4f})/{fi:.4f},{expr})"
    return expr


def _image_fade_filter(
    idx: int, s: float, e: float,
    appear: dict | None, disappear: dict | None,
    scale_w: int | None = None,
) -> tuple[str, str]:
    """
    Build scale + optional fade filter string for an image/video overlay input.
    Returns (filter_line, output_label).
    """
    label_in  = f"[{idx}:v]"
    label_out = f"[ov_{idx}]"

    filters: list[str] = []
    if scale_w:
        filters.append(f"scale={scale_w}:-1")

    fi = 0.0
    fo = 0.0
    if appear and appear.get("effect") == "fade":
        fi = float(appear.get("duration", 0.3))
    if disappear and disappear.get("effect") == "fade":
        fo = float(disappear.get("duration", 0.3))

    if fi or fo:
        filters.append("format=rgba")
    if fi:
        filters.append(f"fade=in:start_time={s:.4f}:duration={fi:.4f}:alpha=1")
    if fo:
        fo_start = e - fo
        filters.append(f"fade=out:start_time={fo_start:.4f}:duration={fo:.4f}:alpha=1")

    filt_str = ",".join(filters) if filters else "null"
    return f"{label_in} {filt_str} {label_out}", label_out


# ─── escaping ────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """Escape text for ffmpeg drawtext filter."""
    return (text
            .replace("\\", "\\\\")
            .replace("'",  "\\'")
            .replace(":",  "\\:")
            .replace("[",  "\\[")
            .replace("]",  "\\]")
            .replace(",",  "\\,"))


# ─── position resolver ────────────────────────────────────────────────────────

def _ffmpeg_xy(x: Any, y: Any, w_expr: str = "0", h_expr: str = "0") -> tuple[str, str]:
    """Convert anchor strings to ffmpeg x/y expressions."""
    def _cvt(val: Any, dim: str, size_expr: str) -> str:
        if isinstance(val, (int, float)):
            return str(int(val))
        s = str(val).strip()
        if s == "center":
            return f"({dim}-{size_expr})/2"
        if s.startswith("right-"):
            off = s.split("-")[1]
            return f"({dim}-{size_expr}-{off})"
        if s.startswith("bottom-"):
            off = s.split("-")[1]
            return f"({dim}-{size_expr}-{off})"
        if "+" in s:
            return s.split("+")[1]
        try:
            return str(int(s))
        except ValueError:
            return "0"
    return _cvt(x, "W", w_expr), _cvt(y, "H", h_expr)


# ─── background builder ───────────────────────────────────────────────────────

def _build_background_inputs(
    bg_elements: list[dict],
    project_dir: Path,
    assets_map: dict[str, str],   # asset_id → abs file path
) -> tuple[list[str], list[str], dict]:
    """
    Build ffmpeg input args and a filter_complex fragment for the background track.
    Returns: (input_args, filter_lines, {bg_id: stream_label})
    """
    input_args: list[str] = []
    filter_lines: list[str] = []
    stream_labels: dict[str, str] = {}   # element id → video stream label
    idx = 0

    for el in bg_elements:
        t = el.get("type", "color")
        dur = float(el.get("duration", 5.0))
        eid = el["id"]

        if t == "clip":
            path = assets_map.get(el.get("asset_id", ""), "")
            if not path:
                # fallback to black
                input_args += ["-f", "lavfi", "-t", str(dur),
                               "-i", f"color=c=black:s=1920x1080:r=30"]
            else:
                src_in  = float(el.get("source_in", 0))
                src_out = float(el.get("source_out", dur))
                input_args += ["-ss", str(src_in), "-t", str(src_out - src_in),
                               "-i", path]
            label = f"[v{idx}]"
            filter_lines.append(
                f"[{idx}:v] scale=1920:1080:force_original_aspect_ratio=increase,"
                f"crop=1920:1080 {label}"
            )

        elif t == "color":
            color = el.get("color", "#121219").lstrip("#")
            input_args += ["-f", "lavfi", "-t", str(dur),
                           "-i", f"color=c=0x{color}:s=1920x1080:r=30"]
            label = f"[v{idx}]"
            filter_lines.append(f"[{idx}:v] null {label}")

        elif t == "image":
            path = assets_map.get(el.get("asset_id", ""), "")
            if path:
                input_args += ["-loop", "1", "-t", str(dur), "-i", path]
                label = f"[v{idx}]"
                filter_lines.append(
                    f"[{idx}:v] scale=1920:1080:force_original_aspect_ratio=increase,"
                    f"crop=1920:1080 {label}"
                )
            else:
                input_args += ["-f", "lavfi", "-t", str(dur),
                               "-i", "color=c=black:s=1920x1080:r=30"]
                label = f"[v{idx}]"
                filter_lines.append(f"[{idx}:v] null {label}")

        elif t == "cutaway":
            source = el.get("source", "")
            ref_id = el.get("ref_id", "")
            cut_path = assets_map.get(ref_id, "")
            if cut_path:
                input_args += ["-t", str(dur), "-i", cut_path]
                label = f"[v{idx}]"
                filter_lines.append(
                    f"[{idx}:v] scale=1920:1080:force_original_aspect_ratio=increase,"
                    f"crop=1920:1080 {label}"
                )
            else:
                input_args += ["-f", "lavfi", "-t", str(dur),
                               "-i", "color=c=black:s=1920x1080:r=30"]
                label = f"[v{idx}]"
                filter_lines.append(f"[{idx}:v] null {label}")

        stream_labels[eid] = f"v{idx}"
        idx += 1

    return input_args, filter_lines, stream_labels


# ─── filter_complex builder ───────────────────────────────────────────────────

def _build_filter_complex(
    timeline: dict,
    input_count: int,
    stream_labels: dict[str, str],  # bg_id → stream index label (e.g. "v0")
    assets_map: dict[str, str],
    overlay_input_start: int,       # index at which overlay inputs begin
) -> tuple[list[str], list[str], str, int]:
    """
    Build filter_complex parts for objects and audio.
    Returns: (overlay_input_args, filter_lines, final_video_label, next_input_idx)
    """
    bg_elements = timeline.get("background", [])
    objects     = timeline.get("objects", [])

    overlay_inputs: list[str] = []
    filter_lines: list[str] = []

    # ── concat background segments ──────────────────────────────────────────
    n_bg = len(bg_elements)
    if n_bg == 0:
        concat_label = "[vbg]"
        filter_lines.append(
            "color=c=black:s=1920x1080:r=30:d=5 [vbg]"
        )
    elif n_bg == 1:
        first_id = bg_elements[0]["id"]
        concat_label = f"[{stream_labels[first_id]}scaled]"
        filter_lines.append(f"[{stream_labels[first_id]}] null {concat_label}")
    else:
        parts = "".join(f"[{stream_labels[e['id']]}]" for e in bg_elements)
        concat_label = "[vbg]"
        filter_lines.append(f"{parts} concat=n={n_bg}:v=1:a=0 {concat_label}")

    # ── overlay objects ──────────────────────────────────────────────────────
    current_label = concat_label
    next_idx = overlay_input_start

    sorted_objs = sorted(objects, key=lambda o: o.get("z", 1))

    for obj in sorted_objs:
        t    = obj.get("type", "")
        s    = float(obj.get("start", 0))
        dur  = float(obj.get("duration", 5))
        e    = s + dur
        eid  = obj.get("id", "obj")
        new_label = f"[v_{eid}]"

        appear    = obj.get("appear")
        disappear = obj.get("disappear")

        if t == "text":
            text  = _esc(obj.get("text", ""))
            style = obj.get("style", "branding.body")
            size_map = {
                "branding.title": 64, "branding.subtitle": 42,
                "branding.body": 28, "branding.code": 24, "branding.caption": 22,
            }
            font_size = size_map.get(style, 28)
            x_expr, y_expr = _ffmpeg_xy(obj.get("x", 60), obj.get("y", 60))
            alpha = _alpha_expr(s, e, appear, disappear)
            filt = (
                f"{current_label} drawtext="
                f"text='{text}':fontsize={font_size}:fontcolor=white@1:"
                f"x={x_expr}:y={y_expr}:alpha='{alpha}':"
                f"enable='between(t,{s},{e})' {new_label}"
            )
            filter_lines.append(filt)
            current_label = new_label

        elif t in ("image", "code_block"):
            path = assets_map.get(obj.get("asset_id", ""), "")
            if path:
                overlay_inputs += ["-i", path]
                w = obj.get("width") or None
                filt_line, scale_out = _image_fade_filter(
                    next_idx, s, e, appear, disappear, scale_w=w,
                )
                filter_lines.append(filt_line)
                x_expr, y_expr = _ffmpeg_xy(obj.get("x", 0), obj.get("y", 0))
                filt = (
                    f"{current_label}{scale_out} overlay="
                    f"x={x_expr}:y={y_expr}:enable='between(t,{s},{e})' {new_label}"
                )
                filter_lines.append(filt)
                current_label = new_label
                next_idx += 1

        elif t == "lower_third":
            title    = _esc(obj.get("title", ""))
            subtitle = _esc(obj.get("subtitle", ""))
            filt = (
                f"{current_label} "
                f"drawtext=text='{title}':fontsize=28:fontcolor=white:"
                f"x=60:y=H-90:enable='between(t,{s},{e})',"
                f"drawtext=text='{subtitle}':fontsize=22:fontcolor=#8899AA:"
                f"x=60:y=H-55:enable='between(t,{s},{e})' {new_label}"
            )
            filter_lines.append(filt)
            current_label = new_label

        elif t == "plate":
            text = _esc(obj.get("text", ""))
            x_expr, y_expr = _ffmpeg_xy(obj.get("x", 60), obj.get("y", 60))
            filt = (
                f"{current_label} drawtext="
                f"text='{text}':fontsize=36:fontcolor=white:"
                f"x={x_expr}:y={y_expr}:box=1:boxcolor=#5B8DEF@0.85:boxborderw=20:"
                f"enable='between(t,{s},{e})' {new_label}"
            )
            filter_lines.append(filt)
            current_label = new_label

        elif t in ("meme", "sticker"):
            # memes/stickers need the actual files from library
            # For MVP we skip if no path available
            pass

        elif t == "progress_bar":
            current_step = obj.get("current", 1)
            total_steps  = obj.get("total", 1)
            pct          = current_step / max(total_steps, 1)
            bar_w        = int(1920 * pct)
            filt = (
                f"{current_label} "
                f"drawbox=x=0:y=ih-8:w={bar_w}:h=8:color=#5B8DEF@1:t=fill:"
                f"enable='between(t,{s},{e})' {new_label}"
            )
            filter_lines.append(filt)
            current_label = new_label

    return overlay_inputs, filter_lines, current_label, next_idx


# ─── audio builder ────────────────────────────────────────────────────────────

def _build_audio(
    timeline: dict,
    assets_map: dict[str, str],
    start_idx: int,
) -> tuple[list[str], list[str], str | None, int]:
    audio_inputs: list[str] = []
    filter_lines: list[str] = []
    idx = start_idx
    mix_inputs: list[str] = []

    for el in timeline.get("audio", []):
        etype = el.get("type", "")
        path = ""
        if etype == "asset":
            path = assets_map.get(el.get("asset_id", ""), "")
        elif etype in ("sfx", "music"):
            # library items need to be looked up externally; skip for MVP
            pass

        if not path:
            continue

        start_sec = float(el.get("start", 0))
        vol       = float(el.get("volume", 1.0))
        loop      = el.get("loop", False)

        audio_inputs += ["-i", path]
        delay_ms = int(start_sec * 1000)
        lbl = f"[a{idx}]"
        loop_flag = ",aloop=loop=-1:size=2e+09" if loop else ""
        filter_lines.append(
            f"[{idx}:a] adelay={delay_ms}|{delay_ms}{loop_flag},volume={vol} {lbl}"
        )
        mix_inputs.append(lbl)
        idx += 1

    if not mix_inputs:
        return audio_inputs, filter_lines, None, idx

    if len(mix_inputs) == 1:
        final_audio = "[afinal]"
        filter_lines.append(f"{mix_inputs[0]} anull {final_audio}")
    else:
        joined = "".join(mix_inputs)
        final_audio = "[afinal]"
        filter_lines.append(f"{joined} amix=inputs={len(mix_inputs)}:duration=longest {final_audio}")

    return audio_inputs, filter_lines, final_audio, idx


# ─── main render ──────────────────────────────────────────────────────────────

def render(
    timeline: dict,
    project_dir: Path,
    assets_map: dict[str, str],   # asset_id → absolute file path
    branding: BrandingConfig,
    quality: str = "1080p",
    output_name: str | None = None,
    apply_branding: bool = True,
) -> Path:
    """
    Render the composition timeline to a final MP4 file.

    apply_branding=False — skip intro/outro clips and watermark stamp entirely.
    Useful for raw exports, previews, or projects without a branding config.

    Returns the path to the output file.
    """
    exports_dir = project_dir / "exports"
    exports_dir.mkdir(exist_ok=True)

    if not output_name:
        ts = int(now_ts())
        output_name = f"final_{quality}_{ts}.mp4"
    output_path = exports_dir / output_name

    bg_elements = timeline.get("background", [])
    if not bg_elements:
        raise ValueError("Timeline has no background elements. Add at least one clip, color, or image.")

    # ── build inputs and filters ────────────────────────────────────────────
    bg_input_args, bg_filter_lines, stream_labels = _build_background_inputs(
        bg_elements, project_dir, assets_map,
    )
    overlay_input_start = len(bg_elements)

    ov_inputs, obj_filter_lines, final_video_label, next_idx = _build_filter_complex(
        timeline, overlay_input_start, stream_labels, assets_map, overlay_input_start,
    )

    audio_inputs, aud_filter_lines, final_audio_label, _ = _build_audio(
        timeline, assets_map, next_idx,
    )

    all_filter_lines = bg_filter_lines + obj_filter_lines + aud_filter_lines

    # ── assemble ffmpeg command ─────────────────────────────────────────────
    quality_map = {"720p": "23", "1080p": "18", "4k": "15"}
    crf = quality_map.get(quality, "18")

    cmd: list[str] = ["ffmpeg", "-y"]
    cmd += bg_input_args
    cmd += ov_inputs
    cmd += audio_inputs

    filter_complex = "; ".join(l.strip() for l in all_filter_lines if l.strip())
    cmd += ["-filter_complex", filter_complex]

    cmd += ["-map", final_video_label]
    if final_audio_label:
        cmd += ["-map", final_audio_label]

    if quality == "4k":
        cmd += ["-s", "3840x2160"]
    elif quality == "720p":
        cmd += ["-s", "1280x720"]
    else:
        cmd += ["-s", "1920x1080"]

    cmd += ["-c:v", "libx264", "-crf", crf, "-preset", "medium",
            "-pix_fmt", "yuv420p"]
    if final_audio_label:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]

    # ── branding: intro + outro via two-pass concat ─────────────────────────
    intro_path  = branding.clips.get("intro", "") if apply_branding else ""
    outro_path  = branding.clips.get("outro", "") if apply_branding else ""
    has_intro   = bool(intro_path) and Path(intro_path).exists()
    has_outro   = bool(outro_path) and Path(outro_path).exists()

    if not (has_intro or has_outro):
        cmd.append(str(output_path))
        _run(cmd)
    else:
        # render content first, then concat with branding clips
        tmp_content = exports_dir / f"_tmp_content_{int(now_ts())}.mp4"
        cmd.append(str(tmp_content))
        _run(cmd)

        # build concat list
        concat_items: list[str] = []
        if has_intro:
            concat_items.append(intro_path)
        concat_items.append(str(tmp_content))
        if has_outro:
            concat_items.append(outro_path)

        _concat_videos(concat_items, output_path)
        tmp_content.unlink(missing_ok=True)

    # ── watermark ────────────────────────────────────────────────────────────
    wm = branding.watermark if apply_branding else None
    if wm and Path(wm.asset).exists():
        tmp_no_wm = output_path.with_suffix(".nowm.mp4")
        output_path.rename(tmp_no_wm)
        wm_cmd = [
            "ffmpeg", "-y",
            "-i", str(tmp_no_wm),
            "-i", wm.asset,
            "-filter_complex",
            f"[1:v] scale=iw*{wm.scale}:-1,format=rgba,colorchannelmixer=aa={wm.opacity} [wm];"
            f"[0:v][wm] overlay=W-w-{wm.margin_x}:H-h-{wm.margin_y}",
            "-map", "0:a?",
            "-c:v", "libx264", "-crf", crf, "-c:a", "copy",
            str(output_path),
        ]
        _run(wm_cmd)
        tmp_no_wm.unlink(missing_ok=True)

    return output_path


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")


def _concat_videos(paths: list[str], output: Path) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in paths:
            f.write(f"file '{p}'\n")
        list_file = f.name
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", str(output),
    ]
    _run(cmd)
    Path(list_file).unlink(missing_ok=True)
