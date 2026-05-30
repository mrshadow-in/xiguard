"""Minimal NetFlow v9 packet parser.

NetFlow v9 is stateful: exporters first send template records that describe
the field layout of subsequent data records. We keep templates keyed by
(exporter_address, source_id, template_id) and parse data records against
the matching template.

We only care about a handful of fields per flow:

  IPV4_SRC_ADDR (8)   IPV4_DST_ADDR (12)
  IN_BYTES (1)        IN_PKTS (2)
  PROTOCOL (4)
  L4_SRC_PORT (7)     L4_DST_PORT (11)

Everything else is parsed for its length so we can skip past it, but the
values are discarded.

References:
- RFC 3954 (Cisco NetFlow v9)
- MikroTik docs: https://help.mikrotik.com/docs/spaces/ROS/pages/24805502/Traffic+Flow
"""
from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from typing import Iterator

# NetFlow v9 field type IDs we read.
F_IN_BYTES = 1
F_IN_PKTS = 2
F_PROTOCOL = 4
F_L4_SRC_PORT = 7
F_IPV4_SRC_ADDR = 8
F_L4_DST_PORT = 11
F_IPV4_DST_ADDR = 12

_RELEVANT_FIELDS = {
    F_IN_BYTES, F_IN_PKTS, F_PROTOCOL,
    F_L4_SRC_PORT, F_IPV4_SRC_ADDR, F_L4_DST_PORT, F_IPV4_DST_ADDR,
}


@dataclass(frozen=True)
class TemplateKey:
    exporter: str
    source_id: int
    template_id: int


@dataclass
class TemplateField:
    type_id: int
    length: int


@dataclass
class FlowRecord:
    src_addr: str | None
    dst_addr: str | None
    in_bytes: int
    in_pkts: int
    protocol: int | None
    src_port: int | None
    dst_port: int | None


class NetFlowParser:
    """Stateful NetFlow v9 parser. Maintains per-exporter template cache."""

    def __init__(self) -> None:
        self._templates: dict[TemplateKey, list[TemplateField]] = {}

    def parse(self, data: bytes, exporter: str) -> Iterator[FlowRecord]:
        if len(data) < 20:
            return
        version, count, _uptime, _ts, _seq, source_id = struct.unpack(
            "!HHIIII", data[:20]
        )
        if version != 9:
            return

        offset = 20
        end = len(data)

        # The header `count` is the number of records across all FlowSets in v9
        # (some Cisco docs say FlowSets, but the field is records — we ignore it
        # and just walk the buffer to end of packet).

        while offset + 4 <= end:
            fs_id, fs_len = struct.unpack("!HH", data[offset:offset + 4])
            if fs_len < 4 or offset + fs_len > end:
                return
            body = data[offset + 4:offset + fs_len]
            offset += fs_len

            if fs_id == 0:
                # Template FlowSet — may carry several templates back to back.
                self._consume_templates(body, exporter, source_id)
            elif fs_id == 1:
                # Options template — we don't need options data; skip.
                continue
            elif fs_id >= 256:
                yield from self._consume_data(body, exporter, source_id, fs_id)
            else:
                # 2..255 reserved — ignore.
                continue

    # ── template handling ────────────────────────────────────────────────
    def _consume_templates(self, body: bytes, exporter: str, source_id: int) -> None:
        i = 0
        end = len(body)
        while i + 4 <= end:
            tid, fcount = struct.unpack("!HH", body[i:i + 4])
            i += 4
            fields: list[TemplateField] = []
            for _ in range(fcount):
                if i + 4 > end:
                    return
                ftype, flen = struct.unpack("!HH", body[i:i + 4])
                i += 4
                fields.append(TemplateField(ftype, flen))
            key = TemplateKey(exporter=exporter, source_id=source_id, template_id=tid)
            self._templates[key] = fields

    # ── data handling ────────────────────────────────────────────────────
    def _consume_data(
        self, body: bytes, exporter: str, source_id: int, template_id: int
    ) -> Iterator[FlowRecord]:
        key = TemplateKey(exporter=exporter, source_id=source_id, template_id=template_id)
        tmpl = self._templates.get(key)
        if not tmpl:
            return  # template not yet known; drop until exporter resends it
        record_len = sum(f.length for f in tmpl)
        if record_len == 0:
            return
        i = 0
        end = len(body)
        while i + record_len <= end:
            yield self._parse_record(body[i:i + record_len], tmpl)
            i += record_len

    def _parse_record(self, raw: bytes, fields: list[TemplateField]) -> FlowRecord:
        src = dst = None
        proto = sport = dport = None
        in_bytes = 0
        in_pkts = 0
        pos = 0
        for f in fields:
            val = raw[pos:pos + f.length]
            pos += f.length
            if f.type_id not in _RELEVANT_FIELDS:
                continue
            if f.type_id == F_IN_BYTES:
                in_bytes = _be_int(val)
            elif f.type_id == F_IN_PKTS:
                in_pkts = _be_int(val)
            elif f.type_id == F_PROTOCOL:
                proto = _be_int(val)
            elif f.type_id == F_L4_SRC_PORT:
                sport = _be_int(val)
            elif f.type_id == F_L4_DST_PORT:
                dport = _be_int(val)
            elif f.type_id == F_IPV4_SRC_ADDR and f.length == 4:
                src = socket.inet_ntoa(val)
            elif f.type_id == F_IPV4_DST_ADDR and f.length == 4:
                dst = socket.inet_ntoa(val)
        return FlowRecord(
            src_addr=src, dst_addr=dst,
            in_bytes=in_bytes, in_pkts=in_pkts,
            protocol=proto, src_port=sport, dst_port=dport,
        )


def _be_int(b: bytes) -> int:
    return int.from_bytes(b, "big", signed=False)
