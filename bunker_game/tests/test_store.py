import asyncio

import fakeredis.aioredis

from app.game import Room
from app.store import FileStore, RedisStore


def play_a_bit(room):
    ps = [room.add_player(f"P{i}", is_host=(i == 0)) for i in range(4)]
    room.start(ps[0])
    room.reveal(ps[1], next(c for c in ps[1].cards if not ps[1].cards[c]["revealed"]))
    room.start_vote(ps[0])
    room.cast_vote(ps[0], ps[3].id)
    return ps


def test_room_roundtrip_preserves_state_and_rng():
    room = Room("ABCDE", seed=5)
    ps = play_a_bit(room)
    copy = Room.from_dict(room.to_dict())
    assert copy.phase == "vote" and copy.round == 1 and copy.seats == room.seats
    assert [p.name for p in copy.players] == [p.name for p in room.players]
    assert copy.players[1].token == ps[1].token
    assert copy.players[1].cards == ps[1].cards
    assert copy.vote == room.vote
    assert copy.rng.random() == room.rng.random()
    # восстановленная комната продолжает партию
    for p in copy.players[1:]:
        copy.cast_vote(p, copy.players[3].id if p is not copy.players[3] else copy.players[0].id)
    assert copy.players[3].status == "out"


def test_file_store_roundtrip(tmp_path):
    async def run():
        store = FileStore(str(tmp_path))
        room = Room("FILE1", seed=1)
        play_a_bit(room)
        await store.save(room.to_dict())
        again = FileStore(str(tmp_path))
        rooms = await again.load_all()
        assert len(rooms) == 1 and rooms[0]["code"] == "FILE1"
        await again.delete("FILE1")
        assert await FileStore(str(tmp_path)).load_all() == []
    asyncio.run(run())


def test_redis_store_roundtrip():
    async def run():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisStore("redis://unused", ttl_seconds=60, client=client)
        room = Room("RED12", seed=2)
        play_a_bit(room)
        await store.save(room.to_dict())
        rooms = await store.load_all()
        assert len(rooms) == 1 and Room.from_dict(rooms[0]).phase == "vote"
        await store.delete("RED12")
        assert await store.load_all() == []
    asyncio.run(run())
