"""asyncio UDP server: receives NetFlow v9 packets, increments per-IP Redis counters.

For each flow record, we add `in_bytes` and `in_pkts` to:
  HSET xiguard:flow:<dst_ip>  bytes_in  <delta>   pkts_in  <delta>
and (so we have outbound visibility too):
  HSET xiguard:flow:<src_ip>  bytes_out <delta>   pkts_out <delta>

The polling task atomically reads + clears these hashes each cycle and
divides by POLL_INTERVAL_SEC to get bps/pps.

We also publish per-exporter packet counts to xiguard:stats:flow:exporter:<ip>
so the Polling page can show which CHRs are actively shipping flows.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from redis.asyncio import Redis

from app.config import settings
from app.services import stats
from app.services.netflow import NetFlowParser
from app.services.pubsub import get_redis

logger = logging.getLogger(__name__)

_LISTEN_PORT = 2055
_FLUSH_INTERVAL_SEC = 1.0  # accumulate locally then flush in batches


def flow_key(ip: str) -> str:
    return f"xiguard:flow:{ip}"


class FlowProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        parser: NetFlowParser,
        buffer: dict[str, dict[str, int]],
        exporter_pkts: dict[str, int],
        meta: dict[str, int],
    ) -> None:
        self.parser = parser
        self.buffer = buffer
        self.exporter_pkts = exporter_pkts
        self.meta = meta

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.meta["packets"] = self.meta.get("packets", 0) + 1
        self.exporter_pkts[addr[0]] = self.exporter_pkts.get(addr[0], 0) + 1
        try:
            for record in self.parser.parse(data, addr[0]):
                self.meta["records"] = self.meta.get("records", 0) + 1
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


async def _flush_loop(
    redis: Redis,
    buffer: dict[str, dict[str, int]],
    exporter_pkts: dict[str, int],
    meta: dict[str, int],
) -> None:
    while True:
        await asyncio.sleep(_FLUSH_INTERVAL_SEC)

        # ── flush per-IP traffic counters ────────────────────────────
        snapshot = buffer
        if snapshot:
            buffer.clear()
            pipe = redis.pipeline(transaction=False)
            for ip, fields in snapshot.items():
                key = flow_key(ip)
                for name, val in fields.items():
                    pipe.hincrby(key, name, val)
                pipe.expire(key, 60)
            try:
                await pipe.execute()
            except Exception:
                logger.exception("redis flush failed")

        # ── flush meta (packets + per-exporter counters) ────────────
        packets = meta.get("packets", 0)
        records = meta.get("records", 0)
        meta["packets"] = 0
        meta["records"] = 0
        exp_snap = dict(exporter_pkts)
        exporter_pkts.clear()
        if packets or records or exp_snap:
            try:
                await stats.record_flow_batch(
                    packets=packets,
                    records=records,
                    per_exporter_packets=exp_snap,
                    redis=redis,
                )
            except Exception:
                logger.exception("flow meta flush failed")


async def serve() -> None:
    logging.basicConfig(level=settings.log_level)
    parser = NetFlowParser()
    buffer: dict[str, dict[str, int]] = defaultdict(dict)
    exporter_pkts: dict[str, int] = {}
    meta: dict[str, int] = {"packets": 0, "records": 0}
    redis = get_redis()

    loop = asyncio.get_running_loop()
    transport, _proto = await loop.create_datagram_endpoint(
        lambda: FlowProtocol(parser, buffer, exporter_pkts, meta),
        local_addr=("0.0.0.0", _LISTEN_PORT),
    )
    logger.warning("flow-collector listening on UDP %d", _LISTEN_PORT)

    flush_task = asyncio.create_task(_flush_loop(redis, buffer, exporter_pkts, meta))
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
