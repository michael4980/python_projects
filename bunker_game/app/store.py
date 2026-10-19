"""Сохранение комнат между перезапусками: Redis (REDIS_URL) или JSON-файл (DATA_DIR)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from . import config

log = logging.getLogger("bunker.store")
PREFIX = "bunker:room:"


class FileStore:
    """Один JSON-файл со всеми комнатами. Для локального запуска и VPS с volume."""

    def __init__(self, data_dir: str) -> None:
        self.path = Path(data_dir) / "rooms.json"
        self._lock = asyncio.Lock()
        self._rooms: dict[str, dict] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                self._rooms = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                log.warning("cannot read %s: %s", self.path, e)

    async def load_all(self) -> list[dict]:
        return list(self._rooms.values())

    async def save(self, data: dict) -> None:
        self._rooms[data["code"]] = data
        await self._flush()

    async def delete(self, code: str) -> None:
        self._rooms.pop(code, None)
        await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._rooms, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)

    async def close(self) -> None:
        return None


class RedisStore:
    def __init__(self, url: str, ttl_seconds: int, client=None) -> None:
        if client is None:
            import redis.asyncio as redis_async

            client = redis_async.from_url(url, decode_responses=True)
        self.r = client
        self.ttl = ttl_seconds

    async def load_all(self) -> list[dict]:
        rooms = []
        async for key in self.r.scan_iter(match=PREFIX + "*"):
            raw = await self.r.get(key)
            if raw:
                try:
                    rooms.append(json.loads(raw))
                except json.JSONDecodeError:
                    log.warning("broken room record %s", key)
        return rooms

    async def save(self, data: dict) -> None:
        await self.r.set(PREFIX + data["code"], json.dumps(data, ensure_ascii=False), ex=self.ttl)

    async def delete(self, code: str) -> None:
        await self.r.delete(PREFIX + code)

    async def close(self) -> None:
        await self.r.aclose()


def make_store():
    ttl = int(config.ROOM_TTL_HOURS * 3600)
    if config.REDIS_URL:
        log.info("rooms are stored in Redis")
        return RedisStore(config.REDIS_URL, ttl)
    log.info("rooms are stored in %s", config.DATA_DIR)
    return FileStore(config.DATA_DIR)
