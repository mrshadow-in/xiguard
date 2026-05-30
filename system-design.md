# System Design — Xiguard: MikroTik CHR DDoS Monitoring Panel

## 1. Project Overview

**Xiguard** is an internal NOC-grade web panel that connects to multiple MikroTik CHR (Cloud Hosted Router) instances, monitors per-IP traffic across configured IP pools, detects volumetric DDoS attacks via baseline deviation, triggers automatic RTBH (Remotely Triggered Blackhole) mitigation, and dispatches dual-target email alerts to both the Hosting NOC and the upstream ISP NOC.

### 1.1 Problem Statement

When a DDoS attack targets a specific IP in a hosting infrastructure:
- Manual detection is slow — operators notice only when collateral damage occurs
- ISP scrubbing requires a human to email or call the NOC
- There is no centralized view across multiple MikroTik CHR nodes
- Blackholing is done manually via RouterOS CLI, introducing delay

### 1.2 Goals

1. **Multi-CHR management** — attach N MikroTik CHR instances from a single admin panel
2. **IP pool configuration** — define IP pools (e.g., `162.141.0.0/24`) and bind them to specific CHR nodes
3. **Per-IP traffic baselining** — learn normal traffic patterns per IP over a rolling window
4. **Spike detection** — detect when an IP's inbound traffic exceeds its baseline by a configurable multiplier within a 30-second window
5. **Auto-blackhole** — push a blackhole route to the target CHR via RouterOS API on detection
6. **Dual email alerts** — send templated alerts to (a) Hosting NOC and (b) ISP NOC with different messaging
7. **Dashboard** — real-time view of all IPs, traffic rates, alert history, and blackhole status

---

## 2. Functional Requirements

### 2.1 Admin Panel

| Feature | Description |
|---------|-------------|
| CHR Management | Add/edit/remove MikroTik CHR instances (IP, API port, credentials) |
| IP Pool Management | Define CIDR pools, assign each pool to a target CHR |
| Mail Configuration | SMTP settings + two recipient groups: Hosting NOC, ISP NOC |
| Threshold Config | Global and per-pool multiplier (default: 3×), evaluation window (default: 30s) |
| Blackhole Policy | Auto-blackhole toggle, blackhole duration, community string for RTBH |
| User Management | Admin login, API key management for CHR credentials |

### 2.2 Monitoring Engine

| Feature | Description |
|---------|-------------|
| Traffic Polling | Poll each CHR's accounting/traffic data every 5 seconds via RouterOS API |
| Baseline Calculation | Rolling exponential weighted moving average (EWMA) per IP, 1-hour warm-up |
| Spike Detection | Flag when `current_bps > baseline_bps × multiplier` sustained for evaluation window |
| State Machine | Per-IP states: `NORMAL → ALERT → BLACKHOLED → RECOVERING → NORMAL` |

### 2.3 Mitigation

| Feature | Description |
|---------|-------------|
| Auto-Blackhole | Push `/ip route add dst-address={IP}/32 type=blackhole` to target CHR |
| Manual Override | Admin can manually blackhole/unblackhole any IP from the panel |
| Auto-Recovery | Remove blackhole after configurable cooldown (default: 10 minutes), re-evaluate |

### 2.4 Alerting

| Feature | Description |
|---------|-------------|
| Hosting NOC Email | Subject: `[Xiguard ALERT] DDoS detected on {IP}` — includes traffic graph, baseline vs current, CHR name, pool, timestamp |
| ISP NOC Email | Subject: `[URGENT] Manual scrubbing requested for {IP}` — formal tone requesting immediate scrubbing, includes IP, AS number, approximate attack volume, contact details |
| Alert Dedup | No repeat alerts for same IP within 5-minute window |
| Recovery Email | Notify both NOCs when blackhole is lifted and traffic normalizes |

---

## 3. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Polling Latency | < 2 seconds per CHR per cycle |
| Detection Latency | < 30 seconds from spike onset to alert |
| Blackhole Latency | < 5 seconds from detection to route push |
| Email Delivery | < 10 seconds from detection to SMTP handoff |
| Concurrent CHRs | Support up to 20 CHR instances |
| Concurrent IPs | Support up to 5,000 monitored IPs across all pools |
| Uptime | Designed for 24/7 operation with auto-restart |
| Data Retention | 30 days of per-IP traffic history, 90 days of alert logs |

---

## 4. Technology Stack

### 4.1 Backend

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.11+ | RouterOS API libraries, async support, team familiarity |
| Framework | FastAPI | Async-native, WebSocket support for real-time dashboard |
| Task Queue | Celery + Redis | Periodic polling tasks, alert dispatch |
| Scheduler | Celery Beat | 5-second polling intervals |
| Database | PostgreSQL 16 | Time-series traffic data, config storage, alert logs |
| Cache | Redis | Real-time traffic counters, baseline cache, pub/sub for WebSocket |
| RouterOS API | `librouteros` | Native Python RouterOS API client |
| Email | `aiosmtplib` | Async SMTP for non-blocking alert dispatch |

### 4.2 Frontend

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Framework | Next.js 14 (App Router) | SSR for initial load, client components for real-time |
| UI Library | Tailwind CSS + shadcn/ui | Consistent dark NOC theme |
| Charts | Recharts | Real-time traffic graphs |
| Real-time | WebSocket (native) | Live traffic updates, alert feed |
| State | Zustand | Lightweight global state for WebSocket data |

### 4.3 Infrastructure

| Component | Technology |
|-----------|-----------|
| Containerization | Docker Compose |
| Reverse Proxy | Caddy |
| Process Manager | systemd (production) |
| Monitoring | Health check endpoint + Uptime Kuma |

---

## 5. Data Model

### 5.1 Core Entities

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   chr_nodes      │     │   ip_pools       │     │   monitored_ips  │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ id (PK)          │◄────│ chr_node_id (FK) │     │ id (PK)          │
│ name             │     │ id (PK)          │◄────│ pool_id (FK)     │
│ host             │     │ cidr             │     │ ip_address       │
│ api_port         │     │ description      │     │ state            │
│ username         │     │ multiplier       │     │ baseline_bps     │
│ password_enc     │     │ eval_window_sec  │     │ current_bps      │
│ use_ssl          │     │ auto_blackhole   │     │ last_spike_at    │
│ status           │     │ created_at       │     │ blackholed_at    │
│ last_seen_at     │     └─────────────────┘     │ updated_at       │
│ created_at       │                              └─────────────────┘
└─────────────────┘
                          ┌─────────────────┐     ┌─────────────────┐
                          │  traffic_samples │     │   alerts         │
                          ├─────────────────┤     ├─────────────────┤
                          │ id (PK)          │     │ id (PK)          │
                          │ ip_id (FK)       │     │ ip_id (FK)       │
                          │ bps_in           │     │ type             │
                          │ bps_out          │     │ severity         │
                          │ pps_in           │     │ baseline_bps     │
                          │ pps_out          │     │ peak_bps         │
                          │ sampled_at       │     │ action_taken     │
                          └─────────────────┘     │ hosting_email_id │
                                                  │ isp_email_id     │
                          ┌─────────────────┐     │ created_at       │
                          │  mail_configs    │     │ resolved_at      │
                          ├─────────────────┤     └─────────────────┘
                          │ id (PK)          │
                          │ config_type      │  ← 'hosting_noc' | 'isp_noc'
                          │ smtp_host        │
                          │ smtp_port        │
                          │ smtp_user        │
                          │ smtp_pass_enc    │
                          │ from_address     │
                          │ to_addresses     │  ← JSON array
                          │ use_tls          │
                          │ enabled          │
                          └─────────────────┘
```

### 5.2 IP State Machine

```
                    ┌──────────┐
          ┌────────►│  NORMAL  │◄────────────────────┐
          │         └────┬─────┘                     │
          │              │ spike detected            │ traffic normalized
          │              │ (current > baseline × N    │ after cooldown
          │              │  for eval_window seconds)  │
          │              ▼                            │
          │         ┌──────────┐                ┌────┴────────┐
          │         │  ALERT   │───────────────►│ RECOVERING  │
          │         └────┬─────┘  cooldown      └─────────────┘
          │              │        expires              ▲
          │              │ auto_blackhole              │
          │              │ enabled                     │
          │              ▼                             │
          │         ┌──────────────┐                   │
          └─────────│  BLACKHOLED  │───────────────────┘
           manual   └──────────────┘  blackhole duration
           unblackhole                expires
```

---

## 6. Security Considerations

1. **CHR Credentials**: AES-256-GCM encrypted at rest in PostgreSQL, decrypted only in-memory by the polling worker
2. **SMTP Credentials**: Same encryption as CHR credentials
3. **Admin Auth**: Session-based with bcrypt password hashing, optional TOTP 2FA
4. **API Security**: All endpoints behind auth middleware, CSRF protection on forms
5. **Network**: Panel should run on a management VLAN, not exposed to public internet
6. **Audit Log**: All config changes (CHR add/remove, pool changes, manual blackhole) logged with timestamp and admin user

---

## 7. Deployment Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Docker Compose                      │
│                                                       │
│  ┌─────────┐  ┌──────────┐  ┌────────┐  ┌────────┐  │
│  │  Caddy   │  │ FastAPI  │  │ Celery │  │ Celery │  │
│  │ (proxy)  │──│ (web)    │  │ Worker │  │  Beat  │  │
│  │ :443     │  │ :8000    │  │        │  │        │  │
│  └─────────┘  └────┬─────┘  └───┬────┘  └───┬────┘  │
│                     │            │            │       │
│               ┌─────┴────────────┴────────────┴──┐   │
│               │            Redis                  │   │
│               │         (broker + cache)           │   │
│               └──────────────────────────────────┘   │
│               ┌──────────────────────────────────┐   │
│               │         PostgreSQL 16              │   │
│               │       (persistent data)            │   │
│               └──────────────────────────────────┘   │
│                                                       │
│  ┌───────────┐                                        │
│  │  Next.js  │  (built static, served by Caddy)       │
│  │ (frontend)│                                        │
│  └───────────┘                                        │
└──────────────────────────────────────────────────────┘
         │
         │ RouterOS API (8728/8729)
         ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │  CHR #1  │  │  CHR #2  │  │  CHR #N  │
   │ (Rajpura)│  │ (Mumbai) │  │  (...)   │
   └──────────┘  └──────────┘  └──────────┘
```

---

## 8. Key Algorithms

### 8.1 Baseline Calculation (EWMA)

```python
# α = 2 / (span + 1), where span = number of samples in baseline window
# For 1-hour baseline with 5s polling: span = 720
ALPHA = 2 / (720 + 1)  # ≈ 0.00277

def update_baseline(current_baseline: float, new_sample: float) -> float:
    if current_baseline == 0:
        return new_sample
    return ALPHA * new_sample + (1 - ALPHA) * current_baseline
```

### 8.2 Spike Detection

```python
def check_spike(ip: MonitoredIP, pool: IPPool) -> bool:
    threshold = ip.baseline_bps * pool.multiplier
    # Check if current traffic exceeds threshold
    if ip.current_bps <= threshold:
        ip.spike_start = None
        return False
    # Check if spike has persisted for evaluation window
    if ip.spike_start is None:
        ip.spike_start = now()
        return False
    return (now() - ip.spike_start).total_seconds() >= pool.eval_window_sec
```

### 8.3 Traffic Data Collection (RouterOS API)

```python
# Using /ip/accounting or /interface/monitor-traffic
# Preferred: /ip/accounting/snapshot for per-IP granularity
async def poll_chr(chr_node: CHRNode) -> dict[str, TrafficSample]:
    async with routeros_connect(chr_node) as api:
        # Take accounting snapshot
        await api('/ip/accounting/snapshot/take')
        data = await api('/ip/accounting/snapshot/print')
        # Aggregate per destination IP
        per_ip = aggregate_by_dst_ip(data)
        # Reset accounting
        await api('/ip/accounting/snapshot/take')
        return per_ip
```

---

## 9. Email Templates

### 9.1 Hosting NOC Alert

```
Subject: [Xiguard ALERT] DDoS detected on {ip_address}
---
ALERT: Volumetric DDoS Attack Detected

Target IP:       {ip_address}
Pool:            {pool_cidr}
CHR Node:        {chr_name} ({chr_host})
Detected At:     {timestamp_utc} UTC

Traffic Analysis:
  Baseline:      {baseline_bps} ({baseline_human})
  Current:       {current_bps} ({current_human})
  Multiplier:    {current/baseline}×
  Peak:          {peak_bps} ({peak_human})

Action Taken:    {action} (Auto-Blackhole / Alert Only)

This is an automated alert from Xiguard.
```

### 9.2 ISP NOC Alert

```
Subject: [URGENT] Manual scrubbing requested — {ip_address} — AS{as_number}
---
Dear NOC Team,

We are observing a possible volumetric DDoS attack targeting
the following IP address on our network:

  IP Address:    {ip_address}
  AS Number:     AS{as_number}
  Approx Volume: {current_human}
  Started:       {timestamp_utc} UTC

We kindly request immediate manual scrubbing for this IP
with immediate effect.

Please acknowledge receipt of this request.

Regards,
{company_name} NOC
{noc_contact_email}
{noc_contact_phone}
```

---

## 10. Open Questions / Future Scope

1. **sFlow/NetFlow integration** — replace API polling with flow-based collection for higher accuracy at scale
2. **BGP RTBH via community** — instead of local blackhole routes, advertise blackhole via BGP community (e.g., `215228:666`) to upstream
3. **Multi-tenant** — support multiple organizations with isolated CHR groups
4. **Webhook alerts** — Slack/Discord/Telegram in addition to email
5. **Historical analytics** — attack pattern analysis, top-targeted IPs dashboard
6. **GoBGP integration** — direct BGP session for RTBH advertisement without going through CHR
