"""
Composition timeline manipulation and inspection.
The timeline is stored as a plain dict (JSON-serializable).
All modifications return the mutated timeline dict.
"""

from __future__ import annotations

from typing import Any

from .models import new_id, now_ts


# ─── create ──────────────────────────────────────────────────────────────────

def create_timeline(project_id: str, duration: float) -> dict[str, Any]:
    return {
        "timeline_id": new_id("tl"),
        "project_id": project_id,
        "duration": duration,
        "background": [],
        "objects": [],
        "audio": [],
        "transitions": [],
    }


# ─── background ──────────────────────────────────────────────────────────────

def add_clip(
    tl: dict, asset_id: str,
    start: float, duration: float,
    source_in: float, source_out: float,
) -> str:
    el = {"id": new_id("bg"), "type": "clip", "asset_id": asset_id,
          "start": start, "duration": duration,
          "source_in": source_in, "source_out": source_out}
    tl["background"].append(el)
    return el["id"]


def add_color_bg(tl: dict, color: str, start: float, duration: float) -> str:
    el = {"id": new_id("bg"), "type": "color", "color": color,
          "start": start, "duration": duration}
    tl["background"].append(el)
    return el["id"]


def add_image_bg(tl: dict, asset_id: str, start: float, duration: float) -> str:
    el = {"id": new_id("bg"), "type": "image", "asset_id": asset_id,
          "start": start, "duration": duration}
    tl["background"].append(el)
    return el["id"]


def add_cutaway(
    tl: dict, source: str, lib_or_asset_id: str,
    start: float, duration: float | None = None,
) -> str:
    el = {"id": new_id("bg"), "type": "cutaway",
          "source": source, "ref_id": lib_or_asset_id,
          "start": start}
    if duration is not None:
        el["duration"] = duration
    tl["background"].append(el)
    return el["id"]


# ─── objects ──────────────────────────────────────────────────────────────────

"""
appear / disappear effect dict schema:
  { "effect": "fade",  "duration": 0.4 }   — smooth opacity transition
  { "effect": "none" }                      — hard cut (default when omitted)

Supported effects in renderer:
  fade  — opacity fades in/out (drawtext: alpha expression; image: fade filter)
  none  — instant appear/disappear
"""

_Effect = dict | None   # type alias for readability


def _obj(type_: str, start: float, duration: float, x: Any, y: Any, z: int, **extra) -> dict:
    return {"id": new_id("o"), "type": type_, "start": start, "duration": duration,
            "x": x, "y": y, "z": z, **extra}


def _with_effects(obj: dict, appear: _Effect, disappear: _Effect) -> dict:
    if appear:
        obj["appear"] = appear
    if disappear:
        obj["disappear"] = disappear
    return obj


def add_text(
    tl: dict, text: str, style: str,
    x: Any, y: Any, z: int,
    start: float, duration: float,
    appear: _Effect = None,
    disappear: _Effect = None,
) -> str:
    el = _with_effects(
        _obj("text", start, duration, x, y, z, text=text, style=style),
        appear, disappear,
    )
    tl["objects"].append(el)
    return el["id"]


def add_image(
    tl: dict, asset_id: str,
    x: Any, y: Any, z: int,
    start: float, duration: float,
    width: int | None = None,
    appear: _Effect = None,
    disappear: _Effect = None,
) -> str:
    el = _with_effects(
        _obj("image", start, duration, x, y, z, asset_id=asset_id, width=width),
        appear, disappear,
    )
    tl["objects"].append(el)
    return el["id"]


def add_code_block(
    tl: dict, asset_id: str,
    x: Any, y: Any, z: int,
    start: float, duration: float,
    width: int | None = None,
    appear: _Effect = None,
    disappear: _Effect = None,
) -> str:
    el = _with_effects(
        _obj("code_block", start, duration, x, y, z, asset_id=asset_id, width=width),
        appear, disappear,
    )
    tl["objects"].append(el)
    return el["id"]


def add_lower_third(
    tl: dict, title: str, subtitle: str,
    start: float, duration: float, z: int = 10,
    appear: _Effect = None,
    disappear: _Effect = None,
) -> str:
    el = _with_effects(
        _obj("lower_third", start, duration, "left+0", "bottom-90", z,
             title=title, subtitle=subtitle),
        appear, disappear,
    )
    tl["objects"].append(el)
    return el["id"]


def add_plate(
    tl: dict, plate: str, text: str,
    x: Any, y: Any, z: int,
    start: float, duration: float,
    appear: _Effect = None,
    disappear: _Effect = None,
) -> str:
    el = _with_effects(
        _obj("plate", start, duration, x, y, z, plate=plate, text=text),
        appear, disappear,
    )
    tl["objects"].append(el)
    return el["id"]


def add_meme(
    tl: dict, lib_id: str,
    x: Any, y: Any, z: int,
    start: float, duration: float,
    width: int | None = None,
    appear: _Effect = None,
    disappear: _Effect = None,
) -> str:
    el = _with_effects(
        _obj("meme", start, duration, x, y, z, lib_id=lib_id, width=width),
        appear, disappear,
    )
    tl["objects"].append(el)
    return el["id"]


def add_sticker(
    tl: dict, lib_id: str,
    x: Any, y: Any, z: int,
    start: float, duration: float,
    scale: float = 1.0,
    appear: _Effect = None,
    disappear: _Effect = None,
) -> str:
    el = _with_effects(
        _obj("sticker", start, duration, x, y, z, lib_id=lib_id, scale=scale),
        appear, disappear,
    )
    tl["objects"].append(el)
    return el["id"]


def add_progress_bar(
    tl: dict, current: int, total: int,
    x: Any, y: Any, z: int,
    start: float, duration: float,
    appear: _Effect = None,
    disappear: _Effect = None,
) -> str:
    el = _with_effects(
        _obj("progress_bar", start, duration, x, y, z, current=current, total=total),
        appear, disappear,
    )
    tl["objects"].append(el)
    return el["id"]


# ─── audio ────────────────────────────────────────────────────────────────────

def add_audio(
    tl: dict, asset_id: str,
    start: float, volume: float = 1.0, mix: str = "duck_main",
) -> str:
    el = {"id": new_id("a"), "type": "asset",
          "asset_id": asset_id, "start": start,
          "volume": volume, "mix": mix}
    tl["audio"].append(el)
    return el["id"]


def add_sfx(tl: dict, lib_id: str, start: float, volume: float = 0.7) -> str:
    el = {"id": new_id("a"), "type": "sfx",
          "lib_id": lib_id, "start": start, "volume": volume, "mix": "add"}
    tl["audio"].append(el)
    return el["id"]


def add_music(
    tl: dict, lib_id: str,
    start: float, volume: float = 0.15, loop: bool = True,
) -> str:
    el = {"id": new_id("a"), "type": "music",
          "lib_id": lib_id, "start": start,
          "volume": volume, "mix": "add", "loop": loop}
    tl["audio"].append(el)
    return el["id"]


# ─── transitions ─────────────────────────────────────────────────────────────

def add_transition(
    tl: dict, after_bg_id: str, type_: str, duration: float = 0.5,
) -> str:
    el = {"id": new_id("tr"), "after": after_bg_id,
          "type": type_, "duration": duration}
    tl["transitions"].append(el)
    return el["id"]


# ─── remove ──────────────────────────────────────────────────────────────────

def remove_element(tl: dict, element_id: str) -> bool:
    """Remove an element from any track. Returns True if found and removed."""
    for key in ("background", "objects", "audio", "transitions"):
        track = tl.get(key, [])
        for i, el in enumerate(track):
            if el.get("id") == element_id:
                track.pop(i)
                return True
    return False


# ─── query ────────────────────────────────────────────────────────────────────

def objects_at(tl: dict, at: float) -> list[dict]:
    """Return all object-layer elements active at the given second."""
    result = []
    for el in tl.get("objects", []):
        s = el.get("start", 0.0)
        e = s + el.get("duration", 0.0)
        if s <= at < e:
            result.append(el)
    return sorted(result, key=lambda e: e.get("z", 1))


def background_at(tl: dict, at: float) -> dict | None:
    """Return the active background element at the given second."""
    for el in tl.get("background", []):
        s = el.get("start", 0.0)
        e = s + el.get("duration", el.get("source_out", 0) - el.get("source_in", 0))
        if el.get("type") == "cutaway" and "duration" not in el:
            e = s + 4.0   # default cutaway estimate
        if s <= at < e:
            return el
    return None


# ─── inspect ─────────────────────────────────────────────────────────────────

def _fmt_t(secs: float) -> str:
    m = int(secs // 60)
    s = secs % 60
    return f"{m}:{s:05.2f}"


def inspect(tl: dict, from_sec: float | None = None, to_sec: float | None = None) -> str:
    """Return a human-readable text layout of the timeline."""
    dur = tl.get("duration", 0.0)
    from_sec = from_sec or 0.0
    to_sec = to_sec or dur

    lines: list[str] = []
    lines.append(f"{_fmt_t(from_sec)} {'─' * 50} {_fmt_t(to_sec)}")
    lines.append("")

    # background
    bg_rows: list[str] = []
    for el in tl.get("background", []):
        s = el.get("start", 0.0)
        d = el.get("duration", 0.0)
        e = s + d
        if e < from_sec or s > to_sec:
            continue
        t = el["type"]
        if t == "clip":
            desc = f"clip  {el.get('asset_id','?')}  (src {_fmt_t(el.get('source_in',0))}→{_fmt_t(el.get('source_out',0))})"
        elif t == "color":
            desc = f"color {el.get('color','?')}"
        elif t == "image":
            desc = f"image {el.get('asset_id','?')}"
        elif t == "cutaway":
            desc = f"cutaway [{el.get('source','?')}] {el.get('ref_id','?')}"
        else:
            desc = str(el)
        bg_rows.append(f"  [{desc}  {_fmt_t(s)}─{_fmt_t(e)}]")

    if bg_rows:
        lines.append("BG:")
        lines.extend(bg_rows)
    lines.append("")

    # objects (sorted by z desc for display)
    obj_rows: list[str] = []
    for el in sorted(tl.get("objects", []), key=lambda e: -e.get("z", 1)):
        s = el.get("start", 0.0)
        d = el.get("duration", 0.0)
        e = s + d
        if e < from_sec or s > to_sec:
            continue
        z = el.get("z", 1)
        t = el["type"]
        if t == "text":
            desc = f'text  "{el.get("text","")[:40]}"  style={el.get("style","")}'
        elif t == "image":
            desc = f'image  {el.get("asset_id","?")}  w={el.get("width","auto")}'
        elif t == "code_block":
            desc = f'code_block  {el.get("asset_id","?")}'
        elif t == "lower_third":
            desc = f'lower_third  "{el.get("title","")} / {el.get("subtitle","")}"'
        elif t == "plate":
            desc = f'plate  {el.get("plate","?")}  "{el.get("text","")[:30]}"'
        elif t == "meme":
            desc = f'meme  {el.get("lib_id","?")}'
        elif t == "sticker":
            desc = f'sticker  {el.get("lib_id","?")}  ×{el.get("scale",1)}'
        elif t == "progress_bar":
            desc = f'progress  {el.get("current","?")}/{el.get("total","?")}'
        else:
            desc = t
        pos = f'x={el.get("x","?")} y={el.get("y","?")}'
        obj_rows.append(f"  z={z:>2}  {desc}  {pos}  {_fmt_t(s)}─{_fmt_t(e)}")

    if obj_rows:
        lines.append("OBJ:")
        lines.extend(obj_rows)
    lines.append("")

    # audio
    aud_rows: list[str] = []
    for el in tl.get("audio", []):
        s = el.get("start", 0.0)
        if s > to_sec:
            continue
        t = el.get("type", "?")
        ref = el.get("asset_id") or el.get("lib_id", "?")
        vol = el.get("volume", 1.0)
        mix = el.get("mix", "")
        loop = " loop" if el.get("loop") else ""
        aud_rows.append(f"  [{t}  {ref}  @{_fmt_t(s)}  vol={vol}  {mix}{loop}]")

    if aud_rows:
        lines.append("AUD:")
        lines.extend(aud_rows)
    lines.append("")

    # transitions
    tr_rows: list[str] = []
    for el in tl.get("transitions", []):
        tr_rows.append(f"  [{el.get('type','?')} after={el.get('after','?')} dur={el.get('duration',0.5)}s]")
    if tr_rows:
        lines.append("TRN:")
        lines.extend(tr_rows)

    return "\n".join(lines)
