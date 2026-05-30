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

> Xiguard is a **management-plane** application. Run it on a management
> VLAN. Do **not** expose the API/web UI directly to the public internet
> without an additional auth layer in front (e.g. WireGuard, Tailscale,
> SSO-protected reverse proxy).

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

# Firewall — open only what we need
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp        # SSH
ufw allow 80/tcp        # ACME HTTP-01 challenge
ufw allow 443/tcp       # HTTPS
ufw allow 2055/udp      # NetFlow v9 from your CHRs (lock down by source IP in prod)
ufw enable

# Restrict 2055/udp to only your CHR addresses (recommended)
# (repeat for each CHR; replace 10.0.0.1)
# ufw delete allow 2055/udp
# ufw allow from 10.0.0.1 to any port 2055 proto udp

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

On every CHR you'll point Xiguard at, run the following — replace
`10.0.0.50` with the Xiguard host's IP that the CHR can reach.

```routeros
# Traffic Flow export → Xiguard's flow-collector
/ip traffic-flow set enabled=yes interfaces=all
/ip traffic-flow set cache-entries=64k active-flow-timeout=00:00:05 \
                    inactive-flow-timeout=00:00:05
/ip traffic-flow target add dst-address=10.0.0.50 port=2055 version=9

# Create a dedicated API user with least privilege for control-plane
# actions (blackhole push/remove, health check)
/user group add name=xiguard policy=api,read,write,!ftp,!local,!telnet,!ssh,!winbox,!web,!sniff,!sensitive,!policy,!test,!password,!reboot,!romon,!dude,!tikapp
/user add name=xiguard group=xiguard password="<long random>"

# (Optional, recommended) restrict the API to the Xiguard host only
/ip service set api address=10.0.0.50/32
# or, for TLS:
/ip service set api-ssl address=10.0.0.50/32
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
```

Then in the Xiguard UI: **CHR Nodes → Add Node** → fill in host, port
(8728 plain or 8729 with **Use SSL** ticked), username, password →
**Test Connection** should report RouterOS version + uptime.

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
| `Test Connection` on a CHR returns timeout but ping works | RouterOS API service not enabled, or address-list on `/ip service` excludes the Xiguard host — see step 8 |
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
