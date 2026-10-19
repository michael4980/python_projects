"""Состояние комнаты и правила партии."""
from __future__ import annotations

import random
import secrets
import time
from typing import Any

from . import config
from .content import CATEGORIES, CATEGORY_TITLES, get_content
from .ending import compute_ending, ending_facts

ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class GameError(Exception):
    """Ошибка правил: текст показывается игроку."""


def new_room_code(rng: random.Random | None = None) -> str:
    r = rng or random.SystemRandom()
    return "".join(r.choice(ROOM_ALPHABET) for _ in range(5))


class Player:
    def __init__(self, name: str, is_host: bool = False) -> None:
        self.id = secrets.token_hex(4)
        self.token = secrets.token_urlsafe(16)
        self.name = name
        self.is_host = is_host
        self.cards: dict[str, dict] = {}
        self.special: dict | None = None
        self.status = "alive"  # alive | out
        self.connected = False
        self.immunity = False
        self.double_vote = False
        self.reveals_left = 0
        self.exiled_round: int | None = None

    def hidden_categories(self) -> list[str]:
        return [c for c in CATEGORIES if self.cards and not self.cards[c]["revealed"]]

    def as_player_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "cards": self.cards}


class Room:
    def __init__(self, code: str, seed: int | None = None) -> None:
        self.code = code
        self.seed = seed if seed is not None else secrets.randbits(63)
        self.rng = random.Random(self.seed)
        self.players: list[Player] = []
        self.phase = "lobby"  # lobby | reveal | vote | finished
        self.round = 0
        self.seats = 0
        self.settings = {"reveals_per_round": 1, "specials": True}
        self.catastrophe: dict | None = None
        self.bunker: dict | None = None
        self.vote: dict | None = None
        self.last_vote: dict | None = None
        self.log: list[dict] = []
        self.ending: dict | None = None
        self.narrative: str | None = None
        self.narrative_status = "idle"  # idle | pending | done | failed | disabled
        self.created_at = time.time()
        self.touched_at = time.time()
        self.content = get_content()
        self._used: dict[str, set[str]] = {}

    # ---- служебное -------------------------------------------------------
    def touch(self) -> None:
        self.touched_at = time.time()

    def _log(self, text: str, kind: str = "info") -> None:
        self.log.append({"t": int(time.time()), "round": self.round, "kind": kind, "text": text})
        self.log = self.log[-200:]

    def player_by_token(self, token: str) -> Player | None:
        return next((p for p in self.players if p.token == token), None)

    def player(self, pid: str) -> Player:
        p = next((p for p in self.players if p.id == pid), None)
        if p is None:
            raise GameError("Игрок не найден")
        return p

    def alive(self) -> list[Player]:
        return [p for p in self.players if p.status == "alive"]

    def exiled(self) -> list[Player]:
        return [p for p in self.players if p.status == "out"]

    def host(self) -> Player | None:
        return next((p for p in self.players if p.is_host), None)

    def _require_host(self, p: Player) -> None:
        if not p.is_host:
            raise GameError("Это может делать только ведущий")

    # ---- лобби -----------------------------------------------------------
    def add_player(self, name: str, is_host: bool = False) -> Player:
        name = (name or "").strip()[:24]
        if not name:
            raise GameError("Введите имя")
        if self.phase != "lobby":
            raise GameError("Игра уже началась, присоединиться нельзя")
        if len(self.players) >= config.MAX_PLAYERS:
            raise GameError("Комната заполнена")
        if any(p.name.lower() == name.lower() for p in self.players):
            raise GameError("Такое имя уже занято в этой комнате")
        p = Player(name, is_host=is_host or not self.players)
        self.players.append(p)
        self.seats = self.default_seats()
        self._log(f"{p.name} вошёл в комнату")
        self.touch()
        return p

    def default_seats(self) -> int:
        return max(1, len(self.players) // 2)

    def kick(self, actor: Player, pid: str) -> None:
        self._require_host(actor)
        if self.phase != "lobby":
            raise GameError("Выгнать можно только в лобби")
        target = self.player(pid)
        if target.is_host:
            raise GameError("Ведущего выгнать нельзя")
        self.players.remove(target)
        self.seats = self.default_seats()
        self._log(f"{target.name} удалён из комнаты")

    def update_settings(self, actor: Player, seats: int | None = None, reveals_per_round: int | None = None,
                        specials: bool | None = None) -> None:
        self._require_host(actor)
        if self.phase != "lobby":
            raise GameError("Настройки меняются только в лобби")
        if seats is not None:
            seats = int(seats)
            if not 1 <= seats < max(2, len(self.players)):
                raise GameError("Мест должно быть от 1 до числа игроков минус один")
            self.seats = seats
        if reveals_per_round is not None:
            r = int(reveals_per_round)
            if not 1 <= r <= 3:
                raise GameError("Карт за раунд: от 1 до 3")
            self.settings["reveals_per_round"] = r
        if specials is not None:
            self.settings["specials"] = bool(specials)

    # ---- старт -----------------------------------------------------------
    def start(self, actor: Player) -> None:
        self._require_host(actor)
        if self.phase != "lobby":
            raise GameError("Игра уже идёт")
        if len(self.players) < config.MIN_PLAYERS:
            raise GameError(f"Нужно хотя бы {config.MIN_PLAYERS} игрока")
        if self.seats >= len(self.players):
            self.seats = self.default_seats()
        self.catastrophe = self.content.random_catastrophe(self.rng)
        self.bunker = self.content.random_bunker(self.rng, len(self.players), self.catastrophe["stay_months"])
        for p in self.players:
            p.cards = self.content.deal_character(self.rng, self._used)
            p.cards["profession"]["revealed"] = True
            p.special = self.content.random_special(self.rng) if self.settings["specials"] else None
            p.status = "alive"
        self._log(f"Катастрофа: {self.catastrophe['title']}. {self.bunker['name']}, мест: {self.seats}", "system")
        self._begin_round(1)

    def _begin_round(self, number: int) -> None:
        self.round = number
        self.phase = "reveal"
        self.vote = None
        for p in self.alive():
            p.reveals_left = self.settings["reveals_per_round"]
        self._log(f"Раунд {number}: откройте по {self.settings['reveals_per_round']} карте и обсудите", "system")
        self.touch()

    # ---- раскрытие и спецкарты ------------------------------------------
    def reveal(self, actor: Player, category: str) -> None:
        if self.phase != "reveal":
            raise GameError("Сейчас нельзя открывать карты")
        if actor.status != "alive":
            raise GameError("Вы уже вне бункера")
        if category not in actor.cards:
            raise GameError("Нет такой карты")
        card = actor.cards[category]
        if card["revealed"]:
            raise GameError("Эта карта уже открыта")
        if actor.reveals_left <= 0:
            raise GameError("В этом раунде вы уже открыли все положенные карты")
        card["revealed"] = True
        actor.reveals_left -= 1
        self._log(f"{actor.name} открывает {CATEGORY_TITLES[category].lower()}: {card['text']}", "reveal")
        self.touch()

    def play_special(self, actor: Player, target_id: str | None = None) -> None:
        if actor.status != "alive":
            raise GameError("Вы уже вне бункера")
        if self.phase != "reveal":
            raise GameError("Особое условие можно сыграть только до голосования")
        sp = actor.special
        if not sp or sp.get("used"):
            raise GameError("У вас нет неиспользованного особого условия")
        effect = sp["effect"]
        target: Player | None = None
        if effect in ("swap", "reveal"):
            if not target_id:
                raise GameError("Выберите игрока")
            target = self.player(target_id)
            if target.id == actor.id or target.status != "alive":
                raise GameError("Нужно выбрать другого игрока, который ещё в игре")
        if effect == "swap":
            cat = sp["category"]
            actor.cards[cat], target.cards[cat] = target.cards[cat], actor.cards[cat]
            actor.cards[cat]["revealed"] = True
            target.cards[cat]["revealed"] = True
            self._log(f"{actor.name} играет «{sp['title']}»: меняется картой «{CATEGORY_TITLES[cat].lower()}» с {target.name}", "special")
        elif effect == "reroll":
            cat = sp["category"]
            new = self.content.random_card(self.rng, cat, exclude=self._used.setdefault(cat, set()))
            self._used[cat].add(new["text"])
            new["revealed"] = True
            old = actor.cards[cat]["text"]
            actor.cards[cat] = new
            self._log(f"{actor.name} играет «{sp['title']}»: {CATEGORY_TITLES[cat].lower()} «{old}» → «{new['text']}»", "special")
        elif effect == "reveal":
            hidden = target.hidden_categories()
            if not hidden:
                raise GameError("У этого игрока не осталось скрытых карт")
            cat = self.rng.choice(hidden)
            target.cards[cat]["revealed"] = True
            self._log(f"{actor.name} играет «{sp['title']}»: у {target.name} открывается {CATEGORY_TITLES[cat].lower()}: {target.cards[cat]['text']}", "special")
        elif effect == "immunity":
            actor.immunity = True
            self._log(f"{actor.name} играет «{sp['title']}»: в ближайшем голосовании его нельзя изгнать", "special")
        elif effect == "double_vote":
            actor.double_vote = True
            self._log(f"{actor.name} играет «{sp['title']}»: его голос в ближайшем голосовании считается за два", "special")
        elif effect == "extra_seat":
            self.seats += 1
            self._log(f"{actor.name} играет «{sp['title']}»: в бункере теперь {self.seats} мест", "special")
        else:
            raise GameError("Неизвестный эффект карты")
        sp["used"] = True
        self.touch()

    # ---- голосование -----------------------------------------------------
    def start_vote(self, actor: Player) -> None:
        self._require_host(actor)
        if self.phase != "reveal":
            raise GameError("Голосование можно начать только в фазе обсуждения")
        candidates = [p.id for p in self.alive() if not p.immunity]
        if len(candidates) < 2:
            raise GameError("Слишком мало кандидатов для голосования")
        self.vote = {"candidates": candidates, "voters": [p.id for p in self.alive()],
                     "votes": {}, "stage": "main", "tiebreak": False, "tally": None}
        self.phase = "vote"
        self._log("Голосование началось", "system")
        self.touch()

    def cancel_vote(self, actor: Player) -> None:
        self._require_host(actor)
        if self.phase != "vote":
            raise GameError("Голосование не идёт")
        self.phase = "reveal"
        self.vote = None
        self._log("Ведущий отменил голосование", "system")

    def cast_vote(self, actor: Player, target_id: str) -> None:
        if self.phase != "vote" or not self.vote:
            raise GameError("Голосование не идёт")
        if actor.id not in self.vote["voters"]:
            raise GameError("Сейчас голосуют другие")
        if target_id not in self.vote["candidates"]:
            raise GameError("За этого игрока голосовать нельзя")
        if target_id == actor.id:
            raise GameError("За себя голосовать нельзя")
        self.vote["votes"][actor.id] = target_id
        self.touch()
        if len(self.vote["votes"]) >= len(self.vote["voters"]):
            self._finish_vote()

    def _finish_vote(self) -> None:
        assert self.vote
        tally: dict[str, int] = {c: 0 for c in self.vote["candidates"]}
        for voter_id, target in self.vote["votes"].items():
            weight = 2 if self.player(voter_id).double_vote else 1
            tally[target] = tally.get(target, 0) + weight
        top = max(tally.values())
        leaders = [pid for pid, v in tally.items() if v == top]
        self.vote["tally"] = tally
        names = ", ".join(f"{self.player(pid).name}: {v}" for pid, v in sorted(tally.items(), key=lambda x: -x[1]))
        stage = self.vote["stage"]
        if len(leaders) > 1:
            alive_ids = [p.id for p in self.alive()]
            jury = [p.id for p in self.exiled()]
            # Переголосование имеет смысл, только если кроме лидеров есть кому голосовать.
            if stage == "main" and len(alive_ids) > len(leaders):
                self._log(f"Ничья ({names}). Оправдательная речь и переголосование", "system")
                self.last_vote = dict(self.vote)
                self.vote = {"candidates": leaders, "voters": alive_ids, "votes": {},
                             "stage": "revote", "tiebreak": True, "tally": None}
                return
            if stage != "jury" and jury:
                self._log(f"Ничья ({names}). Решает суд изгнанных: голосуют те, кто снаружи", "system")
                self.last_vote = dict(self.vote)
                self.vote = {"candidates": leaders, "voters": jury, "votes": {},
                             "stage": "jury", "tiebreak": True, "tally": None}
                return
        exiled_id = leaders[0] if len(leaders) == 1 else self.rng.choice(leaders)
        if len(leaders) > 1:
            self._log(f"Снова ничья ({names}): жребий решает", "system")
        elif stage == "jury":
            self._log(f"Суд изгнанных ({names})", "system")
        target = self.player(exiled_id)
        target.status = "out"
        target.exiled_round = self.round
        for c in target.cards.values():
            c["revealed"] = True
        self.last_vote = dict(self.vote)
        self._log(f"Голоса: {names}. {target.name} остаётся снаружи", "exile")
        for p in self.players:
            p.immunity = False
            p.double_vote = False
        self.vote = None
        if len(self.alive()) <= self.seats:
            self._finish_game()
        else:
            self._begin_round(self.round + 1)

    # ---- финал -----------------------------------------------------------
    def finish_now(self, actor: Player) -> None:
        self._require_host(actor)
        if self.phase in ("lobby", "finished"):
            raise GameError("Игра не идёт")
        self._log("Ведущий закрыл дверь бункера досрочно", "system")
        self._finish_game()

    def _finish_game(self) -> None:
        assert self.catastrophe and self.bunker
        self.phase = "finished"
        self.vote = None
        for p in self.players:
            for c in p.cards.values():
                c["revealed"] = True
        survivors = [p.as_player_dict() for p in self.alive()]
        exiled = [p.as_player_dict() for p in self.exiled()]
        self.ending = compute_ending(self.catastrophe, self.bunker, survivors, exiled, seed=str(self.seed))
        self.narrative_status = "pending" if config.OPENAI_API_KEY else "disabled"
        self._log(f"Дверь закрыта. {self.ending['verdict']['title']}", "system")
        self.touch()

    def facts_for_narrator(self) -> str:
        assert self.ending and self.catastrophe and self.bunker
        return ending_facts(self.catastrophe, self.bunker,
                            [p.as_player_dict() for p in self.alive()],
                            [p.as_player_dict() for p in self.exiled()], self.ending)

    # ---- сериализация ----------------------------------------------------
    def public_state(self) -> dict:
        players = []
        for p in self.players:
            revealed = {c: card["text"] for c, card in p.cards.items() if card["revealed"]}
            players.append({
                "id": p.id, "name": p.name, "is_host": p.is_host, "status": p.status,
                "connected": p.connected, "revealed": revealed,
                "hidden_count": len(p.hidden_categories()),
                "immunity": p.immunity, "double_vote": p.double_vote,
                "special_used": bool(p.special and p.special.get("used")),
                "has_special": bool(p.special),
                "exiled_round": p.exiled_round,
                "voted": bool(self.vote and p.id in self.vote["votes"]),
            })
        vote = None
        if self.vote:
            vote = {"candidates": self.vote["candidates"], "voters": self.vote["voters"],
                    "stage": self.vote["stage"], "tiebreak": self.vote["tiebreak"],
                    "voted": list(self.vote["votes"].keys()), "needed": len(self.vote["voters"])}
        last_vote = None
        if self.last_vote and self.last_vote.get("tally"):
            last_vote = {"tally": self.last_vote["tally"], "tiebreak": self.last_vote["tiebreak"]}
        return {
            "code": self.code, "phase": self.phase, "round": self.round, "seats": self.seats,
            "settings": self.settings, "players": players, "alive_count": len(self.alive()),
            "catastrophe": self.catastrophe, "bunker": self.bunker,
            "vote": vote, "last_vote": last_vote, "log": self.log[-60:],
            "ending": self.ending, "narrative": self.narrative, "narrative_status": self.narrative_status,
            "categories": [{"key": c, "title": CATEGORY_TITLES[c]} for c in CATEGORIES],
            "min_players": config.MIN_PLAYERS,
        }

    def private_state(self, p: Player) -> dict:
        return {
            "id": p.id, "name": p.name, "is_host": p.is_host, "status": p.status,
            "cards": p.cards, "special": p.special, "reveals_left": p.reveals_left,
            "my_vote": (self.vote or {}).get("votes", {}).get(p.id),
        }

    # ---- диспетчер действий ---------------------------------------------
    def apply(self, actor: Player, action: dict[str, Any]) -> None:
        t = action.get("type")
        if t == "start":
            self.start(actor)
        elif t == "settings":
            self.update_settings(actor, action.get("seats"), action.get("reveals_per_round"), action.get("specials"))
        elif t == "kick":
            self.kick(actor, str(action.get("player_id")))
        elif t == "reveal":
            self.reveal(actor, str(action.get("category")))
        elif t == "special":
            self.play_special(actor, action.get("target_id"))
        elif t == "start_vote":
            self.start_vote(actor)
        elif t == "cancel_vote":
            self.cancel_vote(actor)
        elif t == "vote":
            self.cast_vote(actor, str(action.get("target_id")))
        elif t == "finish_now":
            self.finish_now(actor)
        else:
            raise GameError("Неизвестное действие")
