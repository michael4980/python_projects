"""Художественная хроника через OpenAI поверх фактов движка."""
from __future__ import annotations

import logging

import httpx

from . import config

log = logging.getLogger("bunker.narrator")

SYSTEM_PROMPT = (
    "Ты — рассказчик в настольной игре «Бункер». Тебе дают факты о катастрофе, бункере, людях внутри и снаружи "
    "и расчёт исхода. Напиши по-русски художественную хронику выживания на 250–400 слов: что происходило в бункере "
    "месяц за месяцем, кто чем помог, кто погиб и почему, что стало с теми, кто остался снаружи, и чем всё кончилось. "
    "Строго следуй фактам: не воскрешай погибших, не убивай выживших, не меняй итог. Упоминай игроков по именам и "
    "обыгрывай их карты (профессии, фобии, багаж). Тон — мрачноватый, с чёрным юмором. Без заголовков и списков, "
    "только абзацы текста."
)


async def generate_narrative(facts: str) -> str | None:
    if not config.OPENAI_API_KEY:
        return None
    payload = {
        "model": config.OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": facts},
        ],
        "temperature": 0.9,
        "max_tokens": 1200,
    }
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(f"{config.OPENAI_BASE_URL}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        log.warning("narrative failed: %s", e)
        return None
