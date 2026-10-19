"""FastAPI: REST для входа в комнату и WebSocket для игры."""
from __future__ import annotations

import asyncio
import hmac
import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .game import GameError, Room, new_room_code
from .narrator import generate_narrative
from .store import make_store

log = logging.getLogger("bunker")
STATIC_DIR = Path(__file__).parent / "static"


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.sockets: dict[str, dict[str, set[WebSocket]]] = {}  # code -> player_id -> sockets
        self.narrative_tasks: dict[str, asyncio.Task] = {}
        self.store = None

    async def restore(self) -> None:
        """Поднимает комнаты из хранилища при старте сервера."""
        self.store = make_store()
        try:
            records = await self.store.load_all()
        except Exception as e:  # noqa: BLE001
            log.exception("cannot load rooms: %s", e)
            return
        for data in records:
            try:
                room = Room.from_dict(data)
            except Exception as e:  # noqa: BLE001
                log.warning("skip broken room %s: %s", data.get("code"), e)
                continue
            self.rooms[room.code] = room
            self.sockets[room.code] = {}
            self._maybe_start_narrative(room)
        log.info("restored %d rooms", len(records))

    async def persist(self, room: Room) -> None:
        if self.store is None:
            return
        try:
            await self.store.save(room.to_dict())
        except Exception as e:  # noqa: BLE001
            log.warning("cannot save room %s: %s", room.code, e)

    def create(self) -> Room:
        code = new_room_code()
        while code in self.rooms:
            code = new_room_code()
        room = Room(code)
        self.rooms[code] = room
        self.sockets[code] = {}
        return room

    def get(self, code: str) -> Room:
        room = self.rooms.get(code.upper())
        if room is None:
            raise HTTPException(404, "Комната не найдена")
        return room

    async def broadcast(self, room: Room) -> None:
        public = room.public_state()
        dead: list[tuple[str, WebSocket]] = []
        for pid, socks in list(self.sockets.get(room.code, {}).items()):
            try:
                player = room.player(pid)
            except GameError:
                continue
            msg = {"type": "state", "state": public, "you": room.private_state(player)}
            for ws in list(socks):
                try:
                    await ws.send_json(msg)
                except Exception:  # noqa: BLE001
                    dead.append((pid, ws))
        for pid, ws in dead:
            self.sockets[room.code][pid].discard(ws)
        self._maybe_start_narrative(room)
        await self.persist(room)

    def _maybe_start_narrative(self, room: Room) -> None:
        if room.phase != "finished" or room.narrative_status != "pending" or room.code in self.narrative_tasks:
            return
        self.narrative_tasks[room.code] = asyncio.create_task(self._narrate(room))

    async def _narrate(self, room: Room) -> None:
        try:
            text = await generate_narrative(room.facts_for_narrator())
            room.narrative = text
            room.narrative_status = "done" if text else "failed"
        finally:
            self.narrative_tasks.pop(room.code, None)
            await self.broadcast(room)

    async def cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(600)
            ttl = config.ROOM_TTL_HOURS * 3600
            now = time.time()
            for code, room in list(self.rooms.items()):
                if now - room.touched_at > ttl:
                    self.rooms.pop(code, None)
                    self.sockets.pop(code, None)
                    if self.store is not None:
                        try:
                            await self.store.delete(code)
                        except Exception as e:  # noqa: BLE001
                            log.warning("cannot delete room %s: %s", code, e)


manager = RoomManager()
app = FastAPI(title="Бункер")


@app.on_event("startup")
async def _startup() -> None:
    await manager.restore()
    asyncio.create_task(manager.cleanup_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    if manager.store is not None:
        await manager.store.close()


class CreateRoom(BaseModel):
    name: str
    master_code: str = ""


class JoinRoom(BaseModel):
    name: str


@app.get("/api/config")
def api_config() -> dict:
    return {"master_required": bool(config.MASTER_CODE), "narrator": bool(config.OPENAI_API_KEY),
            "min_players": config.MIN_PLAYERS, "max_players": config.MAX_PLAYERS}


@app.post("/api/rooms")
async def api_create_room(body: CreateRoom) -> dict:
    if config.MASTER_CODE and not hmac.compare_digest(body.master_code.strip(), config.MASTER_CODE):
        raise HTTPException(403, "Неверный мастер-код")
    room = manager.create()
    try:
        player = room.add_player(body.name, is_host=True)
    except GameError as e:
        manager.rooms.pop(room.code, None)
        raise HTTPException(400, str(e))
    await manager.persist(room)
    return {"code": room.code, "token": player.token, "player_id": player.id}


@app.post("/api/rooms/{code}/join")
async def api_join_room(code: str, body: JoinRoom) -> dict:
    room = manager.get(code)
    try:
        player = room.add_player(body.name)
    except GameError as e:
        raise HTTPException(400, str(e))
    await manager.broadcast(room)
    return {"code": room.code, "token": player.token, "player_id": player.id}


@app.get("/api/rooms/{code}")
def api_room_info(code: str) -> dict:
    room = manager.get(code)
    return {"code": room.code, "phase": room.phase, "players": len(room.players)}


@app.websocket("/ws/{code}")
async def ws_room(ws: WebSocket, code: str, token: str = "") -> None:
    room = manager.rooms.get(code.upper())
    player = room.player_by_token(token) if room else None
    if room is None or player is None:
        # Сначала принимаем соединение, иначе браузер не увидит код закрытия.
        await ws.accept()
        await ws.close(code=4404, reason="room not found")
        return
    await ws.accept()
    manager.sockets[room.code].setdefault(player.id, set()).add(ws)
    player.connected = True
    await manager.broadcast(room)
    try:
        while True:
            action = await ws.receive_json()
            room.touch()
            try:
                room.apply(player, action)
            except GameError as e:
                await ws.send_json({"type": "error", "message": str(e)})
                continue
            except Exception as e:  # noqa: BLE001
                log.exception("action failed")
                await ws.send_json({"type": "error", "message": f"Ошибка сервера: {e}"})
                continue
            await manager.broadcast(room)
    except WebSocketDisconnect:
        pass
    finally:
        socks = manager.sockets.get(room.code, {}).get(player.id)
        if socks is not None:
            socks.discard(ws)
            if not socks:
                player.connected = False
                await manager.broadcast(room)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
