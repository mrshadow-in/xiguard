"""asyncio UDP server: receives NetFlow v9 packets, increments per-IP Redis counters.

For each flow record, we add `in_bytes` and `in_pkts` to:
  HSET xiguard:flow:<dst_ip>  bytes_in  <delta>   pkts_in  <delta>
and (so we have outbound visibility too):
  HSET xiguard:flow:<src_ip>  bytes_out <delta>   pkts_out <delta>

The polling task atomically reads + clears these hashes each cycle and
divides by POLL_INTERVAL_SEC to get bps/pps.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from redis.asyncio import Redis

from app.config import settings
from app.services.netflow import NetFlowParser
from app.services.pubsub import get_redis

logger = logging.getLogger(__name__)

_LISTEN_PORT = 2055
_FLUSH_INTERVAL_SEC = 1.0  # accumulate locally then flush in batches


def flow_key(ip: str) -> str:
    return f"xiguard:flow:{ip}"


class FlowProtocol(asyncio.DatagramProtocol):
    def __init__(self, parser: NetFlowParser, buffer: dict[str, dict[str, int]]) -> None:
        self.parser = parser
        self.buffer = buffer
        self.packets = 0
        self.records = 0

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.packets += 1
        try:
            for record in self.parser.parse(data, addr[0]):
                self.records += 1
                if record.dst_addr and record.in_bytes > 0:
                    e = self.buffer[record.dst_addr]
                    e["bytes_in"] = e.get("bytes_in", 0) + record.in_bytes
                    e["pkts_in"] = e.get("pkts_in", 0) + record.in_pkts
                if record.src_addr and record.in_bytes > 0:
                    e = self.buffer[record.src_addr]
                    e["bytes_out"] = e.get("bytes_out", 0) + record.in_bytes
                    e["pkts_out"] = e.get("pkts_out", 0) + record.in_pkts
        except Exception:
            logger.exception("netflow parse failure from %s", addr)


async def _flush_loop(redis: Redis, buffer: dict[str, dict[str, int]]) -> None:
    while True:
        await asyncio.sleep(_FLUSH_INTERVAL_SEC)
        if not buffer:
            continue
        # Snapshot + clear so the collector can keep accumulating.
        snapshot = buffer
        buffer.clear()
        pipe = redis.pipeline(transaction=False)
        for ip, fields in snapshot.items():
            key = flow_key(ip)
            for name, val in fields.items():
                pipe.hincrby(key, name, val)
            # Auto-expire orphaned counters (IPs that stop receiving flows).
            pipe.expire(key, 60)
        try:
            await pipe.execute()
        except Exception:
            logger.exception("redis flush failed")


async def serve() -> None:
    logging.basicConfig(level=settings.log_level)
    parser = NetFlowParser()
    buffer: dict[str, dict[str, int]] = defaultdict(dict)
    redis = get_redis()

    loop = asyncio.get_running_loop()
    transport, _proto = await loop.create_datagram_endpoint(
        lambda: FlowProtocol(parser, buffer),
        local_addr=("0.0.0.0", _LISTEN_PORT),
    )
    logger.warning("flow-collector listening on UDP %d", _LISTEN_PORT)

    flush_task = asyncio.create_task(_flush_loop(redis, buffer))
    try:
        await asyncio.Event().wait()  # run forever
    finally:
        flush_task.cancel()
        transport.close()


def main() -> None:
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
