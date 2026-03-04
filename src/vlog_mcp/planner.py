from __future__ import annotations

from typing import Any


TEMPLATES: dict[str, dict[str, Any]] = {
    "system-build-report": {
        "sections": [
            "Постановка задачи",
            "Архитектурные решения",
            "Ключевые этапы реализации",
            "Результат и метрики",
            "Следующие шаги",
        ]
    },
    "bugfix-report": {
        "sections": [
            "Симптомы и влияние",
            "Анализ причины",
            "Исправление и дифф",
            "Проверка",
            "Выводы",
        ]
    },
    "release-update": {
        "sections": ["Что нового", "Демо", "Breaking changes", "План развития"]
    },
    "devlog": {
        "sections": ["Контекст", "Что было сделано", "Проблемы", "Инсайты", "Финал"]
    },
}


def build_video_plan(
    template: str,
    objective: str,
    audience: str,
    platform: str,
    include_vertical_variant: bool = False,
) -> dict[str, Any]:
    base = TEMPLATES.get(template, TEMPLATES["devlog"])
    section_items = [
        {
            "title": title,
            "target_duration_sec": 35,
            "assets": [],
            "voiceover_hint": f"Объяснить раздел '{title}' для аудитории: {audience}.",
        }
        for title in base["sections"]
    ]
    return {
        "template": template,
        "objective": objective,
        "audience": audience,
        "platform": platform,
        "formats": ["16:9"] + (["9:16"] if include_vertical_variant else []),
        "sections": section_items,
        "cta": "Подписывайтесь и задавайте вопросы в комментариях.",
    }
