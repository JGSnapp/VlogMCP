from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .capture import ScreenRecorder
from .composer import compose_with_timeline
from .config import load_config
from .editor import concat_videos, overlay_image, trim_video
from .models import AssetRecord, TimelineEvent
from .observability import traced
from .planner import TEMPLATES, build_video_plan
from .providers import ImageService, TTSService
from .renderer import apply_branding, build_render_job, execute_render_job, write_concat_file
from .screenshots import make_screenshot
from .slides import render_slide_to_image
from .storage import SessionStore
from .telegram import send_video
from .worker import JobWorker

config = load_config()
store = SessionStore(config.workspace_root)
recorder = ScreenRecorder()
tts_service = TTSService(config.tokens.openai_api_key, config.tokens.elevenlabs_api_key)
image_service = ImageService(config.tokens.openai_api_key, config.tokens.stability_api_key)
worker = JobWorker(store)
mcp = FastMCP("vlog-mcp")


def _session_dir(session_id: str) -> Path:
    return Path(store.root) / session_id


def _collect_render_sources(session_id: str) -> list[str]:
    session_dir = _session_dir(session_id)
    assets = store.list_assets(session_id)
    video_kinds = {"video-capture", "video-edited", "video", "clip"}
    files = [item["path"] for item in assets if item.get("kind") in video_kinds]

    recording = session_dir / "captures" / "recording.mp4"
    if recording.exists() and str(recording) not in files:
        files.insert(0, str(recording))

    unique_existing: list[str] = []
    seen = set()
    for path in files:
        if path in seen:
            continue
        if Path(path).exists():
            unique_existing.append(path)
            seen.add(path)
    return unique_existing


def _tts_with_fallback(provider: str, text: str, output: str, voice: str) -> dict[str, Any]:
    providers = [provider] if provider else [config.providers.default_tts_provider, "elevenlabs", "openai"]
    errors: list[str] = []
    for p in dict.fromkeys(providers):
        try:
            return tts_service.generate(p, text, output, voice=voice)
        except Exception as exc:
            errors.append(f"{p}: {exc}")
    raise RuntimeError("; ".join(errors))


def _image_with_fallback(provider: str, prompt: str, output: str, size: str) -> dict[str, Any]:
    providers = [provider] if provider else [config.providers.default_image_provider, "stability", "openai"]
    errors: list[str] = []
    for p in dict.fromkeys(providers):
        try:
            return image_service.generate(p, prompt, output, size=size)
        except Exception as exc:
            errors.append(f"{p}: {exc}")
    raise RuntimeError("; ".join(errors))


@mcp.tool()
def health_check() -> dict[str, Any]:
    return {
        "workspace": str(store.root),
        "ffmpeg_available": bool(shutil.which("ffmpeg")),
        "sessions_count": len(store.list_sessions()),
    }


@mcp.tool()
def capture_capabilities() -> dict[str, Any]:
    return recorder.list_capture_capabilities()


@mcp.tool()
def list_capture_devices() -> dict[str, Any]:
    return recorder.list_capture_devices()


@mcp.tool()
def init_workspace() -> dict[str, Any]:
    return store.init_workspace()


@mcp.tool()
def get_config() -> dict[str, Any]:
    return config.to_dict()


@mcp.tool()
def create_session(title: str, kind: str = "coding-report", tags: list[str] | None = None) -> dict[str, Any]:
    with traced("create_session", title=title, kind=kind):
        return store.create_session(title=title, kind=kind, tags=tags)


@mcp.tool()
def list_sessions(status: str | None = None) -> list[dict[str, Any]]:
    return store.list_sessions(status=status)


@mcp.tool()
def get_session(session_id: str) -> dict[str, Any]:
    return store.load_manifest(session_id)


@mcp.tool()
def start_recording(
    session_id: str,
    source: str = "desktop",
    at_seconds: float = 0.0,
    window_title: str = "",
    fps: int = 30,
    display: str = ":0.0",
    output_filename: str = "recording.mp4",
    region: dict[str, int] | None = None,
    with_audio: bool = False,
) -> dict[str, Any]:
    with traced("start_recording", session_id=session_id):
        session_dir = _session_dir(session_id)
        captures = session_dir / "captures"
        captures.mkdir(exist_ok=True)
        output_path = captures / output_filename
        recording = recorder.start(
            session_id=session_id,
            output_path=str(output_path),
            fps=fps,
            display=display,
            region=region,
            window_title=window_title or None,
            with_audio=with_audio,
        )
        store.update_manifest(session_id, {"status": "recording"})
        event = store.append_event(
            session_id,
            TimelineEvent.create(
                "recording_started",
                at_seconds,
                {
                    "source": source,
                    "window_title": window_title,
                    "output_path": str(output_path),
                    "fps": fps,
                    "region": region or {},
                    "with_audio": with_audio,
                },
            ),
        )
        asset = store.add_asset(session_id, AssetRecord.create("video-capture", str(output_path), metadata={"source": source, "fps": fps}))
        return {"event": event, "recording": recording, "asset": asset}


@mcp.tool()
def pause_recording(session_id: str, at_seconds: float) -> dict[str, Any]:
    recording = recorder.pause(session_id)
    event = store.append_event(session_id, TimelineEvent.create("recording_paused", at_seconds, {}))
    return {"event": event, "recording": recording}


@mcp.tool()
def resume_recording(session_id: str, at_seconds: float) -> dict[str, Any]:
    recording = recorder.resume(session_id)
    event = store.append_event(session_id, TimelineEvent.create("recording_resumed", at_seconds, {}))
    return {"event": event, "recording": recording}


@mcp.tool()
def stop_recording(session_id: str, at_seconds: float) -> dict[str, Any]:
    recording = recorder.stop(session_id)
    store.update_manifest(session_id, {"status": "recorded"})
    event = store.append_event(session_id, TimelineEvent.create("recording_stopped", at_seconds, {}))
    return {"event": event, "recording": recording}


@mcp.tool()
def capture_screenshot(session_id: str, at_seconds: float, caption: str = "", monitor_index: int = 1) -> dict[str, Any]:
    session_dir = _session_dir(session_id)
    images_dir = session_dir / "images"
    images_dir.mkdir(exist_ok=True)
    image_path = images_dir / f"screen_{int(at_seconds * 1000)}.png"
    saved = make_screenshot(str(image_path), monitor_index=monitor_index)
    asset = AssetRecord.create("screenshot", saved, metadata={"caption": caption, "monitor_index": monitor_index})
    store.add_asset(session_id, asset)
    store.append_event(session_id, TimelineEvent.create("screenshot", at_seconds, {"asset_id": asset.asset_id, "caption": caption}))
    return asset.to_dict()


@mcp.tool()
def add_section(session_id: str, title: str, at_seconds: float, note: str = "") -> dict[str, Any]:
    return store.append_event(session_id, TimelineEvent.create("section", at_seconds, {"title": title, "note": note}))


@mcp.tool()
def switch_window(session_id: str, at_seconds: float, window_name: str, reason: str = "") -> dict[str, Any]:
    return store.append_event(
        session_id,
        TimelineEvent.create("window_switched", at_seconds, {"window_name": window_name, "reason": reason}),
    )


@mcp.tool()
def add_screenshot(
    session_id: str,
    file_path: str,
    at_seconds: float,
    caption: str = "",
    tags: list[str] | None = None,
    copy_to_session: bool = True,
) -> dict[str, Any]:
    source = Path(file_path)
    if not source.exists():
        raise FileNotFoundError(f"screenshot not found: {file_path}")

    final_path = source
    if copy_to_session:
        images_dir = _session_dir(session_id) / "images"
        images_dir.mkdir(exist_ok=True)
        final_path = images_dir / source.name
        shutil.copy2(source, final_path)

    asset = AssetRecord.create("screenshot", str(final_path), tags=tags, metadata={"caption": caption})
    store.add_asset(session_id, asset)
    store.append_event(session_id, TimelineEvent.create("screenshot", at_seconds, {"asset_id": asset.asset_id, "caption": caption}))
    return asset.to_dict()


@mcp.tool()
def add_code_diff(session_id: str, diff_text: str, at_seconds: float, file_path: str = "") -> dict[str, Any]:
    session_dir = _session_dir(session_id)
    diffs_dir = session_dir / "captures"
    diffs_dir.mkdir(exist_ok=True)
    diff_file = diffs_dir / f"diff_{int(at_seconds * 1000)}.patch"
    diff_file.write_text(diff_text, encoding="utf-8")

    asset = AssetRecord.create("code-diff", str(diff_file), metadata={"file_path": file_path})
    store.add_asset(session_id, asset)
    store.append_event(session_id, TimelineEvent.create("code_diff", at_seconds, {"asset_id": asset.asset_id, "file_path": file_path}))
    return asset.to_dict()


@mcp.tool()
def add_code_snippet(
    session_id: str,
    code: str,
    language: str,
    at_seconds: float,
    file_path: str = "",
    start_line: int = 0,
    end_line: int = 0,
) -> dict[str, Any]:
    payload = {
        "language": language,
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
        "code": code,
    }
    return store.append_event(session_id, TimelineEvent.create("code_snippet", at_seconds, payload))


@mcp.tool()
def add_subtitle(session_id: str, start_seconds: float, end_seconds: float, text: str) -> dict[str, Any]:
    return store.append_event(
        session_id,
        TimelineEvent.create("subtitle", start_seconds, {"end_seconds": end_seconds, "text": text}),
    )


@mcp.tool()
def generate_tts(
    session_id: str,
    text: str,
    at_seconds: float,
    provider: str = "",
    voice: str = "alloy",
    output_filename: str | None = None,
) -> dict[str, Any]:
    used_provider = provider or config.providers.default_tts_provider
    session_dir = _session_dir(session_id)
    audio_dir = session_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    output = audio_dir / (output_filename or f"tts_{int(at_seconds * 1000)}.mp3")

    generation = _tts_with_fallback(used_provider, text, str(output), voice=voice)
    asset = AssetRecord.create("audio-tts", generation["output_path"], metadata={"provider": generation["provider"], "voice": voice})
    store.add_asset(session_id, asset)
    event = store.append_event(session_id, TimelineEvent.create("tts", at_seconds, {"asset_id": asset.asset_id, "text": text, "voice": voice}))
    return {"event": event, "asset": asset.to_dict(), "generation": generation}


@mcp.tool()
def generate_image(
    session_id: str,
    prompt: str,
    at_seconds: float,
    provider: str = "",
    size: str = "1024x1024",
    output_filename: str | None = None,
) -> dict[str, Any]:
    used_provider = provider or config.providers.default_image_provider
    session_dir = _session_dir(session_id)
    images_dir = session_dir / "images"
    images_dir.mkdir(exist_ok=True)
    output = images_dir / (output_filename or f"ai_image_{int(at_seconds * 1000)}.png")

    generation = _image_with_fallback(used_provider, prompt, str(output), size=size)
    asset = AssetRecord.create("generated-image", generation["output_path"], metadata={"provider": generation["provider"], "prompt": prompt})
    store.add_asset(session_id, asset)
    event = store.append_event(session_id, TimelineEvent.create("generated_image", at_seconds, {"asset_id": asset.asset_id, "prompt": prompt}))
    return {"event": event, "asset": asset.to_dict(), "generation": generation}


@mcp.tool()
def add_slide(
    session_id: str,
    at_seconds: float,
    title: str,
    bullets: list[str] | None = None,
    diagram_code: str = "",
    render_image: bool = True,
) -> dict[str, Any]:
    session_dir = _session_dir(session_id)
    slides_dir = session_dir / "slides"
    slides_dir.mkdir(exist_ok=True)
    slide_file = slides_dir / f"slide_{int(at_seconds * 1000)}.md"
    content = "\n".join([f"# {title}", "", *(f"- {x}" for x in (bullets or [])), "", diagram_code])
    slide_file.write_text(content, encoding="utf-8")

    slide_asset = AssetRecord.create("slide", str(slide_file), metadata={"title": title})
    store.add_asset(session_id, slide_asset)
    store.append_event(session_id, TimelineEvent.create("slide", at_seconds, {"asset_id": slide_asset.asset_id, "title": title}))

    image_asset = None
    if render_image:
        image_path = slides_dir / f"slide_{int(at_seconds * 1000)}.png"
        rendered = render_slide_to_image(str(slide_file), str(image_path))
        image_asset = AssetRecord.create("slide-image", rendered, metadata={"title": title})
        store.add_asset(session_id, image_asset)
        store.append_event(session_id, TimelineEvent.create("slide_image", at_seconds, {"asset_id": image_asset.asset_id, "title": title}))

    return {"slide": slide_asset.to_dict(), "slide_image": image_asset.to_dict() if image_asset else None}


@mcp.tool()
def add_media_insert(
    session_id: str,
    at_seconds: float,
    media_type: str,
    source: str,
    caption: str = "",
    copy_local_to_session: bool = True,
) -> dict[str, Any]:
    final_source = source
    local_source = Path(source)
    if local_source.exists() and copy_local_to_session:
        media_dir = _session_dir(session_id) / "captures" / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        copied = media_dir / local_source.name
        shutil.copy2(local_source, copied)
        final_source = str(copied)

    asset = AssetRecord.create(media_type, final_source, metadata={"caption": caption})
    store.add_asset(session_id, asset)
    store.append_event(
        session_id,
        TimelineEvent.create("media_insert", at_seconds, {"asset_id": asset.asset_id, "media_type": media_type, "source": final_source}),
    )
    return asset.to_dict()


@mcp.tool()
def create_video_plan(
    session_id: str,
    template: str,
    objective: str,
    audience: str,
    platform: str,
    include_vertical_variant: bool = True,
) -> dict[str, Any]:
    plan = build_video_plan(template, objective, audience, platform, include_vertical_variant)
    return store.save_plan(session_id, plan)


@mcp.tool()
def list_video_templates() -> list[str]:
    return sorted(TEMPLATES.keys())


@mcp.tool()
def update_timeline_event(session_id: str, event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return store.update_event(session_id, event_id, payload)


@mcp.tool()
def list_assets(session_id: str, kind: str | None = None) -> list[dict[str, Any]]:
    return store.list_assets(session_id, kind=kind)




@mcp.tool()
def queue_tts_job(session_id: str, text: str, at_seconds: float, voice: str = "alloy", provider: str = "") -> dict[str, Any]:
    payload = {"session_id": session_id, "text": text, "at_seconds": at_seconds, "voice": voice, "provider": provider or config.providers.default_tts_provider}
    return store.add_job(session_id, "tts.generate", payload)


@mcp.tool()
def queue_image_job(session_id: str, prompt: str, at_seconds: float, size: str = "1024x1024", provider: str = "") -> dict[str, Any]:
    payload = {"session_id": session_id, "prompt": prompt, "at_seconds": at_seconds, "size": size, "provider": provider or config.providers.default_image_provider}
    return store.add_job(session_id, "image.generate", payload)


@mcp.tool()
def run_jobs_daemon(session_id: str, interval_sec: float = 2.0, max_cycles: int = 30, per_cycle_limit: int = 20) -> list[dict[str, Any]]:
    return worker.run_daemon(session_id, interval_sec=interval_sec, max_cycles=max_cycles, per_cycle_limit=per_cycle_limit)

@mcp.tool()
def list_jobs(session_id: str, status: str | None = None) -> list[dict[str, Any]]:
    return store.list_jobs(session_id, status=status)


@mcp.tool()
def run_jobs(session_id: str, limit: int = 10) -> list[dict[str, Any]]:
    return worker.run_pending(session_id, limit=limit)


@mcp.tool()
def edit_trim_video(session_id: str, input_path: str, start: float, end: float, output_filename: str) -> dict[str, Any]:
    session_dir = _session_dir(session_id)
    output_path = session_dir / "exports" / output_filename
    output_path.parent.mkdir(exist_ok=True)
    result = trim_video(input_path, str(output_path), start, end)
    asset = AssetRecord.create("video-edited", str(output_path), metadata={"operation": "trim", "start": start, "end": end})
    store.add_asset(session_id, asset)
    return {"result": result, "asset": asset.to_dict()}


@mcp.tool()
def edit_concat_videos(session_id: str, input_paths: list[str], output_filename: str, reencode: bool = True) -> dict[str, Any]:
    session_dir = _session_dir(session_id)
    output_path = session_dir / "exports" / output_filename
    output_path.parent.mkdir(exist_ok=True)
    result = concat_videos(input_paths, str(output_path), reencode=reencode)
    asset = AssetRecord.create("video-edited", str(output_path), metadata={"operation": "concat", "inputs": input_paths, "reencode": reencode})
    store.add_asset(session_id, asset)
    return {"result": result, "asset": asset.to_dict()}


@mcp.tool()
def edit_overlay_image(
    session_id: str,
    input_video: str,
    image_path: str,
    output_filename: str,
    x: int = 20,
    y: int = 20,
) -> dict[str, Any]:
    session_dir = _session_dir(session_id)
    output_path = session_dir / "exports" / output_filename
    output_path.parent.mkdir(exist_ok=True)
    result = overlay_image(input_video, image_path, str(output_path), x=x, y=y)
    asset = AssetRecord.create("video-edited", str(output_path), metadata={"operation": "overlay_image", "x": x, "y": y})
    store.add_asset(session_id, asset)
    return {"result": result, "asset": asset.to_dict()}


@mcp.tool()
def render_video(
    session_id: str,
    profile: str = "16:9",
    quality: str = "1080p",
    execute: bool = True,
    apply_timeline: bool = True,
    apply_branding_layer: bool = True,
    lower_third_text: str = "",
) -> dict[str, Any]:
    session_dir = _session_dir(session_id)
    render_payload = build_render_job(str(session_dir), profile=profile, quality=quality)

    sources = _collect_render_sources(session_id)
    if not sources:
        raise ValueError("no source videos found for rendering")
    concat_file = write_concat_file(render_payload["concat_file"], sources)

    result = None
    if execute:
        result = execute_render_job(render_payload)
        if apply_timeline and result:
            timeline = store.load_timeline(session_id)
            timeline_output = session_dir / "exports" / f"timeline_{Path(result['output']).name}"
            assets = store.list_assets(session_id)
            result = compose_with_timeline(result["output"], timeline, str(timeline_output), assets=assets)

    if execute and apply_branding_layer and result:
        branding_output = session_dir / "exports" / f"branded_{Path(result['output']).name}"
        result = apply_branding(
            input_video=result["output"],
            output_video=str(branding_output),
            intro_clip=config.branding.intro_clip,
            outro_clip=config.branding.outro_clip,
            lower_third_text=lower_third_text,
            primary_color=config.branding.color_palette.get("primary", "#5B8DEF"),
        )

    job = store.add_job(
        session_id,
        "render",
        {
            "render": render_payload,
            "sources": sources,
            "concat_file": concat_file,
            "executed": execute,
            "result": result,
            "apply_timeline": apply_timeline,
            "apply_branding_layer": apply_branding_layer,
            "lower_third_text": lower_third_text,
        },
    )

    if result:
        store.add_asset(session_id, AssetRecord.create("video-final", result["output"], metadata={"profile": profile, "quality": quality}))

    return {"job": job, "render": render_payload, "sources": sources, "result": result}


@mcp.tool()
def publish_to_telegram(session_id: str, video_path: str, caption: str, chat_id: str | None = None, dedupe: bool = True) -> dict[str, Any]:
    target_chat = chat_id or config.tokens.telegram_chat_id
    if dedupe:
        timeline = store.load_timeline(session_id).get("events", [])
        for ev in timeline:
            if ev.get("type") == "published.telegram":
                p = ev.get("payload", {})
                if p.get("video_path") == video_path and p.get("chat_id") == target_chat:
                    return {"telegram": {"ok": True, "deduped": True}, "event": ev}

    response = send_video(
        bot_token=config.tokens.telegram_bot_token,
        chat_id=target_chat,
        video_path=video_path,
        caption=caption,
        attempts=3,
    )
    event = store.append_event(
        session_id,
        TimelineEvent.create("published.telegram", 0, {"video_path": video_path, "caption": caption, "chat_id": target_chat}),
    )
    return {"telegram": response, "event": event}


def _register_worker_handlers() -> None:
    def _handle_render(job: dict[str, Any]) -> dict[str, Any]:
        payload = job["payload"]["render"]
        return execute_render_job(payload)

    def _handle_publish_telegram(job: dict[str, Any]) -> dict[str, Any]:
        p = job["payload"]
        return send_video(config.tokens.telegram_bot_token, p.get("chat_id", ""), p["video_path"], p.get("caption", ""))

    def _handle_tts_generate(job: dict[str, Any]) -> dict[str, Any]:
        p = job["payload"]
        session_id = p["session_id"] if "session_id" in p else None
        if not session_id:
            raise ValueError("tts.generate job requires session_id in payload")
        at = float(p.get("at_seconds", 0))
        out = _session_dir(session_id) / "audio" / f"tts_job_{int(at*1000)}.mp3"
        generation = _tts_with_fallback(p.get("provider", ""), p["text"], str(out), p.get("voice", "alloy"))
        asset = AssetRecord.create("audio-tts", generation["output_path"], metadata={"provider": generation["provider"], "voice": p.get("voice", "alloy")})
        store.add_asset(session_id, asset)
        store.append_event(session_id, TimelineEvent.create("tts", at, {"asset_id": asset.asset_id, "text": p["text"], "voice": p.get("voice", "alloy")}))
        return {"generation": generation, "asset_id": asset.asset_id}

    def _handle_image_generate(job: dict[str, Any]) -> dict[str, Any]:
        p = job["payload"]
        session_id = p["session_id"] if "session_id" in p else None
        if not session_id:
            raise ValueError("image.generate job requires session_id in payload")
        at = float(p.get("at_seconds", 0))
        out = _session_dir(session_id) / "images" / f"image_job_{int(at*1000)}.png"
        generation = _image_with_fallback(p.get("provider", ""), p["prompt"], str(out), p.get("size", "1024x1024"))
        asset = AssetRecord.create("generated-image", generation["output_path"], metadata={"provider": generation["provider"], "prompt": p["prompt"]})
        store.add_asset(session_id, asset)
        store.append_event(session_id, TimelineEvent.create("generated_image", at, {"asset_id": asset.asset_id, "prompt": p["prompt"]}))
        return {"generation": generation, "asset_id": asset.asset_id}

    worker.register("render", _handle_render)
    worker.register("publish.telegram", _handle_publish_telegram)
    worker.register("tts.generate", _handle_tts_generate)
    worker.register("image.generate", _handle_image_generate)


_register_worker_handlers()


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
