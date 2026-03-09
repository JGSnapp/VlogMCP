# MCP-инструменты

Инструменты сгруппированы по фазам работы. Всего ~35 инструментов.

---

## Фаза 0: Проект

### `project_create`
Создаёт новый проект.

```
project_create(name: str) → project_id: str
```

Создаёт директорию проекта, инициализирует `project.json`, `event_log.jsonl`,
`timeline.json`, `assets.json`. Статус: `created`.

---

### `project_get`
Получить текущее состояние проекта.

```
project_get(project_id: str) → Project
```

Возвращает манифест проекта: статус, имя, количество активов, есть ли таймлайн.

---

### `project_list`
Список всех проектов.

```
project_list(status?: str) → list[Project]
```

---

## Фаза 1: Запись

### `record_start`
Запускает запись экрана через ffmpeg.

```
record_start(
    project_id: str,
    source: str = "desktop",   # "desktop" | "window:<title>" | "region:<x,y,w,h>"
    fps: int = 30,
    with_audio: bool = True
) → recording_id: str
```

Автоматически добавляет событие `recording_started` в лог.

---

### `record_pause`
Ставит запись на паузу.

```
record_pause(project_id: str) → ok: bool
```

Добавляет событие `recording_paused`.

---

### `record_resume`
Возобновляет запись.

```
record_resume(project_id: str) → ok: bool
```

Добавляет событие `recording_resumed`.

---

### `record_stop`
Останавливает запись.

```
record_stop(project_id: str) → asset_id: str
```

Завершает ffmpeg-процесс. Регистрирует сырой клип как актив `raw_clip`.
Добавляет событие `recording_stopped`. Статус проекта → `recorded`.

---

### `log_event`
Добавляет произвольное событие в лог записи. Вызывается во время записи.

```
log_event(
    project_id: str,
    type: str,         # "section" | "note" | "window_switch" | "screenshot" | "code_snippet"
    label: str = "",
    payload: dict = {}
) → event_id: str
```

Пример во время записи:
```
log_event(project_id, type="section", label="Нашли корень проблемы")
log_event(project_id, type="note",    label="Здесь стоит вернуться")
```

---

## Фаза 2: Анализ записи

### `event_log_get`
Читает лог событий записи.

```
event_log_get(
    project_id: str,
    from_ts?: float,   # фильтр по времени записи (секунды)
    to_ts?: float,
    types?: list[str]  # фильтр по типам событий
) → list[Event]
```

AI использует это чтобы понять структуру записи и решить, что брать в монтаж.

---

## Фаза 3: Генерация активов

### `screenshot_take`
Делает скриншот рабочего стола и регистрирует как актив.

```
screenshot_take(
    project_id: str,
    monitor: int = 1
) → asset_id: str
```

---

### `code_snapshot`
Создаёт PNG с синтаксически подсвеченным кодом из файла.

```
code_snapshot(
    project_id: str,
    file_path: str,
    start_line?: int,
    end_line?: int,
    highlight_lines?: list[int]   # строки выделить фоном
) → asset_id: str
```

---

### `code_diff`
Создаёт PNG с красивым diff двух файлов или двух строк текста.

```
code_diff(
    project_id: str,
    before: str,       # путь к файлу или текст
    after: str,        # путь к файлу или текст
    lang?: str,
    title?: str        # заголовок diff-карточки
) → asset_id: str
```

---

### `terminal_capture`
Создаёт PNG с выводом терминала (terminal-стиль, тёмный фон, моноширинный шрифт).

```
terminal_capture(
    project_id: str,
    command: str,      # строка команды (только для отображения)
    output: str,       # текст вывода
    theme?: str        # "dark" | "light"
) → asset_id: str
```

---

### `git_log_render`
Создаёт PNG с визуализацией истории коммитов.

```
git_log_render(
    project_id: str,
    repo_path: str,
    n_commits: int = 10,
    highlight_commit?: str   # SHA коммита для выделения
) → asset_id: str
```

---

### `diagram_create`
Создаёт PNG с диаграммой.

```
diagram_create(
    project_id: str,
    type: str,         # "bar_chart" | "pie" | "flowchart" | "table" | "timeline_chart"
    data: dict,        # зависит от типа диаграммы
    title?: str,
    theme?: str        # "dark" | "light"
) → asset_id: str
```

Пример `data` для `bar_chart`:
```json
{
  "labels": ["До", "После"],
  "values": [2400, 140],
  "unit": "мс",
  "color": "#5B8DEF"
}
```

---

### `tts_generate`
Генерирует MP3-аудио из текста.

```
tts_generate(
    project_id: str,
    text: str,
    voice?: str,       # голос провайдера
    provider?: str     # "openai" | "elevenlabs" | auto
) → asset_id: str
```

Fallback: openai → elevenlabs → error.

---

### `image_generate`
Генерирует изображение через AI.

```
image_generate(
    project_id: str,
    prompt: str,
    size?: str         # "1920x1080" | "1024x1024" | "1080x1920"
) → asset_id: str
```

---

### `asset_preview`
Возвращает превью актива.

```
asset_preview(asset_id: str) → base64_png: str
```

Для аудио возвращает метаданные (duration, provider, text).

---

### `asset_list`
Список активов проекта.

```
asset_list(
    project_id: str,
    kind?: str         # фильтр по типу
) → list[Asset]
```

---

## Фаза 3б: Работа с библиотекой и брендингом

### `library_list`
Список материалов из медиабиблиотеки.

```
library_list(
    kind?: str,        # "meme" | "sfx" | "sticker" | "cutaway" | "music"
    tags?: list[str]   # фильтр по тегам
) → list[LibraryItem]
```

---

### `library_search`
Поиск по библиотеке.

```
library_search(
    query: str,        # текстовый запрос по тегам и именам
    kind?: str
) → list[LibraryItem]
```

Пример: `library_search("баг ошибка")` → `[this_is_fine, error_boop, ...]`

---

### `library_preview`
Превью элемента библиотеки.

```
library_preview(lib_id: str) → base64_png | metadata
```

---

### `branding_get`
Получить текущий конфиг брендинга.

```
branding_get() → BrandingConfig
```

AI должен вызвать это в начале работы, чтобы знать какие шрифты, цвета,
плашки и медиа доступны.

---

### `branding_list_plates`
Список доступных плашек из брендинга.

```
branding_list_plates() → list[PlateInfo]
```

---

### `branding_preview_plate`
Превью плашки.

```
branding_preview_plate(plate: str) → base64_png
```

---

### `branding_list_cutaways`
Список брендинговых перебивок.

```
branding_list_cutaways() → list[CutawayInfo]
```

---

## Фаза 4: Монтажный таймлайн

### `timeline_create`
Создаёт монтажный таймлайн.

```
timeline_create(
    project_id: str,
    duration: float    # длина финального видео в секундах
) → timeline_id: str
```

---

### Инструменты фонового слоя

#### `timeline_add_clip`
Добавляет вырезку из сырой записи как фоновый слой.

```
timeline_add_clip(
    timeline_id: str,
    asset_id: str,     # raw_clip актив
    start: float,      # секунда финального видео
    duration: float,
    source_in: float,  # секунда начала вырезки из сырого клипа
    source_out: float  # секунда конца вырезки
) → element_id: str
```

#### `timeline_add_image_bg`
Картинка на весь экран как фон.

```
timeline_add_image_bg(
    timeline_id: str,
    asset_id: str,
    start: float,
    duration: float
) → element_id: str
```

#### `timeline_add_color_bg`
Однотонный цвет как фон.

```
timeline_add_color_bg(
    timeline_id: str,
    color: str,        # hex, например "#121219"
    start: float,
    duration: float
) → element_id: str
```

#### `timeline_add_cutaway`
Перебивка (короткий клип) как фоновый слой.

```
timeline_add_cutaway(
    timeline_id: str,
    source: str,       # "library" | "branding"
    id: str,           # lib_id или id из branding.clips.cutaways
    start: float,
    duration?: float   # если не задана — длина клипа
) → element_id: str
```

---

### Инструменты объектного слоя

#### `timeline_add_text`
Текст поверх фона.

```
timeline_add_text(
    timeline_id: str,
    text: str,
    style: str,        # "branding.title" | "branding.subtitle" | "branding.body" | "branding.caption"
    x: int | str,      # число или якорь: "center", "right-40"
    y: int | str,
    z: int = 1,
    start: float,
    duration: float,
    animate_in?: str,
    animate_out?: str
) → element_id: str
```

#### `timeline_add_image`
Картинка поверх фона (скриншот, схема, AI-изображение и т.д.).

```
timeline_add_image(
    timeline_id: str,
    asset_id: str,
    x: int | str,
    y: int | str,
    width?: int,       # если не задана — оригинальный размер
    z: int = 1,
    start: float,
    duration: float,
    animate_in?: str,
    animate_out?: str
) → element_id: str
```

#### `timeline_add_code_block`
PNG с кодом или диффом поверх фона.

```
timeline_add_code_block(
    timeline_id: str,
    asset_id: str,     # kind: code_snapshot | code_diff | terminal_capture
    x: int | str,
    y: int | str,
    width?: int,
    z: int = 2,
    start: float,
    duration: float
) → element_id: str
```

#### `timeline_add_lower_third`
Брендинговая нижняя плашка с именем и должностью.

```
timeline_add_lower_third(
    timeline_id: str,
    title: str,
    subtitle: str,
    start: float,
    duration: float,
    z: int = 10
) → element_id: str
```

#### `timeline_add_plate`
Карточка из брендинга с текстом.

```
timeline_add_plate(
    timeline_id: str,
    plate: str,        # "section_card" | "quote_card" | "fact_card" | "cta_card"
    text: str,
    x: int | str,
    y: int | str,
    z: int = 5,
    start: float,
    duration: float,
    animate_in?: str
) → element_id: str
```

#### `timeline_add_meme`
Мем из медиабиблиотеки.

```
timeline_add_meme(
    timeline_id: str,
    lib_id: str,
    x: int | str,
    y: int | str,
    width?: int,
    z: int = 2,
    start: float,
    duration: float
) → element_id: str
```

#### `timeline_add_sticker`
Анимированный стикер/GIF из библиотеки.

```
timeline_add_sticker(
    timeline_id: str,
    lib_id: str,
    x: int | str,
    y: int | str,
    scale: float = 1.0,
    z: int = 3,
    start: float,
    duration?: float   # если не задана — длина GIF
) → element_id: str
```

#### `timeline_add_progress_bar`
Индикатор прогресса (шаг N из M).

```
timeline_add_progress_bar(
    timeline_id: str,
    current: int,
    total: int,
    x: int | str,
    y: int | str,
    z: int = 8,
    start: float,
    duration: float
) → element_id: str
```

---

### Инструменты аудио-дорожек

#### `timeline_add_audio`
Добавляет аудио-актив на дорожку.

```
timeline_add_audio(
    timeline_id: str,
    asset_id: str,     # kind: tts
    start: float,
    volume: float = 1.0,
    mix: str = "duck_main"   # "duck_main" | "add" | "replace"
) → element_id: str
```

#### `timeline_add_sfx`
Добавляет звуковой эффект из библиотеки.

```
timeline_add_sfx(
    timeline_id: str,
    lib_id: str,
    start: float,
    volume: float = 0.7
) → element_id: str
```

#### `timeline_add_music`
Добавляет фоновую музыку из библиотеки.

```
timeline_add_music(
    timeline_id: str,
    lib_id: str,
    start: float,
    volume: float = 0.15,
    loop: bool = True
) → element_id: str
```

---

### Переходы

#### `timeline_add_transition`
Добавляет переход между соседними фоновыми клипами.

```
timeline_add_transition(
    timeline_id: str,
    after_bg_id: str,         # id фонового элемента после которого переход
    type: str,                # "fade" | "wipeleft" | "wiperight" | "slideleft" |
                              # "slideright" | "circleopen" | "pixelize"
    duration: float = 0.5
) → element_id: str
```

---

### Управление элементами

#### `timeline_remove`
Удаляет элемент из таймлайна.

```
timeline_remove(
    timeline_id: str,
    element_id: str
) → ok: bool
```

---

## Фаза 5: Просмотр и корректировка

### `timeline_inspect`
Показывает текущее состояние таймлайна в виде текстовой схемы.

```
timeline_inspect(
    timeline_id: str,
    from_sec?: float,  # начало временного окна
    to_sec?: float     # конец временного окна
) → str
```

Пример вывода:
```
00:00 ────────────────────────────────── 03:00

BG:   [clip  rec_01  (src 8:00→9:30)  0:00─1:30]
      [color #121219                   1:30─2:00]
      [image diagram_arch              2:00─3:00]

OBJ:  z=10  lower_third  "Kirill Kostenko"  0:00─3:00
      z= 5  plate  section_card "Шаг 1"    0:00─0:04
      z= 2  code_block  diff_auth.png      1:30─1:55  left
      z= 2  meme  thinking_guy             1:50─1:55  corner
      z= 1  text  "Анализ бага"            0:00─0:05  top_left
      z= 1  text  "Строка 47"             0:45─0:53  bottom

AUD:  [tts  tts_intro.mp3    0:00  duck_main  vol=1.0]
      [sfx  drum_hit         1:30  add        vol=0.7]
      [mus  lofi_chill       0:00  add        vol=0.15  loop]

TRN:  [fade @1:30 dur=0.5s]  [wipeleft @2:00 dur=0.8s]
```

---

### `preview_frame`
Рендерит один кадр финального видео с учётом всех объектов таймлайна.

```
preview_frame(
    project_id: str,
    at_seconds: float
) → base64_png: str
```

Быстрая операция (один кадр, без кодирования). Используется для итеративной
проверки монтажа.

---

### `preview_clip`
Рендерит короткий фрагмент видео в низком качестве.

```
preview_clip(
    project_id: str,
    from_sec: float,
    to_sec: float,
    quality?: str    # "low" (по умолчанию) | "medium"
) → file_path: str
```

---

## Фаза 6: Рендер

### `render`
Рендерит финальное видео.

```
render(
    project_id: str,
    quality?: str    # "720p" | "1080p" (по умолчанию) | "4k"
) → job_id: str
```

Процесс рендера:
1. Вставляет intro-клип из брендинга
2. Рендерит монтажный таймлайн (фон + объекты + аудио + переходы)
3. Накладывает watermark из брендинга
4. Вставляет outro-клип из брендинга
5. Сохраняет в `exports/`

---

### `render_status`
Статус рендер-задачи.

```
render_status(job_id: str) → { status, progress, output_path?, error? }
```

---

## Фаза 7: Публикация

### `publish`
Публикует финальное видео.

```
publish(
    project_id: str,
    platform: str,     # "telegram" | "youtube"
    caption?: str,
    output_path?: str  # если не указан — последний экспорт проекта
) → { ok, url?, message_id? }
```

---

## Справочник позиционирования

Значения для `x` и `y`:

| Запись | Значение |
|---|---|
| `60` | 60 пикселей от левого/верхнего края |
| `"center"` | Центр по этой оси |
| `"right-20"` | 20 пикселей от правого края |
| `"bottom-120"` | 120 пикселей от нижнего края |
| `"left+40"` | 40 пикселей от левого края |
| `"top+40"` | 40 пикселей от верхнего края |

## Справочник стилей текста

| Стиль | Привязан к |
|---|---|
| `branding.title` | `branding.fonts.title` |
| `branding.subtitle` | `branding.fonts.subtitle` |
| `branding.body` | `branding.fonts.body` |
| `branding.code` | `branding.fonts.code` |
| `branding.caption` | `branding.fonts.caption` |
