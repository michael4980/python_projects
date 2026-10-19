"""Настройки из переменных окружения."""
import os

# Если задан, создать комнату можно только с этим кодом (для публичного хостинга).
MASTER_CODE: str = os.environ.get("MASTER_CODE", "").strip()
# Ключ OpenAI для художественной «хроники». Без ключа концовка показывается только из движка.
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_BASE_URL: str = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
# Через сколько часов бездействия комната удаляется.
ROOM_TTL_HOURS: float = float(os.environ.get("ROOM_TTL_HOURS", "8"))
MIN_PLAYERS: int = int(os.environ.get("MIN_PLAYERS", "3"))
MAX_PLAYERS: int = 16
# Хранилище комнат: REDIS_URL (Render Key Value / любой Redis) или файл в DATA_DIR.
REDIS_URL: str = os.environ.get("REDIS_URL", "").strip()
DATA_DIR: str = os.environ.get("DATA_DIR", "data").strip()
