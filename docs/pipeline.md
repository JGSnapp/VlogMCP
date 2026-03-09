# Пайплайн: от записи до публикации

## Полная схема

```
┌─────────────────────────────────────────────────────────────────────┐
│                          ИСТОЧНИКИ                                   │
│                                                                      │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │  ЗАПИСЬ ЭКРАНА   │  │    БИБЛИОТЕКА     │  │     БРЕНДИНГ      │  │
│  │  raw_clip.mp4   │  │  memes/sfx/music  │  │  intro/outro/     │  │
│  │  event_log      │  │  cutaways/stickers│  │  plates/fonts/    │  │
│  └────────┬────────┘  └────────┬─────────┘  │  watermark        │  │
│           │                    │             └─────────┬─────────┘  │
└───────────┼────────────────────┼───────────────────────┼────────────┘
            │                    │                        │
            ▼                    │                        │
   ┌─────────────────┐           │                        │
   │  ГЕНЕРАЦИЯ      │           │                        │
   │  АКТИВОВ        │           │                        │
   │                 │           │                        │
   │  code_diff      │           │                        │
   │  code_snapshot  │           │                        │
   │  terminal_cap   │           │                        │
   │  git_log        │           │                        │
   │  diagram        │           │                        │
   │  tts            │           │                        │
   │  image_ai       │           │                        │
   └────────┬────────┘           │                        │
            │                    │                        │
            └───────────┬────────┘                        │
                        ▼                                 │
            ┌─────────────────────┐                       │
            │  МОНТАЖНЫЙ          │                       │
            │  ТАЙМЛАЙН           │                       │
            │                     │                       │
            │  background[]       │                       │
            │  objects[]          │                       │
            │  audio[]            │                       │
            │  transitions[]      │                       │
            └──────────┬──────────┘                       │
                       │                                  │
                       ▼                                  │
            ┌─────────────────────┐                       │
            │  РЕНДЕРЕР           │◄──────────────────────┘
            │                     │  (читает брендинг)
            │  ffmpeg passes      │
            └──────────┬──────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │   final_video.mp4   │
            └──────────┬──────────┘
                       │
                       ▼
                 ПУБЛИКАЦИЯ
              (Telegram / YouTube)
```

---

## Фаза 1: Запись

```
record_start() → ffmpeg запускается в фоне
                 пишет raw_clip.mp4 в captures/

[во время записи]
log_event(type="section", label="...")
log_event(type="note", label="...")
screenshot_take() → регистрирует asset, добавляет событие в лог

record_stop() → ffmpeg завершается
                raw_clip регистрируется как актив kind=raw_clip
                статус проекта → "recorded"
```

**Платформенные бэкенды ffmpeg:**

| ОС | Видео | Аудио |
|---|---|---|
| Windows | `gdigrab` (desktop/window) | `dshow` |
| macOS | `avfoundation` | `avfoundation` |
| Linux | `x11grab` + `$DISPLAY` | `pulse` |

---

## Фаза 2: Анализ

AI вызывает `event_log_get()` и изучает что произошло при записи:

- Где были разделы (`section`)
- Что отметил пользователь как важное (`note`)
- Какие скриншоты сделаны
- Сколько времени заняла каждая часть

На основе анализа AI принимает решения:
- Какие куски взять в финальное видео
- Какова логическая структура видео (разделы)
- Нужны ли перебивки (cutaways) между частями
- Какая музыка подойдёт по настроению

---

## Фаза 3: Генерация активов

AI параллельно генерирует всё необходимое:

```
code_diff(before="auth.py.bak", after="auth.py")
  → ast_diff_1 (PNG с diff-ом)

terminal_capture(command="pytest", output="...12 passed...")
  → ast_terminal_1 (PNG с выводом)

tts_generate(text="Сегодня мы разберём баг...")
  → ast_tts_1 (MP3)

diagram_create(type="bar_chart", data={...})
  → ast_diagram_1 (PNG)
```

Все активы регистрируются в `assets.json` с метаданными.

---

## Фаза 4: Монтаж

AI строит монтажный таймлайн — декларативную инструкцию для рендерера.

### Типичная структура монтажа

```
0:00─0:30  ВСТУПЛЕНИЕ
  Фон: raw_clip (src: 0:00─0:30)
  Объект: plate "section_card" "Вступление" 0:00─0:05
  Объект: lower_third "Автор" 0:00─0:30
  Аудио: tts "Сегодня разберём..." duck_main
  Аудио: music/lofi_chill vol=0.15 loop

0:30─1:30  СУТЬ ПРОБЛЕМЫ
  Фон: color #121219 (тёмный)
  Объект: code_block diff_auth.png слева
  Объект: text "Строка 47: null pointer" bottom
  Аудио: sfx/drum_hit @0:30
  Аудио: tts "Проблема в том что..." duck_main

1:30─2:00  ПЕРЕБИВКА
  Фон: cutaway branding/typing.mp4
  (без объектов, музыка продолжается)

2:00─3:00  РЕШЕНИЕ
  Фон: raw_clip (src: 23:00─24:00) ← вырезка из записи
  Объект: plate "section_card" "Решение" 2:00─2:05
  Объект: sticker "checkmark" @2:55 center
  Аудио: sfx/success_bell @2:58
```

### Итеративная корректировка

После каждого значимого добавления AI проверяет результат:

```
timeline_add_code_block(...)
preview_frame(at=45.0)  → "текст перекрывает код, нужно сдвинуть"
timeline_remove(element_id)
timeline_add_code_block(..., x="left+40", y=220)
preview_frame(at=45.0)  → "теперь ок"
```

---

## Фаза 5: Рендер

### Что делает рендерер

```
render(project_id, quality="1080p")
```

**Шаг 1: Сборка видео-дорожки**

Рендерер читает `background[]` таймлайна и формирует видеопоследовательность:

```
для каждого фонового элемента:
  clip    → ffmpeg -ss source_in -t duration clip.mp4
  color   → ffmpeg -f lavfi -i color=c=color:s=1920x1080
  image   → ffmpeg -loop 1 -i image.png -t duration
  cutaway → ffmpeg -i cutaway.mp4 -t duration

склеить через concat demuxer
применить переходы (xfade между соседними клипами)
→ bg_track.mp4
```

**Шаг 2: Наложение объектов**

Рендерер читает `objects[]` и строит ffmpeg filter_complex:

```
для каждого объекта (сортировка по z_index):
  text      → drawtext=text=...:enable='between(t,start,end)'
  image     → overlay=x:y:enable='between(t,start,end)'
  code_block → overlay (PNG поверх)
  lower_third → overlay (plate PNG) + drawtext сверху
  plate     → overlay (plate PNG) + drawtext сверху
  meme      → overlay с выбором позиции
  sticker   → overlay (GIF через movie filter)
  progress_bar → drawbox + drawtext
→ применить всё единым filter_complex
→ content_with_objects.mp4
```

**Шаг 3: Микширование аудио**

```
для каждого аудио-элемента:
  duck_main → включить сайдчейн: снизить громкость основного на -15dB
  add       → amix с основным аудио
  replace   → заменить основное в этот период

применить loop для музыки (если loop=true)
→ mixed_audio.aac
```

**Шаг 4: Применение брендинга**

```
1. Взять branding.clips.intro → intro.mp4
2. Взять content_with_objects.mp4
3. Взять branding.clips.outro → outro.mp4
4. Склеить: [intro] + [content] + [outro] → combined.mp4
5. Наложить watermark:
   ffmpeg overlay=branding.watermark.asset:x=...:y=...:alpha=opacity
→ final.mp4
```

**Шаг 5: Финальное кодирование**

```
ffmpeg -i combined.mp4 -i mixed_audio.aac
  -c:v libx264 -crf 18 -preset slow
  -c:a aac -b:a 192k
  -s 1920x1080
  exports/final_1080p.mp4
```

---

## Фаза 6: Публикация

### Telegram

```
publish(project_id, platform="telegram", caption="...")
```

- Берёт последний `exports/final_*.mp4`
- POST multipart к `api.telegram.org/bot{token}/sendVideo`
- Retry: 3 попытки с exponential backoff
- Ограничение размера: 50MB (при превышении — пережатие с `-fs 49M`)

### YouTube (планируется)

```
publish(project_id, platform="youtube", caption="...")
```

---

## preview_frame: как работает быстрый превью

`preview_frame(project_id, at_seconds=45.0)`

```
1. Найти фоновый элемент активный в t=45.0
   → clip: извлечь один кадр ffmpeg -ss (source_in + 45-start) -vframes 1
   → color: создать однотонный PNG
   → image: взять исходную картинку

2. Найти все объекты активные в t=45.0 (start ≤ 45 < start+duration)
   Сортировать по z_index

3. Последовательно нарисовать поверх кадра:
   text      → PIL ImageDraw.text()
   image     → PIL Image.paste()
   code_block → PIL Image.paste()
   lower_third → PIL Image.paste() (plate) + PIL ImageDraw.text()
   meme/sticker → PIL Image.paste()
   progress_bar → PIL ImageDraw.rectangle() + text()

4. Вернуть PNG как base64

Время операции: ~200мс (нет кодирования, только один кадр)
```

Это позволяет AI проверять монтаж без полного рендера.

---

## Объектная модель ffmpeg filter_complex

Финальный filter_complex для типичного видео выглядит так:

```
[0:v]
  drawtext=text='Анализ бага':x=60:y=40:fontsize=64:
          fontcolor=white:enable='between(t,0,5)',
  drawtext=text='Строка 47\: null pointer':x=(w-tw)/2:y=h-120:
          fontsize=42:enable='between(t,45,53)'
[vtxt];

[vtxt][1:v] overlay=x=right-20:y=20:enable='between(t,60,75)' [vimg1];
[vimg1][2:v] overlay=x=40:y=200:enable='between(t,90,115)' [vimg2];
[vimg2][3:v] overlay=x=right-160:y=bottom-160:enable='between(t,110,115)' [vfinal];

[0:a][4:a] adelay=0|0,amix=inputs=2:duration=first:dropout_transition=3 [aout]
```

Критическое требование: все специальные символы в тексте (`:`, `'`, `[`, `]`, `,`)
должны быть экранированы перед вставкой в filter_complex. Это делается в одном месте —
в функции `escape_ffmpeg_text()`.
