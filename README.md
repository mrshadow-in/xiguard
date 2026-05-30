# Xiguard

Internal NOC-grade web panel for multi-MikroTik CHR DDoS monitoring with
EWMA-baselined per-IP spike detection, automatic RTBH (blackhole)
mitigation, and dual-target email alerts (Hosting NOC + upstream ISP NOC).

See `system-design.md`, `architecture.md`, `design.md`, and `wireframe.md`
for the full specification.

---

## Quick start

```bash
cp .env.example .env

# Generate the two secrets (run in two separate Python one-liners):
python -c "import secrets; print(secrets.token_hex(32))"   # → SECRET_KEY
python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"  # → ENCRYPTION_KEY

# Edit .env with the two values above and any org metadata you want.

docker compose up -d --build
```

The first start auto-creates the admin user (`ADMIN_USERNAME` /
`ADMIN_PASSWORD` from `.env`) and inserts empty rows for the Hosting NOC
and ISP NOC mail configs.

Open `http://localhost/` and sign in. Steps:

1. **CHR Nodes** → Add your first MikroTik CHR (host, API port 8728 or
   8729 SSL, RouterOS username/password).
2. **IP Pools** → Add a CIDR (e.g. `162.141.0.0/24`) bound to that CHR.
   The pool's host IPs are auto-expanded into monitored entries.
3. **Settings → Mail** → Configure both NOC SMTP endpoints and send a
   test email to each.
4. The dashboard updates live as the 5-second polling cycle reads the
   NetFlow counters that each CHR is exporting to Xiguard.

---

## Prerequisite — RouterOS Traffic Flow (NetFlow v9)

Xiguard does **not** poll CHRs for per-IP traffic. Each CHR exports
NetFlow v9 records over UDP to Xiguard's `flow-collector` service. On
every CHR, run once (replace `10.0.0.50` with the Xiguard host):

```
/ip traffic-flow set enabled=yes interfaces=all
/ip traffic-flow set active-flow-timeout=00:00:05 inactive-flow-timeout=00:00:05
/ip traffic-flow target add dst-address=10.0.0.50 port=2055 version=9
```

The CHR API (8728/8729) is still used by Xiguard for blackhole route
push/remove and health checks, so the CHR user needs `api,read,write`.
See `DEPLOYMENT.md §8` for the full least-privilege user recipe.

> Why Traffic Flow instead of `/ip accounting`? `/ip accounting` was
> removed in RouterOS 7; Traffic Flow is the v7 replacement.

---

## Architecture at a glance

```
Caddy ── /api/* ─► FastAPI ─► PostgreSQL 16 (partitioned traffic_samples)
       └─ /     ─► Next.js
                  ▲
                  │ WebSocket fanout from Redis pub/sub
                  │
Celery Beat ──► Celery worker (default + critical queues)
                  ├ poll_all_chrs           every 5s   (per-IP read from Redis)
                  ├ check_blackhole_expiry  every 30s
                  ├ health_check_chrs       every 60s  (RouterOS API)
                  ├ ensure_partitions       daily 00:05 UTC
                  └ cleanup_old_data        daily 03:00 UTC

flow-collector  ◄── UDP 2055 NetFlow v9 ── CHR #1 … CHR #N
       │
       │ HINCRBY per-IP counters
       ▼
     Redis (xiguard:flow:<ip>)

      RouterOS API (8728/8729) ── blackhole push/remove + health probe
                                  CHR #1 … CHR #N
```

## Per-IP state machine

```
   ┌─ spike sustained for eval_window ─┐
   │                                   ▼
NORMAL ─► ALERT ─auto_blackhole─► BLACKHOLED ─duration expires─► RECOVERING ─clean for 60s─► NORMAL
   ▲                                                                    │
   └────────────────── spike during recovery ───────────────────────────┘
```

Baseline math: EWMA with α = 2 / (span + 1) and `span = 720` samples
(1 hour at 5 s polling). Warm-up uses simple moving average until
`sample_count ≥ span`. Baseline is **not** updated while an IP is in
the `BLACKHOLED` state — that traffic is by definition zero on our
observation path.

---

## Operations

```bash
# Tail logs
docker compose logs -f api worker beat

# Open a backend shell
docker compose exec api bash

# Run migrations manually (api also runs them on start)
docker compose exec api alembic upgrade head

# Run unit tests
docker compose exec api pytest -q
```

### Common things to tune (in `.env`)

| Var | Default | Effect |
|---|---|---|
| `DEFAULT_MULTIPLIER` | `3.0` | Per-pool default spike multiplier |
| `DEFAULT_EVAL_WINDOW_SEC` | `30` | Sustained-spike duration to alert |
| `DEFAULT_BLACKHOLE_DURATION_SEC` | `600` | Auto-unblackhole after this |
| `BASELINE_EWMA_SPAN` | `720` | EWMA window in samples |
| `ALERT_DEDUP_WINDOW_SEC` | `300` | No repeat alerts per IP for 5 min |
| `POLL_INTERVAL_SEC` | `5` | Celery Beat polling cadence |
| `ORG_AS_NUMBER` / `ORG_NOC_EMAIL` / `ORG_NOC_PHONE` / `ORG_WEBSITE` | — | Stamped into ISP NOC emails |

---

## Project layout

```
.
├── backend/
│   ├── app/
│   │   ├── api/        # FastAPI routers (auth, chr_nodes, ip_pools, monitoring, alerts, actions, mail_config, ws)
│   │   ├── models/     # SQLAlchemy ORM
│   │   ├── schemas/    # Pydantic
│   │   ├── services/   # crypto, chr_api, baseline, detector, mitigator, alerter, poller, pubsub
│   │   └── tasks/      # Celery (polling, recovery, cleanup, health)
│   ├── alembic/        # migrations (0001_initial.py creates partitioned traffic_samples)
│   └── tests/          # pytest unit tests
├── frontend/
│   ├── src/app/        # Next.js App Router pages
│   ├── src/components/ # Sidebar, AuthGuard, StatusBadge, AppShell
│   ├── src/hooks/      # useWebSocket
│   ├── src/stores/     # Zustand (trafficStore, alertStore)
│   └── src/lib/        # api fetch wrapper, ws envelope types, formatters
├── docker-compose.yml
├── Caddyfile
└── .env.example
```

---

## Security notes

- CHR and SMTP passwords are AES-256-GCM encrypted at rest with a fresh
  12-byte nonce per ciphertext. The key comes from `ENCRYPTION_KEY` —
  rotating it requires re-entering all stored credentials.
- Session tokens (`secrets.token_urlsafe(32)`) live in Redis with TTL
  `SESSION_TTL_SEC`. The cookie is `HttpOnly` and `SameSite=Lax`; set
  `secure=True` in `app/api/auth.py` once you are behind real TLS.
- The panel is designed to run on a management VLAN, not on the public
  internet. The Caddyfile in this repo serves HTTP on :80 for local
  testing; replace it with your real hostname + automatic HTTPS in
  production.
