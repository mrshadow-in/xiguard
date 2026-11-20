"""Showcase traffic simulator and attack control panel.

Runs inside the CHR container and exports NetFlow v9 to Xiguard's flow
collector, the same way the CHR's own Traffic Flow does, but for simulated
customer traffic on the showcase prefixes. Real packets would not work for a
demo: a free (unlicensed) CHR is capped at 1 Mbps per interface, far below
Xiguard's 10 Mbps spike floor. Synthetic flows can show a multi-gigabit flood.

Every second it sends one inbound and one reply record per active host, plus
flood records for any attack launched from the panel on PANEL_PORT.

Self-check: `python3 simulator.py selftest`
"""
from __future__ import annotations

import ipaddress
import json
import math
import os
import random
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREFIXES = [
    ipaddress.ip_network(p.strip(), strict=False)
    for p in os.environ.get("SHOWCASE_PREFIXES", "203.0.113.0/24").split(",")
    if p.strip()
]
COLLECTOR_HOST, COLLECTOR_PORT = os.environ.get("FLOW_COLLECTOR", "flow-collector:2055").rsplit(":", 1)
PANEL_PORT = int(os.environ.get("PANEL_PORT", "8090"))

MBPS = 1_000_000
MIN_ATTACKABLE_BPS = 2 * MBPS  # Xiguard ignores IPs whose baseline is under its 1 Mbps floor

# NetFlow v9 layout read by backend/app/services/netflow.py.
SOURCE_ID = 0x5843  # differs from the CHR's own exporter, so templates never collide
TEMPLATE_ID = 300
#          IN_BYTES IN_PKTS PROTOCOL L4_SRC_PORT IPV4_SRC L4_DST_PORT IPV4_DST
FIELDS = [(1, 4), (2, 4), (4, 1), (7, 2), (8, 4), (11, 2), (12, 4)]
RECORD = struct.Struct("!IIBH4sH4s")
RECORDS_PER_PACKET = 60
U32 = 0xFFFFFFFF

# Named hosts at fixed offsets in the first prefix: the ones to attack on stage.
FEATURED = [
    (10, "web-01", 45 * MBPS, 443),
    (11, "game-01", 180 * MBPS, 27015),
    (12, "api-01", 22 * MBPS, 443),
    (13, "cdn-01", 320 * MBPS, 443),
    (14, "mail-01", 6 * MBPS, 25),
    (15, "vps-01", 12 * MBPS, 22),
]

#              protocol, src port (0 = random), dst port (0 = random), avg packet bytes
VECTORS = {
    "dns-amp": (17, 53, 0, 1200, "UDP DNS amplification"),
    "ntp-amp": (17, 123, 0, 468, "UDP NTP amplification"),
    "syn": (6, 0, 443, 60, "TCP SYN flood"),
}

ATTACKS: dict[str, dict] = {}
LOCK = threading.Lock()
STARTED = time.time()


def log(msg: str) -> None:
    print(f"[simulator] {msg}", flush=True)


def _public_ips(seed: int, n: int) -> list[bytes]:
    rnd = random.Random(seed)
    out: list[bytes] = []
    while len(out) < n:
        ip = ipaddress.ip_address(rnd.randint(0x01000000, 0xDFFFFFFF))
        if ip.is_global and not any(ip in p for p in PREFIXES):
            out.append(ip.packed)
    return out


CLIENTS = _public_ips(1, 64)  # a fixed client pool keeps collector key churn low


def build_hosts() -> dict[str, dict]:
    """Deterministic per-IP traffic profiles: the same IPs are busy on every run."""
    hosts: dict[str, dict] = {}
    for net in PREFIXES:
        for addr in net.hosts():
            rnd = random.Random(int(addr))
            roll = rnd.random()
            if roll < 0.15:
                continue  # unused address: no traffic at all
            if roll < 0.65:
                rate = rnd.uniform(0.1, 0.9) * MBPS
            elif roll < 0.92:
                rate = rnd.uniform(1.5, 25) * MBPS
            else:
                rate = rnd.uniform(30, 150) * MBPS
            hosts[str(addr)] = {
                "name": "", "rate": rate, "port": rnd.choice([443, 80, 53, 22, 25565]),
                "phase": rnd.uniform(0, 2 * math.pi), "reply": rnd.uniform(0.4, 3.0),
            }
    first = PREFIXES[0]
    for offset, name, rate, port in FEATURED:
        addr = first.network_address + offset
        if addr in first:
            hosts[str(addr)] = {"name": name, "rate": rate, "port": port, "phase": 0.0, "reply": 2.0}
    for ip, h in hosts.items():
        h["packed"] = ipaddress.ip_address(ip).packed
    return hosts


def normal_records(hosts: dict[str, dict], now: float) -> list[tuple]:
    """One second of ordinary traffic: slow 5-minute swell plus ±10 % jitter (always < 2× baseline)."""
    recs = []
    for h in hosts.values():
        bps = h["rate"] * (1 + 0.15 * math.sin(2 * math.pi * now / 300 + h["phase"])) * random.uniform(0.9, 1.1)
        nbytes = int(bps / 8)
        client = random.choice(CLIENTS)
        sport = random.randint(1024, 65535)
        recs.append((min(nbytes, U32), max(1, nbytes // 900), 6, sport, client, h["port"], h["packed"]))
        rbytes = int(nbytes * h["reply"])
        recs.append((min(rbytes, U32), max(1, rbytes // 1200), 6, h["port"], h["packed"], sport, client))
    return recs


def attack_records(now: float) -> list[tuple]:
    recs = []
    with LOCK:
        for ip in [ip for ip, a in ATTACKS.items() if a["until"] <= now]:
            log(f"attack on {ip} finished")
            del ATTACKS[ip]
        for a in ATTACKS.values():
            proto, sport, dport, size, _ = VECTORS[a["vector"]]
            per_bot = int(a["bps"] / 8 / len(a["bots"]))
            for bot in a["bots"]:
                nbytes = int(per_bot * random.uniform(0.8, 1.2))
                recs.append((
                    min(nbytes, U32), min(max(1, nbytes // size), U32), proto,
                    sport or random.randint(1024, 65535), bot,
                    dport or random.randint(1024, 65535), a["packed"],
                ))
    return recs


def start_attack(hosts: dict[str, dict], ip: str, gbps: float, seconds: int, vector: str) -> dict:
    if ip not in hosts:
        raise ValueError(f"{ip} is not an active host on the showcase prefixes")
    if hosts[ip]["rate"] < MIN_ATTACKABLE_BPS:
        raise ValueError(
            f"{ip} normally carries under 2 Mbps. Xiguard deliberately ignores near-idle IPs "
            "(1 Mbps baseline floor), so this attack would not be blackholed. Pick a listed host."
        )
    if vector not in VECTORS or not 0.05 <= gbps <= 400 or not 5 <= seconds <= 900:
        raise ValueError("vector must be dns-amp|ntp-amp|syn, size 0.05–400 Gbps, duration 5–900 s")
    attack = {
        "ip": ip, "bps": gbps * 1e9, "vector": vector, "until": time.time() + seconds,
        "packed": hosts[ip]["packed"], "bots": _public_ips(int(ipaddress.ip_address(ip)), 32),
    }
    with LOCK:
        ATTACKS[ip] = attack
    log(f"attack started: {gbps:g} Gbps {VECTORS[vector][4]} on {ip} for {seconds}s")
    return attack


def stop_attacks(ip: str | None = None) -> None:
    with LOCK:
        for key in [k for k in ATTACKS if ip in (None, k)]:
            del ATTACKS[key]
    log(f"attack stopped: {ip or 'all'}")


def encode_packets(records: list[tuple], seq: int, uptime_ms: int) -> list[bytes]:
    template = struct.pack("!HH", TEMPLATE_ID, len(FIELDS)) + b"".join(struct.pack("!HH", t, n) for t, n in FIELDS)
    template_fs = struct.pack("!HH", 0, 4 + len(template)) + template
    packets = []
    for i in range(0, len(records), RECORDS_PER_PACKET):
        chunk = records[i:i + RECORDS_PER_PACKET]
        data = b"".join(RECORD.pack(*r) for r in chunk)
        pad = (-len(data)) % 4
        data_fs = struct.pack("!HH", TEMPLATE_ID, 4 + len(data) + pad) + data + b"\0" * pad
        header = struct.pack("!HHIIII", 9, len(chunk) + 1, uptime_ms & U32, int(time.time()), seq & U32, SOURCE_ID)
        packets.append(header + template_fs + data_fs)
        seq += 1
    return packets


# ── control panel ────────────────────────────────────────────────────────────
PANEL_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Xiguard showcase · attack panel</title>
<style>
:root{--bg:#0b1622;--card:#122133;--line:#24364d;--text:#e8edf4;--muted:#8fa2ba;--red:#e5452b;--green:#23895c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:28px 18px}h1{margin:0 0 4px;font-size:24px}p.sub{margin:0 0 22px;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:18px}
.row{display:flex;flex-wrap:wrap;gap:14px;align-items:end}label{font-size:12px;color:var(--muted);display:block;margin-bottom:4px;text-transform:uppercase;letter-spacing:.06em}
select,input{background:#0b1622;color:var(--text);border:1px solid var(--line);border-radius:6px;padding:7px 9px;font:inherit}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
code{font-family:ui-monospace,Consolas,monospace}button{border:0;border-radius:6px;padding:8px 14px;font:600 14px system-ui,sans-serif;cursor:pointer}
.fire{background:var(--red);color:#fff}.stop{background:#2a3b52;color:var(--text)}.ok{color:var(--green)}.err{color:var(--red);min-height:1.5em;margin:8px 0 0}
.live{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--red);margin-right:8px;animation:p 1s infinite}@keyframes p{50%{opacity:.25}}
</style></head><body><main>
<h1>Attack control panel</h1>
<p class="sub">Simulated DDoS traffic for the Xiguard showcase. Nothing leaves this laptop. <span id="meta"></span></p>
<div class="card"><div class="row">
 <div><label for="size">Attack size</label><select id="size"><option value="0.5">0.5 Gbps</option><option value="2.4" selected>2.4 Gbps</option><option value="10">10 Gbps</option><option value="40">40 Gbps</option></select></div>
 <div><label for="dur">Duration</label><select id="dur"><option value="30">30 s</option><option value="60" selected>60 s</option><option value="120">2 min</option></select></div>
 <div><label for="vec">Attack type</label><select id="vec"><option value="dns-amp">UDP DNS amplification</option><option value="ntp-amp">UDP NTP amplification</option><option value="syn">TCP SYN flood</option></select></div>
 <div><label for="custom">Other IP (optional)</label><input id="custom" placeholder="e.g. 203.0.113.40" size="16"></div>
 <div><button class="fire" onclick="fire(document.getElementById('custom').value.trim())">Attack this IP</button></div>
</div><p class="err" id="err"></p></div>
<div class="card"><table><thead><tr><th>Host</th><th>IP address</th><th>Normal traffic</th><th></th></tr></thead><tbody id="hosts"></tbody></table></div>
<div class="card"><div class="row" style="justify-content:space-between;align-items:center"><strong>Active attacks</strong><button class="stop" onclick="stop()">Stop all</button></div>
<table><tbody id="attacks"></tbody></table></div>
</main><script>
const $=id=>document.getElementById(id);
async function post(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});const j=await r.json();$('err').textContent=r.ok?'':j.error;refresh()}
function fire(ip){if(!ip){$('err').textContent='Type an IP, or use a button in the table below.';return}post('/api/attack',{ip,gbps:+$('size').value,seconds:+$('dur').value,vector:$('vec').value})}
function stop(ip){post('/api/stop',ip?{ip}:{})}
async function refresh(){try{const s=await(await fetch('/api/state')).json();
$('meta').textContent=`Exporting ${s.hosts} hosts on ${s.prefixes.join(', ')} · flows sent: ${s.packets_sent}`;
$('hosts').innerHTML=s.featured.map(h=>`<tr><td><strong>${h.name}</strong></td><td><code>${h.ip}</code></td><td>${h.mbps} Mbps</td><td><button class="fire" onclick="fire('${h.ip}')">Attack</button></td></tr>`).join('');
$('attacks').innerHTML=s.attacks.length?s.attacks.map(a=>`<tr><td><span class="live"></span><code>${a.ip}</code></td><td>${a.gbps} Gbps · ${a.vector}</td><td>${a.left}s left</td><td><button class="stop" onclick="stop('${a.ip}')">Stop</button></td></tr>`).join(''):'<tr><td class="ok">No attack running.</td></tr>'}catch(e){$('meta').textContent='(panel lost contact with the simulator)'}}
refresh();setInterval(refresh,1000);
</script></body></html>"""

STATS = {"packets_sent": 0}


def make_handler(hosts: dict[str, dict]):
    class Panel(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict) -> None:
            self._send(code, json.dumps(obj).encode())

        def do_GET(self) -> None:
            if self.path == "/api/state":
                now = time.time()
                with LOCK:
                    attacks = [
                        {"ip": a["ip"], "gbps": round(a["bps"] / 1e9, 2), "vector": VECTORS[a["vector"]][4],
                         "left": max(0, int(a["until"] - now))}
                        for a in ATTACKS.values()
                    ]
                featured = [
                    {"name": h["name"] or "host", "ip": ip, "mbps": round(h["rate"] / MBPS)}
                    for ip, h in hosts.items() if h["name"]
                ]
                self._json(200, {
                    "prefixes": [str(p) for p in PREFIXES], "hosts": len(hosts), "featured": featured,
                    "attacks": attacks, "packets_sent": STATS["packets_sent"], "uptime_sec": int(now - STARTED),
                })
            elif self.path in ("/", "/index.html"):
                self._send(200, PANEL_HTML.encode(), "text/html; charset=utf-8")
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if self.path == "/api/attack":
                    a = start_attack(hosts, str(body.get("ip", "")), float(body.get("gbps", 2.4)),
                                     int(body.get("seconds", 60)), str(body.get("vector", "dns-amp")))
                    self._json(200, {"ok": True, "ip": a["ip"]})
                elif self.path == "/api/stop":
                    stop_attacks(body.get("ip"))
                    self._json(200, {"ok": True})
                else:
                    self._json(404, {"error": "not found"})
            except (ValueError, TypeError) as e:
                self._json(400, {"error": str(e)})

        def log_message(self, *args) -> None:  # keep container logs readable
            pass

    return Panel


def main() -> None:
    hosts = build_hosts()
    busy = sum(1 for h in hosts.values() if h["rate"] >= MIN_ATTACKABLE_BPS)
    log(f"{len(hosts)} active hosts ({busy} attackable) on {', '.join(map(str, PREFIXES))}")
    server = ThreadingHTTPServer(("0.0.0.0", PANEL_PORT), make_handler(hosts))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"attack panel listening on :{PANEL_PORT}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    started = time.monotonic()
    seq, addr, resolved_at, next_tick, last_report = 0, None, 0.0, started, started
    while True:
        if addr is None or time.monotonic() - resolved_at > 30:
            try:
                addr = (socket.gethostbyname(COLLECTOR_HOST), int(COLLECTOR_PORT))
                resolved_at = time.monotonic()
            except OSError:
                addr = None
                if time.monotonic() - last_report > 10:
                    log(f"waiting for flow collector '{COLLECTOR_HOST}' to come up")
                    last_report = time.monotonic()
        if addr:
            now = time.time()
            packets = encode_packets(normal_records(hosts, now) + attack_records(now), seq,
                                     int((time.monotonic() - started) * 1000))
            try:
                for p in packets:
                    sock.sendto(p, addr)
                seq += len(packets)
                STATS["packets_sent"] += len(packets)
            except OSError as e:
                log(f"send to {addr} failed: {e}")
                addr = None
            if time.monotonic() - last_report > 60:
                log(f"exporting to {addr[0] if addr else '?'}:{COLLECTOR_PORT}, {STATS['packets_sent']} packets so far")
                last_report = time.monotonic()
        next_tick += 1.0
        delay = next_tick - time.monotonic()
        if delay < 0:  # fell behind (e.g. laptop slept): resync instead of bursting
            next_tick, delay = time.monotonic(), 0
        time.sleep(delay)


def selftest() -> None:
    """Round-trips simulator packets through a copy of Xiguard's NetFlow parser logic."""
    hosts = build_hosts()
    victim = next(ip for ip, h in hosts.items() if h["name"] == "game-01")
    start_attack(hosts, victim, 2.4, 60, "dns-amp")
    recs = normal_records(hosts, time.time()) + attack_records(time.time())
    total_in: dict[str, int] = {}
    for pkt in encode_packets(recs, 0, 0):
        version, count = struct.unpack("!HH", pkt[:4])
        assert version == 9 and count >= 2
        off, layout = 20, None
        while off + 4 <= len(pkt):
            fs_id, fs_len = struct.unpack("!HH", pkt[off:off + 4])
            body = pkt[off + 4:off + fs_len]
            if fs_id == 0:
                tid, n = struct.unpack("!HH", body[:4])
                layout = [struct.unpack("!HH", body[4 + 4 * i:8 + 4 * i]) for i in range(n)]
                assert tid == TEMPLATE_ID and layout == FIELDS
            else:
                assert fs_id == TEMPLATE_ID and layout
                for i in range(0, len(body) - RECORD.size + 1, RECORD.size):
                    b, _, _, _, _, _, dst = RECORD.unpack(body[i:i + RECORD.size])
                    key = socket.inet_ntoa(dst)
                    total_in[key] = total_in.get(key, 0) + b
            off += fs_len
    gbps = total_in[victim] * 8 / 1e9
    assert 2.2 < gbps < 2.8, gbps
    try:
        start_attack(hosts, next(ip for ip, h in hosts.items() if h["rate"] < MIN_ATTACKABLE_BPS), 1, 30, "syn")
        raise AssertionError("idle host should be rejected")
    except ValueError:
        pass
    print(f"selftest ok: {len(hosts)} hosts, victim {victim} receives {gbps:.2f} Gbps")


if __name__ == "__main__":
    selftest() if sys.argv[1:] == ["selftest"] else main()
