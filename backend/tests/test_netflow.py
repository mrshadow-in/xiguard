"""NetFlow v9 parser: template handling and data record extraction."""
from __future__ import annotations

import socket
import struct

from app.services.netflow import (
    F_IN_BYTES,
    F_IN_PKTS,
    F_IPV4_DST_ADDR,
    F_IPV4_SRC_ADDR,
    F_L4_DST_PORT,
    F_PROTOCOL,
    NetFlowParser,
)


def _header(count: int, source_id: int = 1) -> bytes:
    return struct.pack("!HHIIII", 9, count, 0, 0, 0, source_id)


def _template_flowset(template_id: int, fields: list[tuple[int, int]]) -> bytes:
    body = struct.pack("!HH", template_id, len(fields))
    for ftype, flen in fields:
        body += struct.pack("!HH", ftype, flen)
    fs = struct.pack("!HH", 0, 4 + len(body)) + body
    return fs


def _data_flowset(template_id: int, records: bytes) -> bytes:
    return struct.pack("!HH", template_id, 4 + len(records)) + records


def test_data_records_dropped_until_template_arrives():
    parser = NetFlowParser()
    # Send a data record for template 256 before the template — should drop silently.
    payload = _header(1) + _data_flowset(256, b"\x00" * 16)
    assert list(parser.parse(payload, "10.0.0.1")) == []


def test_template_then_data_yields_records():
    parser = NetFlowParser()
    fields = [
        (F_IPV4_SRC_ADDR, 4),
        (F_IPV4_DST_ADDR, 4),
        (F_IN_BYTES, 4),
        (F_IN_PKTS, 4),
        (F_PROTOCOL, 1),
        (F_L4_DST_PORT, 2),
    ]
    tpl = _template_flowset(256, fields)
    parser.parse(_header(1) + tpl, "10.0.0.1")
    list(parser.parse(_header(1) + tpl, "10.0.0.1"))  # no records, just templates

    src = socket.inet_aton("203.0.113.7")
    dst = socket.inet_aton("162.141.0.15")
    rec = src + dst + (1_500_000).to_bytes(4, "big") + (1_200).to_bytes(4, "big") + b"\x06" + (443).to_bytes(2, "big")

    payload = _header(1) + _data_flowset(256, rec * 2)  # two records back-to-back
    records = list(parser.parse(payload, "10.0.0.1"))

    assert len(records) == 2
    for r in records:
        assert r.src_addr == "203.0.113.7"
        assert r.dst_addr == "162.141.0.15"
        assert r.in_bytes == 1_500_000
        assert r.in_pkts == 1_200
        assert r.protocol == 6
        assert r.dst_port == 443


def test_templates_are_per_exporter():
    parser = NetFlowParser()
    fields = [(F_IPV4_DST_ADDR, 4), (F_IN_BYTES, 4), (F_IN_PKTS, 4)]
    parser.parse(_header(1) + _template_flowset(256, fields), "10.0.0.1")

    dst = socket.inet_aton("162.141.0.15")
    rec = dst + (100).to_bytes(4, "big") + (5).to_bytes(4, "big")
    payload = _header(1) + _data_flowset(256, rec)

    # Same template id but a DIFFERENT exporter — should NOT match.
    assert list(parser.parse(payload, "10.0.0.2")) == []
    # Same exporter — matches.
    assert len(list(parser.parse(payload, "10.0.0.1"))) == 1


def test_unknown_fields_in_template_are_skipped_safely():
    parser = NetFlowParser()
    # Mix one relevant field, two unknown fields with lengths we must skip past.
    fields = [
        (F_IN_BYTES, 4),
        (999, 8),                # unknown — skip 8 bytes
        (F_IPV4_DST_ADDR, 4),
        (998, 2),                # unknown — skip 2 bytes
    ]
    parser.parse(_header(1) + _template_flowset(256, fields), "10.0.0.1")

    dst = socket.inet_aton("162.141.0.15")
    rec = (12345).to_bytes(4, "big") + b"\x00" * 8 + dst + b"\x00" * 2
    payload = _header(1) + _data_flowset(256, rec)
    records = list(parser.parse(payload, "10.0.0.1"))
    assert len(records) == 1
    assert records[0].dst_addr == "162.141.0.15"
    assert records[0].in_bytes == 12345


def test_short_packet_returns_empty():
    parser = NetFlowParser()
    assert list(parser.parse(b"", "10.0.0.1")) == []
    assert list(parser.parse(b"\x00" * 10, "10.0.0.1")) == []


def test_non_v9_packet_returns_empty():
    parser = NetFlowParser()
    payload = struct.pack("!HHIIII", 5, 1, 0, 0, 0, 0) + b"\x00" * 20  # v5 header
    assert list(parser.parse(payload, "10.0.0.1")) == []
