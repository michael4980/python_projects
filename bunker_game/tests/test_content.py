import random

from app.content import CATEGORIES, NEED_TITLES, get_content


def test_decks_loaded():
    c = get_content()
    for cat in CATEGORIES:
        if cat == "biology":
            continue
        assert len(c.decks[cat]) >= 30, cat
    assert len(c.catastrophes) >= 10
    assert len(c.bunker_features) >= 30
    assert len(c.specials) >= 10


def test_all_tags_are_known_needs():
    c = get_content()
    for cat, deck in c.decks.items():
        for card in deck:
            for k in card["tags"]:
                assert k in NEED_TITLES, (cat, card["text"], k)
    for cat in c.catastrophes:
        for k in cat["needs"]:
            assert k in NEED_TITLES, (cat["id"], k)
    for f in c.bunker_features:
        for k in list(f.get("supply") or {}) + list(f.get("demand") or {}):
            assert k in NEED_TITLES, (f["text"], k)


def test_deal_is_unique_within_game():
    c = get_content()
    rng = random.Random(1)
    used = {}
    chars = [c.deal_character(rng, used) for _ in range(16)]
    for cat in CATEGORIES:
        if cat == "biology":
            continue
        texts = [ch[cat]["text"] for ch in chars]
        assert len(set(texts)) == len(texts), cat


def test_biology_card():
    c = get_content()
    card = c.random_biology(random.Random(3))
    assert card["category"] == "biology"
    assert card["sex"] in ("m", "f")
    assert 18 <= card["age"] <= 78
    assert "Мужчина" in card["text"] or "Женщина" in card["text"]
