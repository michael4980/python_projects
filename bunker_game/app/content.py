"""Загрузка колод из YAML и раздача карт."""
from __future__ import annotations

import copy
import random
from pathlib import Path
from typing import Any

import yaml

CONTENT_DIR = Path(__file__).parent / "content"

# Порядок категорий = порядок показа на экране.
CATEGORIES = ["profession", "biology", "health", "hobby", "baggage", "fact", "phobia"]
CATEGORY_TITLES = {
    "profession": "Профессия",
    "biology": "Биология",
    "health": "Здоровье",
    "hobby": "Хобби",
    "baggage": "Багаж",
    "fact": "Факт",
    "phobia": "Фобия",
}
# Ключ в cards.yaml для каждой категории (биология генерируется).
_DECK_KEYS = {
    "profession": "professions",
    "health": "health",
    "hobby": "hobbies",
    "baggage": "baggage",
    "fact": "facts",
    "phobia": "phobias",
}

NEED_TITLES = {
    "medicine": "Медицина",
    "tech": "Техника",
    "food": "Еда",
    "morale": "Психика",
    "security": "Безопасность",
    "reproduction": "Продолжение рода",
    "radiation": "Радиация",
    "infection": "Инфекции",
    "air": "Воздух",
    "water": "Вода",
    "heat": "Тепло",
    "hacking": "Машины и сети",
}


def _load(name: str) -> Any:
    with open(CONTENT_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_card(category: str, raw: dict) -> dict:
    """Нормализует запись из YAML в карту персонажа."""
    return {
        "category": category,
        "text": raw["text"],
        "tags": {k: int(v) for k, v in (raw.get("tags") or {}).items()},
        "risk": int(raw.get("risk", 0) or 0),
        "risk_text": raw.get("risk_text"),
        "mitigated_by": raw.get("mitigated_by"),
        "outside": int(raw.get("outside", 0) or 0),
        "revealed": False,
    }


class Content:
    def __init__(self) -> None:
        cards = _load("cards.yaml")
        self.decks: dict[str, list[dict]] = {
            cat: [make_card(cat, c) for c in cards[key]] for cat, key in _DECK_KEYS.items()
        }
        self.catastrophes: list[dict] = _load("catastrophes.yaml")
        bunkers = _load("bunkers.yaml")
        self.bunker_nicknames: list[str] = bunkers["nicknames"]
        self.bunker_features: list[dict] = bunkers["features"]
        self.specials: list[dict] = _load("specials.yaml")

    # ---- карты персонажа -------------------------------------------------
    def random_card(self, rng: random.Random, category: str, exclude: set[str] | None = None) -> dict:
        if category == "biology":
            return self.random_biology(rng)
        deck = self.decks[category]
        pool = [c for c in deck if not exclude or c["text"] not in exclude] or deck
        return copy.deepcopy(rng.choice(pool))

    def random_biology(self, rng: random.Random) -> dict:
        sex = rng.choice(["m", "f"])
        age = rng.choice([rng.randint(18, 45), rng.randint(18, 45), rng.randint(30, 60), rng.randint(46, 78)])
        orientation = rng.choices(["hetero", "hetero", "hetero", "gay", "bi", "ace"], k=1)[0]
        o_text = {
            "hetero": {"m": "гетеросексуален", "f": "гетеросексуальна"},
            "gay": {"m": "гей", "f": "лесбиянка"},
            "bi": {"m": "бисексуален", "f": "бисексуальна"},
            "ace": {"m": "асексуален", "f": "асексуальна"},
        }[orientation][sex]
        fertile = (sex == "f" and age <= 45) or (sex == "m" and age <= 62)
        tags: dict[str, int] = {}
        if fertile:
            tags["reproduction"] = 1
        risk, risk_text, outside = 0, None, 0
        if age >= 70:
            risk, risk_text, outside = 2, "возраст и тяготы жизни под землёй", -2
        elif age >= 60:
            risk, risk_text, outside = 1, "возраст", -1
        elif age <= 25:
            outside = 1
        years = "год" if age % 10 == 1 and age % 100 != 11 else ("года" if 2 <= age % 10 <= 4 and not 12 <= age % 100 <= 14 else "лет")
        text = f"{'Мужчина' if sex == 'm' else 'Женщина'}, {age} {years}, {o_text}"
        return {
            "category": "biology",
            "text": text,
            "tags": tags,
            "risk": risk,
            "risk_text": risk_text,
            "mitigated_by": "medicine" if risk else None,
            "outside": outside,
            "revealed": False,
            "sex": sex,
            "age": age,
            "fertile": fertile,
        }

    def deal_character(self, rng: random.Random, used: dict[str, set[str]] | None = None) -> dict[str, dict]:
        """Раздаёт полный набор карт, избегая повторов текста внутри партии (used)."""
        used = used if used is not None else {}
        cards: dict[str, dict] = {}
        for cat in CATEGORIES:
            card = self.random_card(rng, cat, exclude=used.setdefault(cat, set()))
            used[cat].add(card["text"])
            cards[cat] = card
        return cards

    # ---- сценарий --------------------------------------------------------
    def random_catastrophe(self, rng: random.Random) -> dict:
        return copy.deepcopy(rng.choice(self.catastrophes))

    def random_bunker(self, rng: random.Random, players: int, stay_months: int) -> dict:
        n_features = rng.randint(3, 5)
        features = [copy.deepcopy(f) for f in rng.sample(self.bunker_features, n_features)]
        size = rng.randint(40, 120) + players * rng.randint(4, 10)
        food_months = max(3, min(stay_months, rng.randint(stay_months // 2, stay_months + 6)))
        return {
            "name": f"Бункер «{rng.choice(self.bunker_nicknames)}»",
            "size_m2": size,
            "stay_months": stay_months,
            "food_months": food_months,
            "features": features,
        }

    def random_special(self, rng: random.Random) -> dict:
        card = copy.deepcopy(rng.choice(self.specials))
        card["used"] = False
        return card


_content: Content | None = None


def get_content() -> Content:
    global _content
    if _content is None:
        _content = Content()
    return _content


def months_text(m: int) -> str:
    if m < 12:
        return f"{m} {'месяц' if m == 1 else 'месяца' if 2 <= m <= 4 else 'месяцев'}"
    y, rest = divmod(m, 12)
    ys = f"{y} {'год' if y % 10 == 1 and y != 11 else 'года' if 2 <= y % 10 <= 4 and not 12 <= y <= 14 else 'лет'}"
    return ys if rest == 0 else f"{ys} {months_text(rest)}"
