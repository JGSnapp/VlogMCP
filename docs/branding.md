# Система брендинга

## Принцип

Брендинг — это визуальная и медийная идентичность канала. Задаётся администратором
в конфиге один раз. AI-агент **только читает** брендинг и использует его элементы
при монтаже — изменить не может.

Это гарантирует, что все ролики выглядят согласованно, независимо от того, что
именно монтирует агент.

---

## Конфиг брендинга

Файл: `branding.json` (задаётся администратором).

```json
{
  "branding_id": "brand_default",

  "palette": {
    "primary":    "#5B8DEF",
    "accent":     "#FF5F7E",
    "background": "#121219",
    "text":       "#FFFFFF",
    "muted":      "#8899AA",
    "success":    "#4ADE80",
    "warning":    "#FBBF24",
    "error":      "#F87171"
  },

  "fonts": {
    "title":    { "family": "Inter Bold",     "size": 64, "color": "#FFFFFF" },
    "subtitle": { "family": "Inter SemiBold", "size": 42, "color": "#FFFFFF" },
    "body":     { "family": "Inter Regular",  "size": 28, "color": "#E2E8F0" },
    "code":     { "family": "JetBrains Mono", "size": 24, "color": "#A3E635" },
    "caption":  { "family": "Inter Light",    "size": 22, "color": "#8899AA" }
  },

  "watermark": {
    "asset": "branding/assets/watermark.png",
    "position": "bottom_right",
    "margin_x": 24,
    "margin_y": 24,
    "opacity": 0.6,
    "scale": 0.07
  },

  "clips": {
    "intro": "branding/clips/intro.mp4",
    "outro": "branding/clips/outro.mp4",
    "cutaways": [
      {
        "id": "br_cut_coffee",
        "path": "branding/clips/cutaways/coffee.mp4",
        "duration": 3.0,
        "tags": ["пауза", "думаю"]
      },
      {
        "id": "br_cut_typing",
        "path": "branding/clips/cutaways/typing.mp4",
        "duration": 4.0,
        "tags": ["кодинг", "пишу"]
      },
      {
        "id": "br_cut_terminal",
        "path": "branding/clips/cutaways/terminal.mp4",
        "duration": 3.5,
        "tags": ["терминал", "команды"]
      },
      {
        "id": "br_cut_deploy",
        "path": "branding/clips/cutaways/deploy.mp4",
        "duration": 5.0,
        "tags": ["деплой", "продакшн"]
      }
    ]
  },

  "plates": {
    "lower_third": {
      "asset": "branding/assets/plates/lower_third.png",
      "title_x": 140, "title_y": 32,
      "subtitle_x": 140, "subtitle_y": 68,
      "title_style": "body",
      "subtitle_style": "caption"
    },
    "section_card": {
      "asset": "branding/assets/plates/section_card.png",
      "text_x": 60, "text_y": 38,
      "text_style": "subtitle",
      "description": "Карточка-заголовок раздела. Текст вставляется поверх."
    },
    "quote_card": {
      "asset": "branding/assets/plates/quote_card.png",
      "text_x": 80, "text_y": 50,
      "text_style": "body",
      "description": "Карточка для цитаты или важного факта."
    },
    "fact_card": {
      "asset": "branding/assets/plates/fact_card.png",
      "text_x": 60, "text_y": 40,
      "text_style": "body",
      "description": "Карточка с фактом или метрикой."
    },
    "cta_card": {
      "asset": "branding/assets/plates/cta_card.png",
      "text_x": 60, "text_y": 40,
      "text_style": "subtitle",
      "description": "Call-to-action карточка в конце видео."
    }
  }
}
```

---

## Что AI может использовать из брендинга

### Шрифты и стили

При добавлении текста через `timeline_add_text` передаётся `style`:

| style | Что даёт |
|---|---|
| `branding.title` | Inter Bold 64px, белый — для крупных заголовков |
| `branding.subtitle` | Inter SemiBold 42px, белый — для подзаголовков |
| `branding.body` | Inter Regular 28px, светло-серый — для основного текста |
| `branding.code` | JetBrains Mono 24px, зелёный — для кода в тексте |
| `branding.caption` | Inter Light 22px, серый — для подписей и второстепенного текста |

---

### Плашки (plates)

Плашки — это pre-designed графические карточки в стиле канала. AI вставляет их
через `timeline_add_plate(plate="section_card", text="...")`.

| Плашка | Когда использовать |
|---|---|
| `section_card` | Анонс нового раздела видео ("Шаг 1: Воспроизводим баг") |
| `quote_card` | Цитата, важная мысль, ключевое наблюдение |
| `fact_card` | Метрика, число, факт ("Время ответа: 140мс → 12мс") |
| `cta_card` | Призыв к действию в конце ("Подписывайся") |
| `lower_third` | Имя и должность автора |

---

### Перебивки (cutaways) из брендинга

Брендинговые перебивки — короткие клипы в стиле канала, которые вставляются между
смысловыми частями для "дыхания" или смены темпа.

Добавляются через `timeline_add_cutaway(source="branding", id="br_cut_typing")`.

Доступные перебивки видны через `branding_list_cutaways()`.

---

### Watermark

Watermark добавляется **автоматически при рендере** — AI не управляет этим явно.
Рендерер читает `branding.watermark` и накладывает в финальном проходе.

---

### Intro / Outro

Intro и outro также **добавляются автоматически при рендере**. AI не вставляет их
в монтажный таймлайн вручную — рендерер клеит их вокруг смонтированного контента.

---

## Как рендерер применяет брендинг

```
render() →

1. Взять intro из branding.clips.intro
2. Рендерить монтажный таймлайн → content.mp4
3. Взять outro из branding.clips.outro
4. Склеить: [intro] + [content] + [outro]
5. Наложить watermark из branding.watermark
→ final.mp4
```

---

## Структура файлов брендинга

```
branding/
├── branding.json              ← конфиг (задаётся администратором)
├── assets/
│   ├── watermark.png          ← лого/watermark
│   └── plates/
│       ├── lower_third.png    ← плашка нижнего третьего
│       ├── section_card.png   ← карточка раздела
│       ├── quote_card.png     ← карточка цитаты
│       ├── fact_card.png      ← карточка факта
│       └── cta_card.png       ← карточка CTA
└── clips/
    ├── intro.mp4
    ├── outro.mp4
    └── cutaways/
        ├── coffee.mp4
        ├── typing.mp4
        ├── terminal.mp4
        └── deploy.mp4
```

---

## Инструменты (только чтение)

```
branding_get()
  → полный конфиг брендинга

branding_list_plates()
  → список плашек с описаниями

branding_preview_plate(plate: str)
  → PNG превью плашки

branding_list_cutaways()
  → список брендинговых перебивок с тегами
```
