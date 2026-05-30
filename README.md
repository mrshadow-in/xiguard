# CHRGuard

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
4. The dashboard updates live as the 5-second polling cycle samples
   `/ip/accounting/snapshot` on every online CHR.

---

## Prerequisite — RouterOS accounting

On each MikroTik CHR, enable IP accounting once (CHRGuard reads
snapshots via the API — no web-access required):

```
/ip accounting set enabled=yes threshold=4096
```

---

## Architecture at a glance

```
Caddy ── /api/* ─► FastAPI ─► PostgreSQL 16 (partitioned traffic_samples)
       └─ /     ─► Next.js
                  ▲
                  │ WebSocket fanout from Redis pub/sub
                  │
Celery Beat ──► Celery worker (default + critical queues)
                  ├ poll_all_chrs           every 5s
                  ├ check_blackhole_expiry  every 30s
                  ├ health_check_chrs       every 60s
                  ├ ensure_partitions       daily 00:05 UTC
                  └ cleanup_old_data        daily 03:00 UTC
                  ▲
                  │ RouterOS API (librouteros)
                  ▼
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
