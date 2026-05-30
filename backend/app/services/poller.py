"""Per-IP traffic poller — reads NetFlow counters from Redis.

The polling task previously talked to each CHR for /ip/accounting/snapshot.
That feature was removed in RouterOS 7, so traffic data is now fed by the
flow-collector service via Redis hashes keyed `xiguard:flow:<ip>`.

read_and_reset() is implemented as a Lua script so HGETALL + DEL happens
atomically — no flow-collector writes can be lost or double-counted
between the read and the clear.
"""
from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from app.config import settings
from app.services.flow_collector import flow_key
from app.services.pubsub import get_redis

# KEYS[1] = the hash key.  Returns the prior contents as a flat list, then deletes the key.
_READ_RESET_LUA = """
local data = redis.call('HGETALL', KEYS[1])
if next(data) ~= nil then
    redis.call('DEL', KEYS[1])
end
return data
"""


@dataclass
class PerIPSample:
    bps_in: int
    bps_out: int
    pps_in: int
    pps_out: int


_script_sha: str | None = None


async def _ensure_script(redis: Redis) -> str:
    global _script_sha
    if _script_sha is None:
        _script_sha = await redis.script_load(_READ_RESET_LUA)
    return _script_sha


async def _read_and_reset(redis: Redis, key: str) -> dict[str, int]:
    sha = await _ensure_script(redis)
    try:
        flat = await redis.evalsha(sha, 1, key)
    except Exception:
        flat = await redis.eval(_READ_RESET_LUA, 1, key)
    out: dict[str, int] = {}
    for i in range(0, len(flat), 2):
        try:
            out[flat[i]] = int(flat[i + 1])
        except (TypeError, ValueError):
            continue
    return out


async def sample_ip(ip_address: str, redis: Redis | None = None) -> PerIPSample:
    r = redis or get_redis()
    data = await _read_and_reset(r, flow_key(ip_address))
    iv = max(1, int(settings.poll_interval_sec))
    return PerIPSample(
        bps_in=(data.get("bytes_in", 0) * 8) // iv,
        bps_out=(data.get("bytes_out", 0) * 8) // iv,
        pps_in=data.get("pkts_in", 0) // iv,
        pps_out=data.get("pkts_out", 0) // iv,
    )


async def sample_many(ips: list[str], redis: Redis | None = None) -> dict[str, PerIPSample]:
    r = redis or get_redis()
    out: dict[str, PerIPSample] = {}
    for ip in ips:
        out[ip] = await sample_ip(ip, r)
    return out
