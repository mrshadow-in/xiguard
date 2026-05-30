# Xiguard — Ubuntu 22.04 Deployment Guide

Production install on a single Ubuntu 22.04 LTS host using Docker Compose.

Audience: someone with root on a fresh VPS, comfortable with the Linux
shell. Estimated time: ~20 minutes.

---

## 1. Prerequisites

| Item | Recommended |
|---|---|
| OS | Ubuntu 22.04 LTS (Server) |
| vCPU | 4 (8 for 5,000+ IPs) |
| RAM | 8 GB (16 GB for 5,000+ IPs) |
| Disk | 100 GB NVMe (≈ 50 GB used at 5,000 IPs × 30-day retention) |
| Network | Reachable on TCP 80/443 from your operators; TCP 8728/8729 to each MikroTik CHR; TCP 587/465 outbound to SMTP; **UDP 2055 inbound from each CHR (NetFlow v9)** |
| DNS | An A/AAAA record pointing to this host (for TLS via Let's Encrypt) |

### 1.0 Xiguard must survive the attack it's trying to mitigate

The single most common operational failure: an actual DDoS hits, the
upstream Xiguard shares with the target gets saturated, Xiguard's API
calls to the CHR time out, the polling cycle stalls, and the blackhole
never lands. Software hardening can't fix a saturated uplink.

Mandatory:

- **Out-of-band network** — Xiguard's host MUST sit on a separate
  upstream from the IP pools it's protecting, OR on a management VLAN
  / loopback the attack traffic doesn't traverse. NetFlow export from
  the CHR to Xiguard's UDP 2055 should ride the same out-of-band link.
- **Dedicated CPU + RAM** — a `t3.medium` /4 GB VPS shared with
  unrelated workloads will choke at 1 Gbps+ flow rates. 8 vCPU / 16 GB
  with no neighbors is the practical baseline.
- **`sysctl` UDP tuning** — without this the kernel drops NetFlow
  packets long before the collector sees them:

  ```bash
  cat >> /etc/sysctl.d/99-xiguard.conf <<EOF
  net.core.rmem_max = 33554432
  net.core.rmem_default = 16777216
  net.core.netdev_max_backlog = 5000
  EOF
  sysctl --system
  ```

The collector requests `SO_RCVBUF = 16 MiB` on startup but the kernel
clamps to `net.core.rmem_max` if that's smaller. Check the actual
buffer size in `docker compose logs flow-collector` — the startup line
prints it.

In the application itself, the polling cycle does the **detection
only** and dispatches the actual blackhole push to a dedicated Celery
`critical` queue worker. So even if RouterOS API or SMTP slows down
under attack load, the polling loop keeps running and other IPs keep
being evaluated. Verify the critical worker is up: `docker compose ps
worker` — its command line includes `-Q default,critical`.

---

### 1.1 Network model — public-IP addressing

In this deployment the Xiguard host and every MikroTik CHR have their
own public IPv4 addresses. Even though they may sit in the same
datacenter, **all addressing between Xiguard ↔ CHR is by public IP**:

- The CHR sends NetFlow records to **Xiguard's public IP** on UDP 2055.
- Xiguard reaches each CHR's **public IP** on TCP 8728 (or 8729 for SSL)
  for the RouterOS API.

Two consequences flow from that, and the rest of this guide assumes
them:

1. **Lock both sides down by source IP.** UDP 2055 on the Xiguard host
   and the RouterOS API on each CHR must be restricted to the other
   side's public IP only — otherwise you're publishing a NetFlow
   collector and a RouterOS management API to the internet.
2. **No private/internal IPs anywhere in the config.** All examples
   below use placeholders — substitute the *public* addresses:

   | Placeholder | What it is |
   |---|---|
   | `203.0.113.10` | Xiguard host **public IP** |
   | `198.51.100.21`, `198.51.100.22` | CHR #1, CHR #2 **public IPs** |

> Xiguard is still a **management-plane** application — the web UI
> should not be left wide-open. Either keep it behind WireGuard /
> Tailscale / an SSO reverse proxy, or at minimum restrict TCP 443 to
> operator source IPs. The Caddy site in §6 terminates TLS for you, but
> TLS alone is not authentication.

---

## 2. Initial system hardening (optional but recommended)

```bash
# Become root
sudo -i

# Up-to-date base
apt update && apt -y upgrade

# A few QoL packages
apt -y install ufw fail2ban unattended-upgrades curl git ca-certificates \
               gnupg lsb-release htop tmux

# Automatic security updates
dpkg-reconfigure -plow unattended-upgrades

# Firewall — open only what we need. Public-IP deployment, so we
# whitelist every source explicitly.
ufw default deny incoming
ufw default allow outgoing

ufw allow 22/tcp                    # SSH — better: restrict to your jumphost IP
ufw allow 80/tcp                    # ACME HTTP-01 challenge (Caddy needs it on first run)
ufw allow 443/tcp                   # HTTPS web UI — see note below

# NetFlow v9 from each CHR's public IP. Repeat for every CHR you'll add.
ufw allow from 198.51.100.21 to any port 2055 proto udp comment 'CHR #1 netflow'
ufw allow from 198.51.100.22 to any port 2055 proto udp comment 'CHR #2 netflow'

# (Recommended) Restrict the web UI to your operator subnets too —
# pick whichever fits your environment:
# ufw allow from 203.0.113.0/24 to any port 443 proto tcp comment 'NOC office'
# (then remove the broad `ufw allow 443/tcp` above)

ufw enable
ufw status verbose

# Create a non-root deploy user (skip if you already have one)
adduser --disabled-password --gecos "" xiguard
usermod -aG sudo xiguard
mkdir -p /home/xiguard/.ssh
cp ~/.ssh/authorized_keys /home/xiguard/.ssh/
chown -R xiguard:xiguard /home/xiguard/.ssh
chmod 700 /home/xiguard/.ssh
chmod 600 /home/xiguard/.ssh/authorized_keys
```

From here on, log in as `xiguard`.

---

## 3. Install Docker Engine + Compose plugin

Using Docker's official `apt` repo (the Ubuntu-shipped `docker.io` is
older and ships Compose v1 only):

```bash
# Add Docker's GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt -y install docker-ce docker-ce-cli containerd.io \
                    docker-buildx-plugin docker-compose-plugin

# Run docker without sudo (re-login required after this)
sudo usermod -aG docker $USER
newgrp docker

# Sanity check
docker version
docker compose version
```

---

## 4. Clone the repo

```bash
sudo mkdir -p /opt/xiguard
sudo chown $USER:$USER /opt/xiguard
cd /opt
git clone <your-git-url> xiguard
cd xiguard
```

If you're pulling from a private repo, set up a deploy key first:

```bash
ssh-keygen -t ed25519 -C "xiguard-deploy@$(hostname)" -f ~/.ssh/xiguard_deploy -N ""
cat ~/.ssh/xiguard_deploy.pub
# → add as a deploy key on the repo, then:
cat >> ~/.ssh/config <<EOF
Host github-xiguard
  HostName github.com
  User git
  IdentityFile ~/.ssh/xiguard_deploy
  IdentitiesOnly yes
EOF
git clone git@github-xiguard:OWNER/REPO.git xiguard
```

---

## 5. Configure `.env`

```bash
cp .env.example .env

# Generate the two secrets
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
ENCRYPTION_KEY=$(python3 -c 'import base64,os; print(base64.b64encode(os.urandom(32)).decode())')
ADMIN_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')

# Patch them in
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|"             .env
sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${ENCRYPTION_KEY}|" .env
sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PASSWORD}|" .env

echo "Initial admin password: ${ADMIN_PASSWORD}"
```

**Now edit `.env`** by hand and set, at minimum:

| Variable | Why |
|---|---|
| `POSTGRES_PASSWORD` | Pick a strong random value |
| `DATABASE_URL`, `DATABASE_SYNC_URL` | Update the password segment to match |
| `CORS_ORIGINS` | Set to `https://xiguard.example.com` (your real hostname) |
| `ORG_NAME`, `ORG_AS_NUMBER`, `ORG_NOC_EMAIL`, `ORG_NOC_PHONE`, `ORG_WEBSITE` | Stamped into the ISP NOC alert emails |

Lock the file down:

```bash
chmod 600 .env
```

> **Back up `ENCRYPTION_KEY` somewhere safe** (password manager, secret
> vault). If you lose it, every stored CHR/SMTP password becomes
> unrecoverable and you'll have to re-enter them all.

---

## 6. Replace the bundled Caddyfile with a real-hostname one

The repo ships a development `Caddyfile` that listens on `:80` with
auto-HTTPS disabled. For production, swap it for the version below
which terminates TLS via Let's Encrypt.

```bash
cat > Caddyfile <<'EOF'
{
    email ops@example.com
}

xiguard.example.com {
    encode gzip zstd

    @ws path /api/ws
    reverse_proxy @ws api:8000

    handle /api/* {
        reverse_proxy api:8000
    }

    handle {
        reverse_proxy frontend:3000
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        X-Frame-Options "DENY"
    }
}
EOF
```

Replace `xiguard.example.com` and `ops@example.com` with your actual
hostname and contact email.

Set the cookie to `secure=True` for HTTPS — open
`backend/app/api/auth.py` and change `secure=False` to `secure=True`
in the `response.set_cookie(...)` call.

---

## 7. First boot

```bash
docker compose pull
docker compose build
docker compose up -d
```

Watch the logs until you see `Application startup complete` in the
`api` service and `celery beat: ... Starting` in `beat`:

```bash
docker compose logs -f api beat worker
```

(Hit `Ctrl-C` once it's settled.)

Database migrations run automatically on `api` startup. Verify:

```bash
docker compose exec api alembic current
# → 0001_initial (head)
```

Open `https://xiguard.example.com/`, sign in with the admin password
you generated in step 5, then immediately change it in the UI.

---

## 8. Prepare each MikroTik CHR

On every CHR you'll point Xiguard at, run the snippet below. **All
addressing is by public IP** — see §1.1. Substitute:

- `203.0.113.10` → Xiguard host **public IP**
- `Stark321!` → a long random password for the `xiguard` API user

```routeros
# ── 1. Traffic Flow export → Xiguard's flow-collector (public IP) ─────
/ip traffic-flow set enabled=yes interfaces=all
/ip traffic-flow set cache-entries=64k \
                    active-flow-timeout=00:00:05 \
                    inactive-flow-timeout=00:00:05
/ip traffic-flow target add dst-address=203.0.113.10 port=2055 version=9

# ── 2. Dedicated least-privilege API user for the control plane ──────
# (used by Xiguard for blackhole push/remove and health checks)
/user group add name=xiguard \
    policy=api,read,write,!ftp,!local,!telnet,!ssh,!winbox,!web,!sniff,!sensitive,!policy,!test,!password,!reboot,!romon,!dude,!tikapp
/user add name=xiguard group=xiguard password="Stark321!"

# ── 3. Lock the RouterOS API down to Xiguard's public IP only ────────
# Without this the API listens on every interface — never leave it open.
/ip service set api address=203.0.113.10/32
# If you'll use SSL (port 8729) instead:
/ip service set api-ssl address=203.0.113.10/32
# Optionally disable whichever you're NOT using:
# /ip service disable api      # if going SSL-only
# /ip service disable api-ssl  # if going plain-only

# ── 4. (Recommended) firewall the API source at the input chain too ──
# Belt + braces in case /ip service ACLs are ever loosened. We place
# both rules at the TOP so they evaluate before any existing
# default-accept (or default-drop) rules you already have.
/ip firewall filter add chain=input action=accept protocol=tcp \
    dst-port=8728,8729 src-address=203.0.113.10 \
    place-before=0 comment="Xiguard RouterOS API"
/ip firewall filter add chain=input action=drop protocol=tcp \
    dst-port=8728,8729 \
    place-before=1 comment="Drop other RouterOS API attempts"
```

> **Why the 5-second flow timeouts?** RouterOS only emits a flow when it
> hits the cache size limit OR one of the timeouts. With the defaults
> (active 30m / inactive 15s) a steady-state DDoS would take up to 15
> seconds to surface its first flow record, defeating the 30-second
> detection target. The 5-second timeouts above align flow emission
> with Xiguard's polling cadence.

Verify on the CHR:
```routeros
/ip traffic-flow print
/ip traffic-flow target print
/ip service print where name~"api"
/ip firewall filter print where comment~"Xiguard"
```

You should see `traffic-flow` enabled with a target at `203.0.113.10:2055`,
the `api`/`api-ssl` service's `address=203.0.113.10/32`, and your two
filter rules at the top of the input chain.

Then in the Xiguard UI: **CHR Nodes → Add Node** → fill in:

| Field | Value |
|---|---|
| Host | the CHR's **public IP** (e.g. `198.51.100.21`) |
| API Port | `8728` (plain) or `8729` with **Use SSL** ticked |
| Username | `xiguard` |
| Password | the one from step 2 above |

→ **Test Connection** should report RouterOS version + uptime within a
second. If it times out, double-check that:

1. UDP/TCP egress from Xiguard's host isn't itself firewalled (cloud
   security groups often deny by default).
2. The CHR's `/ip service` address ACL has the *exact* Xiguard public
   IP — not a netblock, unless you spelled out the mask.
3. The CHR's input filter rules above were placed at the TOP (use
   `print` to check ordering; reorder with `move`).

---

## 9. Configure mail and add a pool

1. **Settings → Mail → Hosting NOC**: fill in SMTP host/port, From,
   recipients. Send a test email — it should arrive prefixed `[TEST]`.
2. **Settings → Mail → ISP NOC**: same, with your upstream's NOC inbox.
3. **IP Pools → Add Pool**: pick the CHR you added in step 8, enter a
   CIDR (e.g. `162.141.0.0/24`), set the multiplier and auto-blackhole
   policy. Pool member IPs are auto-expanded.

Within 30 seconds you should see traffic samples flowing on the
**Dashboard**.

---

## 10. Routine ops

```bash
cd /opt/xiguard

# Status
docker compose ps

# Logs
docker compose logs -f api worker beat

# Restart one service
docker compose restart api

# Update to a new commit
git pull
docker compose pull
docker compose up -d --build       # rebuilds api / frontend if needed
docker compose exec api alembic upgrade head

# Run tests
docker compose exec api pytest -q

# Open a Python shell with the app context
docker compose exec api python

# Postgres shell
docker compose exec postgres psql -U xiguard -d xiguard

# Redis CLI
docker compose exec redis redis-cli
```

### Manual migration / rollback

```bash
docker compose exec api alembic upgrade head
docker compose exec api alembic downgrade -1
docker compose exec api alembic history
```

### Inspecting Celery

```bash
docker compose exec worker celery -A app.tasks.celery_app.celery_app inspect active
docker compose exec worker celery -A app.tasks.celery_app.celery_app inspect scheduled
docker compose exec worker celery -A app.tasks.celery_app.celery_app inspect stats
```

---

## 11. Backups

Two things matter for restore: **PostgreSQL** and **the `ENCRYPTION_KEY`**.
Without the key, the encrypted CHR/SMTP credentials in PostgreSQL are
useless.

### Nightly DB dump

```bash
sudo mkdir -p /var/backups/xiguard
sudo chown $USER:$USER /var/backups/xiguard

cat > ~/xiguard-backup.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/xiguard
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT=/var/backups/xiguard/xiguard-${TS}.sql.gz
docker compose exec -T postgres pg_dump -U xiguard -d xiguard \
  | gzip -9 > "$OUT"
# keep 14 days
find /var/backups/xiguard -name 'xiguard-*.sql.gz' -mtime +14 -delete
echo "wrote $OUT"
EOF
chmod +x ~/xiguard-backup.sh

# Cron — daily at 02:30 UTC
( crontab -l 2>/dev/null; echo "30 2 * * * /home/$USER/xiguard-backup.sh >> /var/log/xiguard-backup.log 2>&1" ) | crontab -
```

Ship the dump and a copy of `.env` to off-box storage (S3, B2, an
encrypted external host). The `.env` carries the `ENCRYPTION_KEY` —
treat it like a private SSH key.

### Restore

```bash
# Stop everything
docker compose down

# Volumes will be re-created on `up`. To wipe an existing DB:
docker volume rm xiguard_pg_data

docker compose up -d postgres
sleep 5
gunzip -c /var/backups/xiguard/xiguard-YYYYMMDD....sql.gz \
  | docker compose exec -T postgres psql -U xiguard -d xiguard

docker compose up -d
```

---

## 12. Monitoring this stack (light-touch)

Xiguard exposes `GET /api/health` returning `{"status":"ok"}`. Point
Uptime Kuma / Healthchecks.io / your existing monitor at:

| Check | URL / command |
|---|---|
| Web up | `https://xiguard.example.com/api/health` |
| Polling fresh | `docker compose exec -T postgres psql -U xiguard -d xiguard -tAc "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(last_seen_at))) FROM chr_nodes;"` — alert if > 30 |
| Disk free | standard node-level check; the DB grows ≈ 1.5 GB/day at 5,000 IPs |
| Cert renewal | Caddy handles this; alert on the container restarting unexpectedly |

---

## 13. Common pitfalls

| Symptom | Cause / fix |
|---|---|
| `api` exits with `RuntimeError: ENCRYPTION_KEY env var is not set` | You skipped step 5; populate `.env` and `docker compose up -d` again |
| `Test Connection` on a CHR returns timeout but ping works | `/ip service` `address=` ACL doesn't include Xiguard's **public** IP, or step 8.4 firewall rule was placed below an existing default-drop. Re-run `print` on both. |
| Dashboard says CHR `online` but no traffic samples | Almost always NetFlow not reaching Xiguard. On the CHR: `/ip traffic-flow target print` shows status. On Xiguard: `docker compose logs flow-collector` should mention "listening on UDP 2055"; `docker compose exec redis redis-cli --scan --pattern 'xiguard:flow:*' \| head` should return keys within ~10s. If no keys, check the host firewall (`ufw status`) lists the CHR's public IP for 2055/udp. |
| Test emails arrive but real alerts don't | The IP must be in a pool, the pool's CHR must be `online`, and traffic must exceed `baseline × multiplier` for `eval_window_sec`. Until `sample_count ≥ baseline_ewma_span` (~1 hour at 5 s) the warm-up is conservative |
| Dashboard shows `Reconnecting` | Caddy needs the `/api/ws` matcher (see step 6). Confirm with `curl -i https://xiguard.example.com/api/health` — should be `200` |
| `worker` log spam: `MaxRetriesExceededError` on blackhole push | Check the CHR's API user has `write` policy, and that the route doesn't already exist with a different comment |
| Postgres OOMs after a few days | Either bump RAM or shrink `TRAFFIC_RETENTION_DAYS` and re-run `ensure_partitions` manually: `docker compose exec api python -c "from app.tasks.cleanup import _ensure_partitions; import asyncio; print(asyncio.run(_ensure_partitions()))"` |

---

## 14. Uninstall

```bash
cd /opt/xiguard
docker compose down -v       # removes containers + volumes (DESTRUCTIVE)
cd ..
sudo rm -rf /opt/xiguard
```
