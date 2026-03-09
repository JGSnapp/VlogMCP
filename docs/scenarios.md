# Готовые сценарии

## Что такое сценарий

Сценарий — это один MCP-инструмент, который принимает параметры и автоматически:
1. Анализирует входные данные
2. Генерирует нужные активы (TTS, code_diff, diagrams)
3. Строит черновой монтажный таймлайн
4. Применяет брендинговые элементы

Результат — готовый черновик, который AI может дополнить и скорректировать перед рендером.

**Сценарий не заменяет монтаж — он создаёт стартовую точку.**

---

## `scenario_devlog`

Дневник разработчика: запись рабочей сессии с разбивкой по разделам.

```python
scenario_devlog(
    project_id: str,
    raw_clip_id: str,           # asset_id сырой записи
    sections: list[dict],       # список разделов (см. ниже)
    author_name: str,           # для lower_third
    author_title: str = "",
    voice: str = "nova",        # голос для TTS
    music: str = "lofi_chill"   # lib_id фоновой музыки
) → timeline_id: str
```

**Формат sections:**
```json
[
  {
    "label": "Открываем задачу",
    "source_in": 0,
    "source_out": 180,
    "note": "Краткое описание для TTS"
  },
  {
    "label": "Реализация",
    "source_in": 180,
    "source_out": 900,
    "note": "Пишем код авторизации"
  },
  {
    "label": "Тестирование",
    "source_in": 900,
    "source_out": 1200,
    "note": "Прогоняем тесты, всё зелёное"
  }
]
```

**Что делает сценарий:**
1. Для каждого раздела — вставляет вырезку из raw_clip как фон
2. Добавляет `plate "section_card"` с лейблом в начале каждого раздела
3. Генерирует TTS из `note` каждого раздела
4. Добавляет `lower_third` автора (весь таймлайн)
5. Добавляет фоновую музыку
6. Добавляет перебивки `branding.cutaways` между разделами (если > 1 раздела)

**Результирующая структура таймлайна:**

```
0:00─0:03  plate "Открываем задачу"  (section_card)
0:00─3:00  clip raw (src 0:00─3:00)  (фон — запись)
0:00─0:12  tts "Открываем задачу..."  (duck_main)
─────────────────────────────────────
3:00─3:04  cutaway (branding)         (перебивка)
─────────────────────────────────────
3:04─3:07  plate "Реализация"
3:04─15:04 clip raw (src 3:00─15:00)
3:04─3:08  tts "Пишем код..."
...
```

---

## `scenario_bugfix_report`

Отчёт об исправлении бага: что сломалось, где, как починили, результат.

```python
scenario_bugfix_report(
    project_id: str,
    raw_clip_id: str,
    bug_description: str,       # текстовое описание бага
    diff_files: list[dict],     # файлы до/после для code_diff
    test_output: str = "",      # вывод тестов после исправления
    author_name: str = "",
    voice: str = "nova"
) → timeline_id: str
```

**Формат diff_files:**
```json
[
  {
    "before": "src/auth.py.bak",
    "after": "src/auth.py",
    "lang": "python",
    "title": "auth.py"
  }
]
```

**Структура видео (5 разделов):**

| Раздел | Продолжительность | Содержание |
|---|---|---|
| Симптомы | ~30с | Описание бага + фрагмент записи с воспроизведением |
| Диагностика | ~60с | Запись с анализом + `code_snapshot` проблемного места |
| Исправление | ~60с | `code_diff` для каждого файла + запись с правкой |
| Проверка | ~30с | `terminal_capture` с выводом тестов |
| Итог | ~20с | `plate "fact_card"` с цифрами: было/стало |

**Автоматически генерирует:**
- `code_diff` для каждого файла из `diff_files`
- `terminal_capture` из `test_output` (если передан)
- TTS-озвучку для каждого раздела
- `plate "section_card"` для каждого раздела
- SFX: `error_boop` на раздел "Симптомы", `success_bell` на "Итог"
- Мем `this_is_fine` на раздел "Симптомы" (в углу, 4 секунды)
- Стикер `checkmark` на раздел "Итог"

---

## `scenario_feature_demo`

Демо новой фичи: что сделали, как работает, технические детали.

```python
scenario_feature_demo(
    project_id: str,
    raw_clip_id: str,
    feature_name: str,
    key_moments: list[dict],    # ключевые моменты записи
    author_name: str = "",
    voice: str = "nova"
) → timeline_id: str
```

**Формат key_moments:**
```json
[
  {
    "label": "Создаём эндпоинт",
    "source_in": 300,
    "source_out": 600,
    "highlight": true           # если true — добавит plate
  },
  {
    "label": "Тест в Postman",
    "source_in": 1200,
    "source_out": 1500,
    "screenshot_asset": "ast_screen_1"  # скриншот показать рядом
  }
]
```

**Структура видео:**

| Раздел | Содержание |
|---|---|
| Intro | Название фичи большим текстом (plate "section_card") + TTS |
| [Для каждого key_moment] | Вырезка записи + заголовок + screenshot (если есть) |
| Заключение | plate "cta_card" + TTS |

---

## `scenario_code_review`

Разбор кода без записи экрана — только code_snapshot + TTS.
Подходит для ситуаций "хочу объяснить этот код на видео".

```python
scenario_code_review(
    project_id: str,
    files: list[dict],          # файлы для разбора
    review_notes: list[str],    # комментарии к каждому файлу
    author_name: str = "",
    voice: str = "nova",
    bg_color: str = "#121219"   # фоновый цвет
) → timeline_id: str
```

**Формат files:**
```json
[
  {
    "path": "src/auth.py",
    "start_line": 40,
    "end_line": 80,
    "highlight_lines": [47, 48, 49],
    "lang": "python"
  }
]
```

**Полностью headless** — без сырой записи. Таймлайн строится из:
- Фон: `color bg_color` для каждого файла
- Объект: `code_block` (code_snapshot файла) по центру
- Аудио: TTS из review_notes[i]
- Переход: `fade` между файлами
- Брендинг: lower_third + watermark (авто при рендере)

---

## `scenario_release_notes`

Видео-релизноутс: новые фичи, изменения, планы.
Полностью headless — только текст, плашки и диаграммы.

```python
scenario_release_notes(
    project_id: str,
    version: str,               # "v2.3.0"
    sections: list[dict],       # разделы релизноутс
    author_name: str = "",
    voice: str = "nova",
    music: str = "epic_build"
) → timeline_id: str
```

**Формат sections:**
```json
[
  {
    "title": "Что нового",
    "items": ["Поддержка OAuth 2.0", "Новый дашборд", "WebSocket API"],
    "kind": "features"
  },
  {
    "title": "Breaking Changes",
    "items": ["Удалён /api/v1/auth", "Изменён формат токенов"],
    "kind": "breaking"
  },
  {
    "title": "Метрики",
    "chart": {
      "type": "bar_chart",
      "labels": ["Запросы/с", "Время ответа"],
      "values": [1200, 48]
    },
    "kind": "metrics"
  }
]
```

**Структура таймлайна:**

Для каждого section:
- Фон: `color` (для features — темно-синий, для breaking — темно-красный, для metrics — тёмный)
- Объект: `plate "section_card"` с `title`
- Объект: `text` для каждого item (выровненные по вертикали)
- Объект: `diagram` если есть chart
- Аудио: TTS из items
- Переход: `wipeleft` между разделами

Первый кадр: большой текст с версией (plate "fact_card") + SFX `tada`.

---

## `scenario_git_recap`

Визуализация работы по репозиторию за период: коммиты, диффы, статистика.

```python
scenario_git_recap(
    project_id: str,
    repo_path: str,
    since: str,                 # "2025-01-01" или "1 week ago"
    until: str = "now",
    author: str = "",           # фильтр по автору
    author_name: str = "",
    voice: str = "nova"
) → timeline_id: str
```

**Автоматически генерирует:**
- `git_log_render` — визуализация истории коммитов
- `diagram_create(type="bar_chart")` — коммиты по дням
- `code_diff` для значимых изменений (большие диффы)

**Структура видео:**

| Раздел | Содержание |
|---|---|
| Введение | Период и количество коммитов (plate "fact_card") |
| Активность | bar_chart коммитов по дням |
| История | git_log PNG |
| Ключевые изменения | code_diff для топ-изменений |

---

## Общие принципы работы сценариев

### Сценарий возвращает черновик

После вызова `scenario_*` AI должен:
1. Вызвать `timeline_inspect()` — посмотреть что получилось
2. Вызвать `preview_frame()` на нескольких ключевых секундах
3. Добавить/убрать/переместить элементы по необходимости
4. Только потом вызывать `render()`

### Сценарии не блокируют

Все операции внутри сценария — синхронные последовательные вызовы тех же
инструментов, которые AI мог бы вызвать руками. Сценарий — это удобная
обёртка, а не магия.

### Расширение сценариев

После сценария AI может добавить любые элементы:

```python
# Запустили сценарий
scenario_bugfix_report(project_id, ...)

# Досыпали своё
timeline_add_meme(timeline_id, lib_id="galaxy_brain",
    x="right-160", y="bottom-160", start=90.0, duration=4.0)

timeline_add_sfx(timeline_id, lib_id="drum_hit", start=30.0)

preview_frame(project_id, at=92.0)  → проверяем
```
