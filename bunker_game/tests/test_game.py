import pytest

from app.game import GameError, Room


def make_room(n=6, seed=42):
    room = Room("TEST1", seed=seed)
    players = [room.add_player(f"P{i}", is_host=(i == 0)) for i in range(n)]
    return room, players


def test_lobby_and_start():
    room, ps = make_room(6)
    assert room.seats == 3
    assert ps[0].is_host
    with pytest.raises(GameError):
        room.start(ps[1])
    room.start(ps[0])
    assert room.phase == "reveal" and room.round == 1
    for p in ps:
        assert p.cards["profession"]["revealed"]
        assert len(p.cards) == 7
        assert p.special is not None


def test_cannot_join_after_start():
    room, ps = make_room(4)
    room.start(ps[0])
    with pytest.raises(GameError):
        room.add_player("Late")


def test_reveal_limits():
    room, ps = make_room(4)
    room.start(ps[0])
    p = ps[1]
    hidden = [c for c in p.cards if not p.cards[c]["revealed"]]
    room.reveal(p, hidden[0])
    with pytest.raises(GameError):
        room.reveal(p, hidden[1])
    with pytest.raises(GameError):
        room.reveal(p, hidden[0])


def _vote_all(room, target):
    for p in room.alive():
        if p.id != target.id:
            room.cast_vote(p, target.id)
    # сам target голосует за кого-то другого
    other = next(p for p in room.alive() if p.id != target.id)
    if target.status == "alive" and room.phase == "vote":
        room.cast_vote(target, other.id)


def test_full_game_to_ending():
    room, ps = make_room(5)  # seats = 2 -> три изгнания
    room.start(ps[0])
    rounds = 0
    while room.phase != "finished":
        rounds += 1
        room.start_vote(ps[0])
        target = room.alive()[-1]
        _vote_all(room, target)
        assert target.status == "out"
        assert rounds < 10
    assert len(room.alive()) == room.seats == 2
    assert room.ending is not None
    assert room.ending["verdict"]["total"] == 2
    assert len(room.ending["outside"]) == 3
    state = room.public_state()
    assert state["phase"] == "finished" and state["ending"]
    # все карты открыты в финале
    assert all(p["hidden_count"] == 0 for p in state["players"])


def test_tie_leads_to_revote_then_random():
    room, ps = make_room(4)
    room.start(ps[0])
    room.start_vote(ps[0])
    a, b, c, d = room.alive()
    room.cast_vote(a, b.id)
    room.cast_vote(b, a.id)
    room.cast_vote(c, b.id)
    room.cast_vote(d, a.id)
    assert room.phase == "vote" and room.vote["tiebreak"]
    assert set(room.vote["candidates"]) == {a.id, b.id}
    room.cast_vote(a, b.id)
    room.cast_vote(b, a.id)
    room.cast_vote(c, b.id)
    room.cast_vote(d, a.id)
    assert room.phase == "reveal"
    assert sum(1 for p in room.players if p.status == "out") == 1


def test_vote_rules():
    room, ps = make_room(4)
    room.start(ps[0])
    with pytest.raises(GameError):
        room.cast_vote(ps[0], ps[1].id)
    room.start_vote(ps[0])
    with pytest.raises(GameError):
        room.cast_vote(ps[0], ps[0].id)


def test_specials():
    room, ps = make_room(5)
    room.start(ps[0])
    p = ps[1]
    p.special = {"id": "x", "title": "Неприкасаемый", "effect": "immunity", "text": "", "used": False}
    room.play_special(p)
    assert p.immunity and p.special["used"]
    with pytest.raises(GameError):
        room.play_special(p)
    room.start_vote(ps[0])
    assert p.id not in room.vote["candidates"]
    room.cancel_vote(ps[0])
    q = ps[2]
    q.special = {"id": "y", "title": "Бартер", "effect": "swap", "category": "baggage", "text": "", "used": False}
    mine, theirs = q.cards["baggage"]["text"], ps[3].cards["baggage"]["text"]
    room.play_special(q, target_id=ps[3].id)
    assert q.cards["baggage"]["text"] == theirs and ps[3].cards["baggage"]["text"] == mine
    assert q.cards["baggage"]["revealed"] and ps[3].cards["baggage"]["revealed"]
    r = ps[4]
    r.special = {"id": "z", "title": "Потайная комната", "effect": "extra_seat", "text": "", "used": False}
    seats = room.seats
    room.play_special(r)
    assert room.seats == seats + 1


def test_private_state_hides_nothing_from_owner_and_public_hides_hidden():
    room, ps = make_room(3)
    room.start(ps[0])
    pub = room.public_state()
    me = room.private_state(ps[0])
    assert set(me["cards"]) == {"profession", "biology", "health", "hobby", "baggage", "fact", "phobia"}
    mine_pub = next(p for p in pub["players"] if p["id"] == ps[0].id)
    assert list(mine_pub["revealed"]) == ["profession"]
    assert mine_pub["hidden_count"] == 6
