"""Redis pub/sub channel names and helpers."""
from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from app.config import settings

CH_TRAFFIC = "xiguard:traffic"
CH_ALERTS = "xiguard:alerts"
CH_STATE = "xiguard:state"
CH_CHR_STATUS = "xiguard:chr_status"


_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def publish(channel: str, payload: dict[str, Any]) -> None:
    r = get_redis()
    await r.publish(channel, json.dumps(payload, default=str))
