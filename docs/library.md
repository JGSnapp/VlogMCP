# Медиабиблиотека

## Принцип

Медиабиблиотека — коллекция готовых материалов: мемов, звуков, стикеров,
перебивок и музыки. Задаётся администратором, AI только ищет и использует.

Ссылки в таймлайне используют формат `lib_id` — просто строка, которая
находится через `library_search` или `library_list`.

---

## Структура

```
library/
├── index.json             ← каталог всех материалов
├── memes/                 ← изображения и GIF
├── sfx/                   ← звуковые эффекты (MP3, WAV)
├── stickers/              ← анимированные стикеры (GIF)
├── cutaways/              ← короткие видеоклипы (MP4)
└── music/                 ← фоновая музыка (MP3)
```

---

## index.json

Полный каталог библиотеки. AI никогда не пишет в него — только читает через
инструменты `library_list` и `library_search`.

```json
{
  "version": "1.0",
  "memes": [
    {
      "id": "thinking_guy",
      "path": "memes/thinking_guy.png",
      "kind": "image",
      "tags": ["думает", "хмм", "рассуждение", "анализ"],
      "mood": "ironic",
      "description": "Человек задумчиво смотрит в сторону"
    },
    {
      "id": "this_is_fine",
      "path": "memes/this_is_fine.gif",
      "kind": "gif",
      "duration": 3.0,
      "tags": ["баг", "пожар", "всё ок", "паника", "продакшн горит"],
      "mood": "chaos",
      "description": "Собака сидит в горящей комнате и пьёт кофе"
    },
    {
      "id": "drake_no_yes",
      "path": "memes/drake.png",
      "kind": "image",
      "tags": ["выбор", "нет-да", "сравнение", "предпочтение"],
      "mood": "comparison",
      "description": "Drake отказывается от одного и выбирает другое"
    },
    {
      "id": "todo_comment",
      "path": "memes/todo_comment.png",
      "kind": "image",
      "tags": ["техдолг", "todo", "потом", "не сейчас"],
      "mood": "relatable",
      "description": "// TODO: fix this later"
    },
    {
      "id": "works_on_my_machine",
      "path": "memes/works_on_my_machine.png",
      "kind": "image",
      "tags": ["баг", "среда", "локально работает", "деплой"],
      "mood": "relatable",
      "description": "Works on my machine"
    },
    {
      "id": "galaxy_brain",
      "path": "memes/galaxy_brain.gif",
      "kind": "gif",
      "duration": 4.0,
      "tags": ["инсайт", "решение", "умно", "eureka"],
      "mood": "triumph",
      "description": "Расширяющийся мозг — всё более грандиозные идеи"
    }
  ],

  "sfx": [
    {
      "id": "drum_hit",
      "path": "sfx/drum_hit.mp3",
      "duration": 0.3,
      "tags": ["удар", "акцент", "переход", "бам"],
      "description": "Резкий удар барабана для акцента"
    },
    {
      "id": "tada",
      "path": "sfx/tada.mp3",
      "duration": 1.2,
      "tags": ["успех", "готово", "финал", "ура"],
      "description": "Победный сигнал"
    },
    {
      "id": "error_boop",
      "path": "sfx/error_boop.mp3",
      "duration": 0.4,
      "tags": ["ошибка", "баг", "неудача", "fail"],
      "description": "Звук ошибки"
    },
    {
      "id": "success_bell",
      "path": "sfx/success_bell.mp3",
      "duration": 0.8,
      "tags": ["успех", "готово", "работает", "тест прошёл"],
      "description": "Мягкий звон успеха"
    },
    {
      "id": "keyboard_click",
      "path": "sfx/keyboard_click.mp3",
      "duration": 0.1,
      "tags": ["кодинг", "ввод", "набираю"],
      "description": "Клик клавиши"
    },
    {
      "id": "whoosh",
      "path": "sfx/whoosh.mp3",
      "duration": 0.5,
      "tags": ["переход", "быстро", "смена"],
      "description": "Звук быстрого движения"
    },
    {
      "id": "level_up",
      "path": "sfx/level_up.mp3",
      "duration": 1.5,
      "tags": ["достижение", "прокачка", "выполнено"],
      "description": "Звук повышения уровня как в игре"
    }
  ],

  "stickers": [
    {
      "id": "fire",
      "path": "stickers/fire.gif",
      "duration": 2.0,
      "tags": ["горит", "огонь", "жара", "hot"],
      "description": "Анимированное пламя"
    },
    {
      "id": "checkmark",
      "path": "stickers/checkmark.gif",
      "duration": 1.5,
      "tags": ["готово", "ок", "выполнено", "галочка"],
      "description": "Зелёная галочка с анимацией"
    },
    {
      "id": "explosion",
      "path": "stickers/explosion.gif",
      "duration": 1.8,
      "tags": ["взрыв", "бах", "сломалось", "краш"],
      "description": "Анимированный взрыв"
    },
    {
      "id": "loading_spinner",
      "path": "stickers/loading.gif",
      "duration": 2.0,
      "tags": ["загрузка", "ждём", "процесс", "долго"],
      "description": "Крутящийся спиннер загрузки"
    },
    {
      "id": "nerd_face",
      "path": "stickers/nerd.gif",
      "duration": 2.0,
      "tags": ["умно", "разбираюсь", "знаю", "нёрд"],
      "description": "Лицо умника в очках"
    },
    {
      "id": "party_popper",
      "path": "stickers/party.gif",
      "duration": 2.5,
      "tags": ["праздник", "запуск", "релиз", "ура"],
      "description": "Хлопушка и конфетти"
    }
  ],

  "cutaways": [
    {
      "id": "coffee_cup",
      "path": "cutaways/coffee_cup.mp4",
      "duration": 3.0,
      "tags": ["пауза", "думаю", "перерыв", "размышление"],
      "description": "Крупный план кружки кофе"
    },
    {
      "id": "typing_fast",
      "path": "cutaways/typing_fast.mp4",
      "duration": 4.0,
      "tags": ["кодинг", "пишу", "быстро", "продуктивность"],
      "description": "Руки быстро печатают на клавиатуре"
    },
    {
      "id": "loading_bar",
      "path": "cutaways/loading_bar.mp4",
      "duration": 3.5,
      "tags": ["загрузка", "ждём", "процесс", "долго"],
      "description": "Прогресс-бар заполняется"
    },
    {
      "id": "git_graph",
      "path": "cutaways/git_graph.mp4",
      "duration": 4.0,
      "tags": ["git", "ветки", "коммиты", "версии"],
      "description": "Анимированный граф git-веток"
    },
    {
      "id": "matrix_code",
      "path": "cutaways/matrix_code.mp4",
      "duration": 5.0,
      "tags": ["код", "матрица", "хакер", "программирование"],
      "description": "Зелёный падающий код как в Матрице"
    },
    {
      "id": "deploy_rocket",
      "path": "cutaways/deploy_rocket.mp4",
      "duration": 3.0,
      "tags": ["деплой", "запуск", "продакшн", "релиз"],
      "description": "Анимированная ракета улетает"
    }
  ],

  "music": [
    {
      "id": "lofi_chill",
      "path": "music/lofi_chill.mp3",
      "duration": 180,
      "bpm": 85,
      "mood": "focus",
      "tags": ["фон", "спокойно", "кодинг", "размышление"],
      "description": "Лоу-фай хип-хоп для фоновой музыки"
    },
    {
      "id": "epic_build",
      "path": "music/epic_build.mp3",
      "duration": 120,
      "bpm": 140,
      "mood": "triumph",
      "tags": ["финал", "успех", "достижение", "победа"],
      "description": "Нарастающая эпическая музыка"
    },
    {
      "id": "upbeat_coding",
      "path": "music/upbeat_coding.mp3",
      "duration": 200,
      "bpm": 120,
      "mood": "energetic",
      "tags": ["энергия", "кодинг", "продуктивность", "быстро"],
      "description": "Бодрый электронный бит"
    },
    {
      "id": "suspense",
      "path": "music/suspense.mp3",
      "duration": 90,
      "bpm": 100,
      "mood": "tense",
      "tags": ["баг", "расследование", "что-то пошло не так", "напряжение"],
      "description": "Напряжённая музыка для момента анализа бага"
    },
    {
      "id": "chill_beats",
      "path": "music/chill_beats.mp3",
      "duration": 240,
      "bpm": 75,
      "mood": "relaxed",
      "tags": ["объяснение", "туториал", "спокойно", "введение"],
      "description": "Расслабленные биты для образовательного контента"
    }
  ]
}
```

---

## Инструменты работы с библиотекой

### `library_list(kind?, tags?)`

Возвращает список всех элементов категории.

```
library_list(kind="meme") → все мемы
library_list(kind="sfx", tags=["успех"]) → SFX с тегом "успех"
library_list() → всё
```

### `library_search(query, kind?)`

Поиск по тексту. Ищет по полям `tags`, `id`, `description`.

```
library_search("баг пожар") → [this_is_fine, error_boop, ...]
library_search("деплой", kind="cutaway") → [deploy_rocket, ...]
library_search("победа успех") → [tada, success_bell, party_popper, epic_build, ...]
```

### `library_preview(lib_id)`

Для изображений и GIF — возвращает base64 PNG первого кадра.
Для аудио — метаданные (duration, bpm, mood).

---

## Как использовать в таймлайне

```python
# Мем в углу
timeline_add_meme(timeline_id,
    lib_id="this_is_fine",
    x="right-160", y="bottom-160",
    width=140, z=2,
    start=45.0, duration=4.0)

# Стикер по центру
timeline_add_sticker(timeline_id,
    lib_id="party_popper",
    x="center", y="center",
    scale=1.5, z=3,
    start=88.0, duration=2.5)

# Перебивка как фон
timeline_add_cutaway(timeline_id,
    source="library",
    id="typing_fast",
    start=60.0, duration=4.0)

# Звуковой эффект
timeline_add_sfx(timeline_id,
    lib_id="drum_hit",
    start=90.0, volume=0.7)

# Фоновая музыка
timeline_add_music(timeline_id,
    lib_id="lofi_chill",
    start=0.0, volume=0.15, loop=True)
```

---

## Сценарии подбора материалов

AI должен сам принимать решение о подходящих материалах на основе контекста.
Примерная логика:

| Контекст | Рекомендуемые материалы |
|---|---|
| Нашли баг | мем `this_is_fine`, SFX `error_boop`, музыка `suspense` |
| Исправили баг | стикер `checkmark`, SFX `success_bell`, музыка `upbeat_coding` |
| Деплой | перебивка `deploy_rocket`, стикер `party_popper`, SFX `tada` |
| Объясняем архитектуру | музыка `chill_beats`, без мемов |
| Технический долг | мем `todo_comment`, SFX `error_boop` |
| Умное решение | мем `galaxy_brain`, SFX `level_up` |
| Долгое ожидание | перебивка `loading_bar`, стикер `loading_spinner` |
