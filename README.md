# VlogMCP

MCP-сервер для AI-агентов, который превращает рабочую сессию в структурированный видео-отчёт.

## Что уже реализовано

- Кроссплатформенная запись экрана через `ffmpeg`:
  - Windows: `gdigrab`
  - Linux: `x11grab`
  - macOS: `avfoundation`
- Управление записью: старт/пауза/возобновление/стоп.
- Режимы захвата: full screen, region, window (где поддерживается ffmpeg backend) + tools диагностики `capture_capabilities` и `list_capture_devices`.
- Скриншоты на Windows/Linux/macOS через `mss`.
- Базовое редактирование видео через `ffmpeg`: `trim`, `concat(copy/reencode)`, `overlay image`.
- Реальный render с автосборкой concat-файла, timeline-композицией (sections/subtitles/window/code/image overlays + TTS audio mix) и branding-слоем (intro/outro/lower-third).
- Автогенерация слайдов: markdown -> PNG.
- Генерация TTS и изображений через нескольких провайдеров с retry/fallback.
- Публикация в Telegram Bot API с retry.
- Наблюдаемость: structured event logs + `health_check` tool.
- Воркер задач: статусная модель jobs (`queued/in_progress/completed/failed`), `run_jobs` и `run_jobs_daemon`.

## Структура хранения

Для каждой сессии создаётся папка `session_<id>`:

```text
sessions/
  session_xxx/
    manifest.json
    timeline.json
    assets.json
    plan.json
    jobs.json
    captures/
    images/
    audio/
    slides/
    exports/
```

## MCP tools

- Базовые: `health_check`, `capture_capabilities`, `list_capture_devices`, `init_workspace`, `get_config`, `create_session`, `list_sessions`, `get_session`
- Захват: `start_recording`, `pause_recording`, `resume_recording`, `stop_recording`, `capture_screenshot`
- Таймлайн: `add_section`, `switch_window`, `add_subtitle`, `update_timeline_event`
- Контент: `add_screenshot`, `add_code_diff`, `add_code_snippet`, `add_slide`, `add_media_insert`
- AI-генерация: `generate_tts`, `generate_image`, `queue_tts_job`, `queue_image_job`
- Монтаж: `edit_trim_video`, `edit_concat_videos`, `edit_overlay_image`
- Планирование: `list_video_templates`, `create_video_plan`
- Экспорт/публикация: `render_video`, `publish_to_telegram`
- Jobs: `list_jobs`, `run_jobs`, `run_jobs_daemon`

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
vlog-mcp
```

## Системные требования

- `ffmpeg` в `PATH`.
- Для Linux capture нужен X11 display.
- Для macOS требуются permissions на Screen Recording.
