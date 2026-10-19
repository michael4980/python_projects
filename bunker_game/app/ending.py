"""Движок динамической концовки.

Итог — детерминированная функция от катастрофы, бункера, оставшихся и изгнанных:
одинаковые решения всегда дают одинаковую концовку, и видно, кто из изгнанных мог бы
закрыть незакрытую потребность.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .content import CATEGORY_TITLES, NEED_TITLES, months_text

# Коэффициенты убывающей отдачи: второй врач полезен меньше первого.
_DIMINISH = [1.0, 0.75, 0.5]

# Общие тексты событий по потребностям (катастрофа может переопределить через events).
_GENERIC_EVENTS: dict[str, dict[str, str]] = {
    "medicine": {
        "ok": "Медицина была на высоте: раны зашивали, лекарства выдавали по графику, никто не умер от пустяка.",
        "partial": "Врача не хватало. Лечили по энциклопедии и наугад, и пару раз это едва не кончилось плохо.",
        "fail": "В бункере не оказалось никого, кто разбирался бы в медицине. Первая же инфекция прошла по всем койкам.",
    },
    "tech": {
        "ok": "Генератор, фильтры и насосы работали всё время: было кому чинить и кому понимать схемы.",
        "partial": "Технику чинили на коленке. Свет гас на недели, но каждый раз удавалось вернуть.",
        "fail": "Когда отказала вентиляция, выяснилось, что чинить её некому. Дальше ломалось всё по цепочке.",
    },
    "food": {
        "ok": "Еды хватало: запасы растянули, огород давал урожай, никто не голодал.",
        "partial": "Пайки урезали вдвое. Худели и ссорились из-за последней банки, но дотянули.",
        "fail": "Запасы кончились раньше срока, а выращивать еду никто не умел. Начался голод.",
    },
    "morale": {
        "ok": "В бункере было кому пошутить, кого послушать и с кем поговорить. Люди остались людьми.",
        "partial": "Под землёй стало тесно и тоскливо. Было несколько тяжёлых ссор, но до крови не дошло.",
        "fail": "Замкнутое пространство и нервы сделали своё: группа раскололась, и худшее случилось изнутри.",
    },
    "security": {
        "ok": "Когда к гермодвери пришли чужие, их встретили подготовленные люди. Больше не приходили.",
        "partial": "Мародёров отогнали, но едва. Дверь после этого заклинило навсегда.",
        "fail": "Никто не умел защищаться. Однажды ночью дверь открыли снаружи.",
    },
    "reproduction": {
        "ok": "В бункере родился ребёнок: у этих людей оказалось будущее.",
        "partial": "Продолжить род было почти некому, но надежда осталась.",
        "fail": "В бункере некому продолжить род: эти люди стали последним поколением.",
    },
}
_GENERIC_FALLBACK = {
    "ok": "{title}: с этим справились.",
    "partial": "{title}: справились с трудом.",
    "fail": "{title}: с этим никто не справился, и это стоило дорого.",
}


def _h(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _contribution(cards: dict[str, dict], need: str) -> list[tuple[str, int]]:
    """Вклад карт одного игрока в потребность: [(описание, значение)]."""
    out = []
    for cat, card in cards.items():
        v = card.get("tags", {}).get(need, 0)
        if v:
            out.append((f"{CATEGORY_TITLES[cat]}: {card['text']}", v))
    return out


def _player_total(cards: dict[str, dict], need: str) -> int:
    return sum(v for _, v in _contribution(cards, need))


def _status(ratio: float) -> str:
    return "ok" if ratio >= 1 else "partial" if ratio >= 0.5 else "fail"


def compute_ending(
    catastrophe: dict,
    bunker: dict,
    survivors: list[dict],
    exiled: list[dict],
    seed: str = "",
) -> dict:
    """survivors / exiled: [{"id", "name", "cards": {category: card}}]."""
    n = len(survivors)
    stay = int(catastrophe.get("stay_months", 24))

    # 1. Требования: катастрофа + бункер + размер группы.
    demand: dict[str, int] = {k: int(v) for k, v in catastrophe["needs"].items()}
    for f in bunker.get("features", []):
        for k, v in (f.get("demand") or {}).items():
            demand[k] = demand.get(k, 0) + int(v)
    demand["food"] = demand.get("food", 0) + max(0, (n - 1) // 3)
    demand["medicine"] = demand.get("medicine", 0) + n // 5
    if stay >= 36:
        demand["morale"] = demand.get("morale", 0) + 1
    if bunker.get("food_months", stay) < stay:
        demand["food"] += 1
    demand = {k: v for k, v in demand.items() if v > 0}

    # 2. Покрытие: карты выживших (с убывающей отдачей) + особенности бункера.
    needs_out = []
    status: dict[str, str] = {}
    weighted_sum, weight_total = 0.0, 0.0
    for need, req in demand.items():
        per_player = []
        for p in survivors:
            total = _player_total(p["cards"], need)
            if total:
                per_player.append((p["name"], total, _contribution(p["cards"], need)))
        positives = sorted([x for x in per_player if x[1] > 0], key=lambda x: -x[1])
        negatives = [x for x in per_player if x[1] < 0]
        supply = 0.0
        for i, (_, total, _) in enumerate(positives):
            supply += total * (_DIMINISH[i] if i < len(_DIMINISH) else _DIMINISH[-1])
        supply += sum(t for _, t, _ in negatives)
        bunker_supply = 0
        for f in bunker.get("features", []):
            bunker_supply += int((f.get("supply") or {}).get(need, 0))
        supply += bunker_supply
        note = None
        if need == "reproduction":
            men = [p for p in survivors if p["cards"].get("biology", {}).get("sex") == "m" and p["cards"]["biology"].get("fertile")]
            women = [p for p in survivors if p["cards"].get("biology", {}).get("sex") == "f" and p["cards"]["biology"].get("fertile")]
            if not men or not women:
                supply = min(supply, req * 0.3)
                note = "В бункере нет пары, способной иметь детей."
        supply = max(0.0, supply)
        ratio = supply / req if req else 1.0
        st = _status(ratio)
        status[need] = st
        weighted_sum += req * min(ratio, 1.0)
        weight_total += req
        needs_out.append({
            "key": need,
            "title": NEED_TITLES.get(need, need),
            "demand": req,
            "supply": round(supply, 1),
            "ratio": round(min(ratio, 1.5), 2),
            "status": st,
            "note": note,
            "contributors": [
                {"name": name, "total": total, "cards": [{"text": t, "value": v} for t, v in contrib]}
                for name, total, contrib in per_player
            ],
            "bunker_supply": bunker_supply,
        })
    group_score = weighted_sum / weight_total if weight_total else 1.0

    # 3. Хроника событий по потребностям.
    timeline: list[dict] = []
    cat_events = catastrophe.get("events") or {}
    for i, item in enumerate(sorted(needs_out, key=lambda x: {"fail": 0, "partial": 1, "ok": 2}[x["status"]])):
        need, st = item["key"], item["status"]
        text = (cat_events.get(need) or {}).get(st) or _GENERIC_EVENTS.get(need, {}).get(st) \
            or _GENERIC_FALLBACK[st].format(title=item["title"])
        if item["note"] and st != "ok":
            text = f"{text} {item['note']}"
        base = {"fail": 2, "partial": max(4, stay // 3), "ok": max(6, stay // 2)}[st]
        month = min(stay, base + (_h(seed, need) % 3) + i)
        timeline.append({"month": month, "kind": st, "need": need, "text": text})

    # 4. Личные судьбы.
    extra_all = 0
    victims: dict[str, tuple[int, str]] = {}
    if status.get("food") == "fail":
        extra_all += 1
    if status.get("tech") == "fail":
        extra_all += 1
    for need in ("radiation", "infection", "air", "water", "heat", "hacking"):
        if status.get(need) == "fail":
            extra_all += 1
    if n:
        if status.get("security") == "fail":
            weakest = min(survivors, key=lambda p: (_player_total(p["cards"], "security"), -_personal_risk(p)[0]))
            victims[weakest["id"]] = (2, "погиб, когда чужие ворвались в бункер")
        if status.get("morale") == "fail":
            weakest = min(survivors, key=lambda p: (_player_total(p["cards"], "morale"), -_personal_risk(p)[0]))
            prev = victims.get(weakest["id"], (0, ""))
            victims[weakest["id"]] = (prev[0] + 2, prev[1] or "не пережил раскола в группе")

    fates = []
    dead = 0
    for p in survivors:
        base, reason, mitigated_by = _personal_risk(p)
        eff = base
        if mitigated_by:
            eff -= {"ok": 2, "partial": 1, "fail": 0}.get(status.get(mitigated_by, "ok"), 0)
        eff = max(0, eff) + extra_all
        v_extra, v_reason = victims.get(p["id"], (0, ""))
        if eff < 3 and eff + v_extra >= 3:
            reason = v_reason
        elif eff < 3 and not reason and extra_all:
            reason = "не пережил того, что случилось с бункером"
        eff += v_extra
        if eff >= 3:
            dead += 1
            month = 1 + (_h(seed, p["id"]) % max(1, stay - 1))
            text = f"Погиб на {month}-м месяце: {reason or 'не пережил то, что случилось с бункером'}."
            fates.append({"id": p["id"], "name": p["name"], "status": "dead", "month": month, "text": text})
            timeline.append({"month": month, "kind": "death", "need": None, "text": f"{p['name']} — {text[0].lower() + text[1:]}"})
        elif eff == 2:
            fates.append({"id": p["id"], "name": p["name"], "status": "trouble", "month": None,
                          "text": f"Выжил, но едва: {reason or 'тяжело перенёс жизнь под землёй'}."})
        else:
            fates.append({"id": p["id"], "name": p["name"], "status": "alive", "month": None,
                          "text": "Дожил до открытия двери в добром здравии."})
    timeline.sort(key=lambda e: (e["month"], 0 if e["kind"] == "death" else 1))

    # 5. Изгнанные.
    outside_base = float(catastrophe.get("outside", 0.1))
    outside = []
    for p in exiled:
        bonus = sum(int(c.get("outside", 0)) for c in p["cards"].values())
        risk, reason, _ = _personal_risk(p)
        score = outside_base + 0.12 * bonus - 0.1 * risk
        survived = score >= 0.5
        skills = [c["text"] for c in p["cards"].values() if int(c.get("outside", 0)) > 0]
        if survived:
            text = "Выжил снаружи" + (f": помогло — {', '.join(skills[:3])}." if skills else ".")
        else:
            text = "Снаружи не выжил" + (f": {reason}." if reason and risk >= 2 else ".")
        outside.append({"id": p["id"], "name": p["name"], "survived": survived, "score": round(score, 2), "text": text})

    # 6. «А что если»: кто из изгнанных закрыл бы дыру.
    whatif = []
    for item in needs_out:
        if item["status"] == "ok":
            continue
        helpers = []
        for p in exiled:
            total = _player_total(p["cards"], item["key"])
            if total >= 1:
                helpers.append({"name": p["name"], "total": total,
                                "cards": [{"text": t, "value": v} for t, v in _contribution(p["cards"], item["key"]) if v > 0]})
        helpers.sort(key=lambda h: -h["total"])
        whatif.append({"key": item["key"], "title": item["title"], "status": item["status"], "helpers": helpers})

    # 7. Вердикт.
    alive = n - dead
    percent = int(round(100 * (0.55 * group_score + 0.45 * (alive / n if n else 0))))
    if n == 0:
        title, text = "Бункер пуст", "В бункер никто не вошёл."
    elif alive == 0:
        title, text = "Бункер погиб", "Дверь так и не открылась изнутри."
    elif dead == 0 and group_score >= 0.8:
        title, text = "Все выжили", f"Через {months_text(stay)} дверь открылась, и наружу вышли все {n}."
    elif dead == 0:
        title, text = "Все выжили, но дорогой ценой", f"Через {months_text(stay)} наружу вышли все {n}, измотанные и злые."
    elif alive >= max(1, n // 2):
        title, text = f"Выжили {alive} из {n}", f"Через {months_text(stay)} дверь открыли {alive} человек. Остальных похоронили в дальнем отсеке."
    else:
        title, text = f"Выжили только {alive} из {n}", "Бункер не стал спасением. Наружу вышли единицы."
    if status.get("reproduction") == "fail" and alive > 0:
        text += " Детей у них не будет: это последнее поколение."

    return {
        "verdict": {"title": title, "text": text, "percent": max(0, min(100, percent)), "alive": alive, "dead": dead, "total": n},
        "group_score": round(group_score, 2),
        "needs": needs_out,
        "timeline": timeline,
        "fates": fates,
        "outside": outside,
        "whatif": whatif,
        "stay_months": stay,
    }


def _personal_risk(p: dict) -> tuple[int, str | None, str | None]:
    """Максимальный личный риск по картам: (риск, причина, потребность, которая его снижает)."""
    best = (0, None, None)
    for card in p["cards"].values():
        r = int(card.get("risk", 0) or 0)
        if r > best[0]:
            best = (r, card.get("risk_text"), card.get("mitigated_by"))
    return best


def ending_facts(catastrophe: dict, bunker: dict, survivors: list[dict], exiled: list[dict], ending: dict) -> str:
    """Факты для рассказчика (LLM): он украшает, но не меняет."""
    lines = [f"Катастрофа: {catastrophe['title']}. {catastrophe['text']}",
             f"Бункер: {bunker['name']}, {bunker['size_m2']} м², сидеть {months_text(bunker['stay_months'])}, еды на {months_text(bunker['food_months'])}.",
             "Особенности бункера: " + "; ".join(f["text"] for f in bunker.get("features", [])) + ".",
             "", "В бункере:"]
    for p in survivors:
        lines.append(f"- {p['name']}: " + "; ".join(f"{CATEGORY_TITLES[c]} — {card['text']}" for c, card in p["cards"].items()))
    lines.append("")
    lines.append("Остались снаружи:")
    for p in exiled:
        lines.append(f"- {p['name']}: " + "; ".join(f"{CATEGORY_TITLES[c]} — {card['text']}" for c, card in p["cards"].items()))
    lines.append("")
    lines.append("Расчёт движка (это факты, им нельзя противоречить):")
    for nd in ending["needs"]:
        lines.append(f"- {nd['title']}: {nd['status']} (покрытие {nd['supply']} из {nd['demand']})")
    lines.append("Хроника:")
    for e in ending["timeline"]:
        lines.append(f"- Месяц {e['month']}: {e['text']}")
    lines.append("Судьбы в бункере:")
    for f in ending["fates"]:
        lines.append(f"- {f['name']}: {f['text']}")
    lines.append("Судьбы снаружи:")
    for o in ending["outside"]:
        lines.append(f"- {o['name']}: {o['text']}")
    lines.append(f"Итог: {ending['verdict']['title']}. {ending['verdict']['text']}")
    return "\n".join(lines)
