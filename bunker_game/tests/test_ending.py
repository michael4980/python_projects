from app.content import make_card
from app.ending import compute_ending, ending_facts


def card(cat, text, tags=None, risk=0, risk_text=None, mitigated_by=None, outside=0, **extra):
    c = make_card(cat, {"text": text, "tags": tags or {}, "risk": risk, "risk_text": risk_text,
                        "mitigated_by": mitigated_by, "outside": outside})
    c.update(extra)
    return c


def bio(sex="m", age=30):
    return card("biology", f"{'Мужчина' if sex == 'm' else 'Женщина'}, {age}", {"reproduction": 1},
                sex=sex, age=age, fertile=True)


def person(pid, name, **cards):
    base = {"profession": card("profession", "Безработный"), "biology": bio(), "health": card("health", "Идеальное здоровье"),
            "hobby": card("hobby", "Кроссворды"), "baggage": card("baggage", "Резиновая уточка"),
            "fact": card("fact", "Храпит"), "phobia": card("phobia", "Фобий нет")}
    base.update(cards)
    return {"id": pid, "name": name, "cards": base}


CAT = {"id": "test", "title": "Тест", "text": "t", "stay_months": 12, "outside": 0.1,
       "needs": {"medicine": 3, "tech": 3, "food": 2, "morale": 2, "security": 1, "reproduction": 1}, "events": {}}
BUNKER = {"name": "Бункер «Тест»", "size_m2": 100, "stay_months": 12, "food_months": 12, "features": []}


def test_ending_depends_on_who_stays():
    doctor = person("1", "Врач", profession=card("profession", "Хирург", {"medicine": 3}),
                    baggage=card("baggage", "Пистолет", {"security": 2}))
    engineer = person("2", "Инженер", profession=card("profession", "Электрик", {"tech": 3}))
    farmer = person("3", "Фермер", profession=card("profession", "Фермер", {"food": 3}), biology=bio("f", 28),
                    hobby=card("hobby", "Гитара", {"morale": 2}))
    clown = person("4", "Клоун", profession=card("profession", "Стендап-комик", {"morale": 2}))
    diabetic = person("5", "Диабетик", health=card("health", "Диабет 1 типа", risk=3, risk_text="кончился инсулин", mitigated_by="medicine"))

    good = compute_ending(CAT, BUNKER, [doctor, engineer, farmer, diabetic], [clown], seed="s")
    bad = compute_ending(CAT, BUNKER, [clown, farmer, diabetic], [doctor, engineer], seed="s")

    assert good["group_score"] > bad["group_score"]
    assert good["verdict"]["percent"] > bad["verdict"]["percent"]
    # Диабетик выживает рядом с врачом и погибает без него.
    assert next(f for f in good["fates"] if f["id"] == "5")["status"] != "dead"
    assert next(f for f in bad["fates"] if f["id"] == "5")["status"] == "dead"
    # «А что если» указывает на изгнанного врача.
    med = next(w for w in bad["whatif"] if w["key"] == "medicine")
    assert any(h["name"] == "Врач" for h in med["helpers"])


def test_deterministic():
    a = person("1", "A", profession=card("profession", "Хирург", {"medicine": 3}))
    b = person("2", "B")
    e1 = compute_ending(CAT, BUNKER, [a, b], [], seed="x")
    e2 = compute_ending(CAT, BUNKER, [a, b], [], seed="x")
    assert e1 == e2


def test_reproduction_requires_pair():
    men = [person(str(i), f"M{i}") for i in range(3)]
    e = compute_ending(CAT, BUNKER, men, [], seed="x")
    rep = next(n for n in e["needs"] if n["key"] == "reproduction")
    assert rep["status"] == "fail"
    assert "последнее поколение" in e["verdict"]["text"]


def test_bunker_features_count():
    b = dict(BUNKER, features=[{"text": "Медблок", "supply": {"medicine": 3}}])
    p = person("1", "A")
    with_med = compute_ending(CAT, b, [p], [], seed="x")
    without = compute_ending(CAT, BUNKER, [p], [], seed="x")
    med_with = next(n for n in with_med["needs"] if n["key"] == "medicine")
    med_without = next(n for n in without["needs"] if n["key"] == "medicine")
    assert med_with["supply"] > med_without["supply"]


def test_outside_fate_uses_skills():
    ranger = person("1", "Лесник", fact=card("fact", "6 недель в лесу", outside=3),
                    hobby=card("hobby", "Походы", outside=2), baggage=card("baggage", "Палатка", outside=2))
    office = person("2", "Офис")
    e = compute_ending(CAT, BUNKER, [person("3", "X")], [ranger, office], seed="x")
    fates = {o["id"]: o["survived"] for o in e["outside"]}
    assert fates["1"] and not fates["2"]


def test_facts_text():
    p = person("1", "A")
    e = compute_ending(CAT, BUNKER, [p], [], seed="x")
    txt = ending_facts(CAT, BUNKER, [p], [], e)
    assert "Катастрофа: Тест" in txt and "A:" in txt and "Итог:" in txt
