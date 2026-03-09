# Модель данных

## Проект

```json
{
  "project_id": "proj_a3f9bc2",
  "name": "Исправляем баг с авторизацией",
  "status": "composing",
  "branding_id": "brand_default",
  "created_at": 1741300000,
  "updated_at": 1741303600,
  "dir": "./projects/proj_a3f9bc2"
}
```

Статусы и допустимые переходы:

```
created
  └─► recording
        └─► recorded
              └─► composing
                    └─► rendered
                          └─► published
```

Структура директории проекта:

```
projects/proj_a3f9bc2/
├── project.json        ← манифест проекта
├── event_log.jsonl     ← лог событий записи (append-only)
├── timeline.json       ← монтажный таймлайн
├── assets.json         ← реестр активов
├── captures/           ← сырые записи экрана (.mp4)
├── screenshots/        ← скриншоты (.png)
├── audio/              ← TTS-аудио (.mp3)
├── generated/          ← code_diff, diagrams, ai_images (.png)
└── exports/            ← финальное видео (.mp4)
```

---

## Лог событий записи

Файл: `event_log.jsonl` (каждая строка — JSON-объект, append-only).

### Схема события

```json
{
  "event_id": "evt_7a2c",
  "type": "section",
  "ts": 120.5,
  "created_at": 1741300120,
  "payload": {}
}
```

`ts` — секунда **сырой записи** в момент события.

### Типы событий

| Тип | Payload | Описание |
|---|---|---|
| `recording_started` | `{ "recording_id": "...", "source": "desktop" }` | Старт записи |
| `recording_paused` | `{}` | Пауза |
| `recording_resumed` | `{}` | Продолжение |
| `recording_stopped` | `{ "duration": 2400.0 }` | Конец записи |
| `section` | `{ "label": "Открываем auth.py", "note": "..." }` | Смысловой раздел |
| `screenshot` | `{ "asset_id": "ast_screen_1", "monitor": 1 }` | Снимок экрана |
| `window_switch` | `{ "to": "VS Code - auth.py" }` | Переключение окна |
| `code_snippet` | `{ "asset_id": "ast_code_1", "file": "src/auth.py" }` | Фрагмент кода |
| `note` | `{ "text": "Здесь нашли корень проблемы" }` | Произвольная заметка |

Пример заполненного лога:

```jsonl
{"event_id":"evt_1","type":"recording_started","ts":0,"payload":{"recording_id":"rec_01","source":"desktop"}}
{"event_id":"evt_2","type":"section","ts":120,"payload":{"label":"Открываем auth.py"}}
{"event_id":"evt_3","type":"screenshot","ts":145,"payload":{"asset_id":"ast_scr_1"}}
{"event_id":"evt_4","type":"window_switch","ts":280,"payload":{"to":"Terminal"}}
{"event_id":"evt_5","type":"section","ts":510,"payload":{"label":"Нашли баг"}}
{"event_id":"evt_6","type":"code_snippet","ts":530,"payload":{"asset_id":"ast_code_1","file":"auth.py","lines":"40-55"}}
{"event_id":"evt_7","type":"section","ts":900,"payload":{"label":"Исправляем"}}
{"event_id":"evt_8","type":"recording_stopped","ts":2400,"payload":{"duration":2400.0}}
```

---

## Монтажный таймлайн

Файл: `timeline.json`

Все временны́е значения здесь — секунды **финального видео**, не сырой записи.

```json
{
  "timeline_id": "tl_01",
  "project_id": "proj_a3f9bc2",
  "duration": 180.0,
  "background": [...],
  "objects": [...],
  "audio": [...],
  "transitions": [...]
}
```

### background — фоновый слой

Элементы не перекрываются по времени (по одному фону на каждый момент).

```json
[
  {
    "id": "bg1",
    "type": "clip",
    "asset_id": "ast_rec_01",
    "start": 0.0,
    "duration": 90.0,
    "source_in": 480.0,
    "source_out": 570.0
  },
  {
    "id": "bg2",
    "type": "color",
    "color": "#121219",
    "start": 90.0,
    "duration": 30.0
  },
  {
    "id": "bg3",
    "type": "image",
    "asset_id": "ast_diagram_arch",
    "start": 120.0,
    "duration": 60.0
  }
]
```

Типы фона:

| Тип | Параметры | Описание |
|---|---|---|
| `clip` | `asset_id`, `source_in`, `source_out` | Вырезка из сырой записи |
| `color` | `color` (hex) | Однотонный цвет |
| `image` | `asset_id` | Картинка на весь экран |
| `cutaway` | `lib_id` или `asset_id` | Перебивка (клип из библиотеки или брендинга) |

### objects — объекты поверх фона

Каждый объект имеет позицию, z-индекс и временной интервал.

```json
[
  {
    "id": "o1",
    "type": "text",
    "text": "Анализ бага",
    "style": "branding.title",
    "x": 60, "y": 40,
    "z": 1,
    "start": 0.0, "duration": 5.0,
    "animate_in": "fade",
    "animate_out": "fade"
  },
  {
    "id": "o2",
    "type": "text",
    "text": "Строка 47: null pointer",
    "style": "branding.subtitle",
    "x": "center", "y": "bottom-120",
    "z": 1,
    "start": 45.0, "duration": 8.0
  },
  {
    "id": "o3",
    "type": "image",
    "asset_id": "ast_screenshot_1",
    "x": "right-20", "y": 20,
    "width": 600,
    "z": 2,
    "start": 60.0, "duration": 15.0,
    "animate_in": "slide_left"
  },
  {
    "id": "o4",
    "type": "code_block",
    "asset_id": "ast_code_diff_1",
    "x": 40, "y": 200,
    "width": 900,
    "z": 2,
    "start": 90.0, "duration": 25.0
  },
  {
    "id": "o5",
    "type": "meme",
    "lib_id": "thinking_guy",
    "x": "right-160", "y": "bottom-160",
    "width": 140,
    "z": 2,
    "start": 110.0, "duration": 5.0
  },
  {
    "id": "o6",
    "type": "sticker",
    "lib_id": "fire",
    "x": 400, "y": 300,
    "scale": 1.5,
    "z": 3,
    "start": 88.0, "duration": 2.5
  },
  {
    "id": "o7",
    "type": "lower_third",
    "title": "Kirill Kostenko",
    "subtitle": "Backend Engineer",
    "start": 0.0, "duration": 180.0,
    "z": 10
  },
  {
    "id": "o8",
    "type": "plate",
    "plate": "section_card",
    "text": "Шаг 1: Воспроизводим баг",
    "x": 60, "y": 60,
    "z": 5,
    "start": 0.0, "duration": 4.0
  },
  {
    "id": "o9",
    "type": "progress_bar",
    "current": 1, "total": 4,
    "x": 0, "y": "bottom-8",
    "z": 8,
    "start": 0.0, "duration": 90.0
  }
]
```

#### Типы объектов

| Тип | Специфичные параметры | Описание |
|---|---|---|
| `text` | `text`, `style` | Произвольный текст |
| `image` | `asset_id`, `width?` | Картинка из активов проекта |
| `code_block` | `asset_id`, `width?` | PNG с кодом/диффом |
| `lower_third` | `title`, `subtitle` | Брендинговая нижняя плашка |
| `plate` | `plate` (имя из брендинга), `text` | Карточка из брендинга с текстом |
| `meme` | `lib_id` | Мем из библиотеки |
| `sticker` | `lib_id`, `scale?` | Стикер/GIF из библиотеки |
| `shape` | `shape_type`, `color`, `width`, `height` | Прямоугольник, круг |
| `progress_bar` | `current`, `total` | Индикатор прогресса шагов |

#### Позиционирование

`x` и `y` принимают:
- Число в пикселях: `60`, `200`
- Якорное значение: `"center"`, `"right-20"`, `"bottom-120"`, `"left+40"`

#### Анимации

`animate_in` / `animate_out`: `fade`, `slide_left`, `slide_right`, `slide_up`, `slide_down`, `zoom_in`, `zoom_out`

### audio — аудио-дорожки

```json
[
  {
    "id": "a1",
    "type": "asset",
    "asset_id": "ast_tts_intro",
    "start": 0.0,
    "volume": 1.0,
    "mix": "duck_main"
  },
  {
    "id": "a2",
    "type": "lib",
    "lib_id": "sfx/drum_hit",
    "start": 90.0,
    "volume": 0.7,
    "mix": "add"
  },
  {
    "id": "a3",
    "type": "lib",
    "lib_id": "music/lofi_chill",
    "start": 0.0,
    "volume": 0.15,
    "mix": "add",
    "loop": true
  }
]
```

`mix` — режим микширования:
- `duck_main` — понижает громкость основного аудио пока звучит этот трек
- `add` — добавляется поверх основного без изменения его громкости
- `replace` — полностью заменяет основное аудио в этот момент

### transitions — переходы между фоновыми клипами

```json
[
  { "after": "bg1", "type": "fade",     "duration": 0.5 },
  { "after": "bg2", "type": "wipeleft", "duration": 0.8 }
]
```

Типы переходов: `fade`, `wipeleft`, `wiperight`, `slideleft`, `slideright`, `circleopen`, `pixelize`

---

## Реестр активов

Файл: `assets.json` (список объектов).

```json
[
  {
    "asset_id": "ast_rec_01",
    "kind": "raw_clip",
    "path": "captures/recording_01.mp4",
    "created_at": 1741300000,
    "metadata": {
      "duration": 2400.0,
      "fps": 30,
      "resolution": "1920x1080",
      "has_audio": true
    }
  },
  {
    "asset_id": "ast_code_diff_1",
    "kind": "code_diff",
    "path": "generated/diff_auth_py.png",
    "created_at": 1741303000,
    "metadata": {
      "file": "src/auth.py",
      "lang": "python",
      "lines_added": 12,
      "lines_removed": 3,
      "commit": "a3f9bc2"
    }
  },
  {
    "asset_id": "ast_tts_intro",
    "kind": "tts",
    "path": "audio/tts_intro.mp3",
    "created_at": 1741303100,
    "metadata": {
      "text": "Сегодня разберём баг...",
      "voice": "nova",
      "provider": "openai",
      "duration": 12.3
    }
  },
  {
    "asset_id": "ast_diagram_arch",
    "kind": "diagram",
    "path": "generated/diagram_arch.png",
    "created_at": 1741303200,
    "metadata": {
      "diagram_type": "flowchart",
      "width": 1920,
      "height": 1080
    }
  }
]
```

#### Виды активов (`kind`)

| kind | Описание |
|---|---|
| `raw_clip` | Сырая запись экрана |
| `screenshot` | Скриншот рабочего стола |
| `code_diff` | PNG с diff файла |
| `code_snapshot` | PNG с синтаксической подсветкой кода |
| `terminal_capture` | PNG с выводом терминала |
| `git_log` | PNG с историей коммитов |
| `diagram` | PNG с диаграммой |
| `tts` | MP3 с TTS-озвучкой |
| `image_ai` | AI-сгенерированное изображение |
| `imported` | Импортированный файл (видео, картинка) |

---

## Конфиг брендинга

Файл: `branding.json` (задаётся администратором, AI только читает).

Полная схема описана в [branding.md](branding.md).

---

## Конфиг медиабиблиотеки

Файл: `library/index.json` (задаётся администратором, AI только читает).

Полная схема описана в [library.md](library.md).
