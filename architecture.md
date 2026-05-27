# Architecture Document — CHRGuard

## 1. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                     │
│                                                                           │
│   Next.js 14 (App Router)                                                 │
│   ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│   │  Dashboard   │  │  CHR Nodes   │  │   IP Pools   │  │   Settings   │  │
│   │  (real-time) │  │  (CRUD)      │  │  (CRUD)      │  │  (mail/cfg)  │  │
│   └──────┬──────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│          │                │                  │                  │          │
│   ┌──────┴──────────────┴──────────────────┴──────────────────┴───────┐  │
│   │                     Zustand Store Layer                            │  │
│   │   trafficStore (WebSocket)    │    alertStore (WebSocket)          │  │
│   └──────────────────┬──────────────────────┬─────────────────────────┘  │
│                      │ WS                    │ REST                       │
└──────────────────────┼──────────────────────┼────────────────────────────┘
                       │                      │
═══════════════════════╪══════════════════════╪═══════════════ NETWORK ═════
                       │                      │
┌──────────────────────┼──────────────────────┼────────────────────────────┐
│                      │      BACKEND         │                             │
│                      ▼                      ▼                             │
│   ┌──────────────────────────────────────────────────────────────────┐   │
│   │                     FastAPI Application                          │   │
│   │                                                                  │   │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐   │   │
│   │  │ REST API │  │WebSocket │  │  Auth    │  │  Middleware     │   │   │
│   │  │ Routers  │  │  Manager │  │  Layer   │  │ (CORS, Rate)   │   │   │
│   │  └────┬─────┘  └────┬─────┘  └──────────┘  └────────────────┘   │   │
│   │       │              │                                            │   │
│   │  ┌────┴──────────────┴──────────────────────────────────────┐    │   │
│   │  │                  Service Layer                            │    │   │
│   │  │                                                           │    │   │
│   │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │    │   │
│   │  │  │  Poller  │ │ Detector │ │Mitigator │ │ Alerter  │    │    │   │
│   │  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘    │    │   │
│   │  │       │             │            │             │          │    │   │
│   │  └───────┼─────────────┼────────────┼─────────────┼──────────┘    │   │
│   └──────────┼─────────────┼────────────┼─────────────┼──────────────┘   │
│              │             │            │             │                    │
│   ┌──────────┴─────────────┴────────────┴─────────────┴──────────────┐   │
│   │                    Celery Task Layer                               │   │
│   │                                                                    │   │
│   │  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐             │   │
│   │  │ poll_all_chr │  │ evaluate_ips │  │ check_expiry │             │   │
│   │  │  (every 5s)  │  │ (after poll) │  │ (every 30s)  │             │   │
│   │  └─────────────┘  └──────────────┘  └──────────────┘             │   │
│   └──────────────────────────────────────────────────────────────────┘   │
│                                                                           │
│   ┌──────────────────┐  ┌──────────────────┐                             │
│   │   PostgreSQL 16  │  │      Redis        │                             │
│   │                  │  │                   │                             │
│   │  • chr_nodes     │  │  • Celery broker  │                             │
│   │  • ip_pools      │  │  • Traffic cache  │                             │
│   │  • monitored_ips │  │  • Baseline cache │                             │
│   │  • traffic_data  │  │  • Pub/Sub        │                             │
│   │  • alerts        │  │  • Rate limiting  │                             │
│   │  • mail_configs  │  │                   │                             │
│   │  • users         │  │                   │                             │
│   └──────────────────┘  └──────────────────┘                             │
└──────────────────────────────────────────────────────────────────────────┘
         │                                              │
         │ RouterOS API (8728/8729)                      │ SMTP (587/465)
         ▼                                              ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐     ┌──────────────┐
   │  CHR #1  │  │  CHR #2  │  │  CHR #N  │     │  SMTP Server │
   │ Rajpura  │  │  Mumbai  │  │   ...    │     │  (Postal)    │
   └──────────┘  └──────────┘  └──────────┘     └──────────────┘
```

---

## 2. Data Flow Architecture

### 2.1 Traffic Monitoring Pipeline

```
 ┌─ EVERY 5 SECONDS ──────────────────────────────────────────────────────┐
 │                                                                         │
 │  ┌─────────────┐     ┌──────────────┐     ┌───────────────┐            │
 │  │ Celery Beat  │────►│ poll_all_chr │────►│ For each CHR: │            │
 │  │ (scheduler)  │     │   (task)     │     │  asyncio pool │            │
 │  └─────────────┘     └──────────────┘     └───────┬───────┘            │
 │                                                    │                    │
 │       ┌────────────────────────────────────────────┤                    │
 │       │                                            │                    │
 │       ▼                                            ▼                    │
 │  ┌─────────────────┐                    ┌─────────────────┐            │
 │  │ RouterOS API    │                    │ RouterOS API    │            │
 │  │ CHR #1          │                    │ CHR #2          │            │
 │  │                 │                    │                 │            │
 │  │ 1. /ip/acct/   │                    │ 1. /ip/acct/   │            │
 │  │    snapshot/take│                    │    snapshot/take│            │
 │  │ 2. Read data   │                    │ 2. Read data   │            │
 │  │ 3. Delta calc  │                    │ 3. Delta calc  │            │
 │  └────────┬────────┘                    └────────┬────────┘            │
 │           │                                      │                     │
 │           └──────────────┬───────────────────────┘                     │
 │                          │                                              │
 │                          ▼                                              │
 │              ┌───────────────────────┐                                  │
 │              │   Aggregate Results   │                                  │
 │              │   per-IP: bps, pps    │                                  │
 │              └───────────┬───────────┘                                  │
 │                          │                                              │
 │            ┌─────────────┼─────────────┐                               │
 │            │             │             │                                │
 │            ▼             ▼             ▼                                │
 │     ┌────────────┐ ┌──────────┐ ┌──────────────┐                      │
 │     │ PostgreSQL │ │  Redis   │ │  Redis       │                      │
 │     │ batch      │ │ HSET     │ │ PUB          │                      │
 │     │ INSERT     │ │ traffic  │ │ chrguard:    │                      │
 │     │ samples    │ │ cache    │ │ traffic      │───► WebSocket ──► UI │
 │     └────────────┘ └──────────┘ └──────────────┘                      │
 │                                                                         │
 └─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Detection & Mitigation Pipeline

```
 ┌─ TRIGGERED AFTER EACH POLL ────────────────────────────────────────────┐
 │                                                                         │
 │  ┌──────────────┐     ┌────────────────────────────────────┐           │
 │  │ evaluate_ips │────►│ For each IP with new sample:       │           │
 │  │   (task)     │     │                                    │           │
 │  └──────────────┘     │  1. Load baseline from Redis cache │           │
 │                        │  2. Update EWMA baseline           │           │
 │                        │  3. Compare: current vs threshold  │           │
 │                        │  4. Check spike persistence        │           │
 │                        └─────────────────┬──────────────────┘           │
 │                                          │                              │
 │                              ┌───────────┴───────────┐                 │
 │                              │                       │                  │
 │                        spike = false            spike = true            │
 │                              │                       │                  │
 │                              ▼                       ▼                  │
 │                     ┌──────────────┐      ┌─────────────────────┐      │
 │                     │ Update state │      │ Transition to ALERT │      │
 │                     │ NORMAL       │      └──────────┬──────────┘      │
 │                     │ (or RECOVER  │                 │                  │
 │                     │  → NORMAL)   │       ┌─────────┴─────────┐       │
 │                     └──────────────┘       │                   │       │
 │                                      auto_blackhole       alert_only   │
 │                                      enabled               │          │
 │                                            │                │          │
 │                                            ▼                │          │
 │                                   ┌────────────────┐        │          │
 │                                   │   Mitigator    │        │          │
 │                                   │                │        │          │
 │                                   │ RouterOS API:  │        │          │
 │                                   │ /ip/route/add  │        │          │
 │                                   │ type=blackhole │        │          │
 │                                   └───────┬────────┘        │          │
 │                                           │                 │          │
 │                                           └────────┬────────┘          │
 │                                                    │                   │
 │                                                    ▼                   │
 │                                           ┌────────────────┐          │
 │                                           │    Alerter     │          │
 │                                           │                │          │
 │                                           │ ┌────────────┐ │          │
 │                                           │ │Hosting NOC │ │          │
 │                                           │ │  (tech)    │─┼──► SMTP │
 │                                           │ └────────────┘ │          │
 │                                           │ ┌────────────┐ │          │
 │                                           │ │  ISP NOC   │ │          │
 │                                           │ │ (formal)   │─┼──► SMTP │
 │                                           │ └────────────┘ │          │
 │                                           └───────┬────────┘          │
 │                                                   │                   │
 │                                                   ▼                   │
 │                                       Redis PUB chrguard:alerts       │
 │                                              │                        │
 │                                              ▼                        │
 │                                      WebSocket ──► UI Alert Feed      │
 │                                                                        │
 └────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Recovery Pipeline

```
 ┌─ EVERY 30 SECONDS ─────────────────────────────────────────────────────┐
 │                                                                         │
 │  ┌──────────────┐     ┌──────────────────────────────────────┐         │
 │  │ check_expiry │────►│ Query all IPs where:                 │         │
 │  │   (task)     │     │   state = BLACKHOLED                 │         │
 │  └──────────────┘     │   AND blackholed_at + duration < now │         │
 │                        └─────────────────┬────────────────────┘         │
 │                                          │                              │
 │                                          ▼                              │
 │                               ┌─────────────────────┐                  │
 │                               │   Mitigator         │                  │
 │                               │                     │                  │
 │                               │ RouterOS API:       │                  │
 │                               │ /ip/route/remove    │                  │
 │                               │ (CHRGuard routes)   │                  │
 │                               └──────────┬──────────┘                  │
 │                                          │                              │
 │                                          ▼                              │
 │                               ┌─────────────────────┐                  │
 │                               │ Transition to       │                  │
 │                               │ RECOVERING           │                  │
 │                               │                      │                  │
 │                               │ Monitor for 60s:    │                  │
 │                               │ • Normal → NORMAL   │                  │
 │                               │ • Spike  → re-ALERT │                  │
 │                               └──────────┬──────────┘                  │
 │                                          │                              │
 │                                          ▼                              │
 │                              Send recovery email to                     │
 │                              both NOC groups                            │
 │                                                                         │
 └─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Architecture

### 3.1 Service Layer Dependency Graph

```
                    ┌──────────────┐
                    │   FastAPI    │
                    │   Routers   │
                    └──────┬───────┘
                           │ depends on
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │  Poller  │ │  Actions │ │ Settings │
       └────┬─────┘ └────┬─────┘ └──────────┘
            │             │
            │  triggers   │ calls
            ▼             ▼
       ┌──────────┐ ┌──────────┐
       │ Detector │ │Mitigator │
       └────┬─────┘ └────┬─────┘
            │             │
            │  triggers   │
            ▼             │
       ┌──────────┐       │
       │ Alerter  │◄──────┘ (on blackhole success/fail)
       └────┬─────┘
            │
            ▼
       ┌──────────┐
       │  Crypto  │  (used by all services for credential decryption)
       └──────────┘
```

### 3.2 Frontend Component Tree

```
App (layout.tsx)
├── AuthGuard
│   ├── Sidebar
│   │   ├── NavItem: Dashboard
│   │   ├── NavItem: CHR Nodes
│   │   ├── NavItem: IP Pools
│   │   ├── NavItem: Alerts
│   │   └── NavItem: Settings
│   │
│   └── PageShell
│       │
│       ├── [Dashboard Page]
│       │   ├── CHRHealthBar          ← CHR online/offline status
│       │   ├── TrafficOverview       ← Aggregate line chart (Recharts)
│       │   │   └── TimeRangeSelector
│       │   ├── IPStatusGrid          ← Card grid, color-coded by state
│       │   │   └── IPStatusCard      ← Per-IP: bps gauge, state badge
│       │   │       ├── BaselineIndicator
│       │   │       └── QuickActions (blackhole/unblackhole)
│       │   ├── AlertFeed             ← Live scrolling alert list
│       │   │   └── AlertItem         ← Severity icon + summary
│       │   └── TopTargetsTable       ← Sorted by attack frequency
│       │
│       ├── [CHR Nodes Page]
│       │   ├── DataTable             ← List all CHRs with status
│       │   ├── CHRNodeForm           ← Add/edit modal
│       │   └── ConnectionTestButton  ← Test RouterOS connectivity
│       │
│       ├── [IP Pools Page]
│       │   ├── DataTable             ← List all pools
│       │   ├── IPPoolForm            ← Add/edit with CHR selector
│       │   └── [Pool Detail]
│       │       ├── PoolStatsBar      ← Total IPs, blackholed, alerts
│       │       └── IPTable           ← All IPs in pool with status
│       │           └── IPTrafficChart ← Expandable per-IP chart
│       │
│       ├── [Alerts Page]
│       │   ├── AlertFilters          ← Date, severity, IP, state
│       │   ├── AlertStats            ← Count by day/severity chart
│       │   └── DataTable             ← Alert history with details
│       │
│       └── [Settings Page]
│           ├── GeneralSettings       ← Defaults form
│           └── MailConfigForm (×2)   ← Hosting NOC + ISP NOC tabs
│               └── TestEmailButton
```

---

## 4. Database Architecture

### 4.1 Schema with Indexes

```sql
-- CHR Router Nodes
CREATE TABLE chr_nodes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    host        VARCHAR(255) NOT NULL,
    api_port    INTEGER NOT NULL DEFAULT 8728,
    username    VARCHAR(255) NOT NULL,
    password_enc BYTEA NOT NULL,          -- AES-256-GCM encrypted
    use_ssl     BOOLEAN NOT NULL DEFAULT FALSE,
    status      VARCHAR(20) NOT NULL DEFAULT 'unknown',  -- online/offline/unknown
    last_seen_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- IP Pools (CIDR blocks assigned to CHR nodes)
CREATE TABLE ip_pools (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chr_node_id     UUID NOT NULL REFERENCES chr_nodes(id) ON DELETE CASCADE,
    cidr            CIDR NOT NULL,
    description     TEXT,
    multiplier      REAL NOT NULL DEFAULT 3.0,
    eval_window_sec INTEGER NOT NULL DEFAULT 30,
    auto_blackhole  BOOLEAN NOT NULL DEFAULT TRUE,
    blackhole_duration_sec INTEGER NOT NULL DEFAULT 600,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ip_pools_chr ON ip_pools(chr_node_id);

-- Individual monitored IPs (auto-populated from pool CIDR)
CREATE TABLE monitored_ips (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pool_id     UUID NOT NULL REFERENCES ip_pools(id) ON DELETE CASCADE,
    ip_address  INET NOT NULL UNIQUE,
    state       VARCHAR(20) NOT NULL DEFAULT 'NORMAL',
    baseline_bps BIGINT NOT NULL DEFAULT 0,
    current_bps  BIGINT NOT NULL DEFAULT 0,
    current_pps  BIGINT NOT NULL DEFAULT 0,
    spike_start  TIMESTAMPTZ,           -- when current spike began
    last_spike_at TIMESTAMPTZ,
    blackholed_at TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_monitored_ips_pool ON monitored_ips(pool_id);
CREATE INDEX idx_monitored_ips_state ON monitored_ips(state) WHERE state != 'NORMAL';
CREATE INDEX idx_monitored_ips_blackholed ON monitored_ips(blackholed_at)
    WHERE state = 'BLACKHOLED';

-- Traffic samples (time-series, partitioned by day)
CREATE TABLE traffic_samples (
    id          BIGSERIAL,
    ip_id       UUID NOT NULL REFERENCES monitored_ips(id) ON DELETE CASCADE,
    bps_in      BIGINT NOT NULL,
    bps_out     BIGINT NOT NULL,
    pps_in      BIGINT NOT NULL,
    pps_out     BIGINT NOT NULL,
    sampled_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (sampled_at);
CREATE INDEX idx_traffic_ip_time ON traffic_samples(ip_id, sampled_at DESC);

-- Auto-create daily partitions (run via cron or pg_partman)
-- CREATE TABLE traffic_samples_20260524 PARTITION OF traffic_samples
--     FOR VALUES FROM ('2026-05-24') TO ('2026-05-25');

-- Alerts
CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_id           UUID NOT NULL REFERENCES monitored_ips(id) ON DELETE CASCADE,
    type            VARCHAR(30) NOT NULL,  -- ddos_detected, blackhole_applied, recovered, chr_offline
    severity        VARCHAR(10) NOT NULL,  -- critical, warning, info
    baseline_bps    BIGINT,
    peak_bps        BIGINT,
    action_taken    VARCHAR(30),           -- auto_blackhole, alert_only, blackhole_failed, manual
    hosting_email_sent BOOLEAN DEFAULT FALSE,
    isp_email_sent     BOOLEAN DEFAULT FALSE,
    acknowledged    BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_by VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX idx_alerts_ip ON alerts(ip_id, created_at DESC);
CREATE INDEX idx_alerts_unack ON alerts(acknowledged) WHERE acknowledged = FALSE;

-- Mail configuration
CREATE TABLE mail_configs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_type VARCHAR(20) NOT NULL UNIQUE,  -- hosting_noc, isp_noc
    smtp_host   VARCHAR(255) NOT NULL,
    smtp_port   INTEGER NOT NULL DEFAULT 587,
    smtp_user   VARCHAR(255),
    smtp_pass_enc BYTEA,
    from_address VARCHAR(255) NOT NULL,
    to_addresses JSONB NOT NULL DEFAULT '[]',  -- ["noc@example.com"]
    cc_addresses JSONB NOT NULL DEFAULT '[]',
    use_tls     BOOLEAN NOT NULL DEFAULT TRUE,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users (admin panel access)
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username    VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    last_login  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit log
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id),
    action      VARCHAR(50) NOT NULL,
    entity_type VARCHAR(30) NOT NULL,
    entity_id   UUID,
    details     JSONB,
    ip_address  INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_time ON audit_log(created_at DESC);
```

### 4.2 Data Retention Strategy

```
┌────────────────────┬──────────────┬───────────────────────────┐
│ Data               │ Retention    │ Cleanup Method            │
├────────────────────┼──────────────┼───────────────────────────┤
│ traffic_samples    │ 30 days      │ DROP partition daily      │
│ alerts             │ 90 days      │ DELETE WHERE created_at < │
│ audit_log          │ 365 days     │ DELETE WHERE created_at < │
│ baseline (Redis)   │ Persistent   │ Synced to DB every 5 min │
│ traffic cache      │ 60s TTL      │ Auto-expire in Redis      │
└────────────────────┴──────────────┴───────────────────────────┘
```

---

## 5. Network Architecture

### 5.1 Communication Paths

```
┌───────────────────────────────────────────────────────────────┐
│                    Management VLAN (10.0.0.0/24)              │
│                                                               │
│   ┌──────────────┐                                           │
│   │   CHRGuard   │                                           │
│   │   Server     │                                           │
│   │  10.0.0.50   │                                           │
│   └──────┬───────┘                                           │
│          │                                                    │
│          ├───────── TCP 8728 ──────────► CHR #1 (10.0.0.1)   │
│          ├───────── TCP 8728 ──────────► CHR #2 (10.0.0.2)   │
│          ├───────── TCP 8728 ──────────► CHR #N (10.0.0.N)   │
│          │                                                    │
│          ├───────── TCP 587  ──────────► SMTP (Postal)        │
│          │                               (can be external)    │
│          │                                                    │
│          └───────── TCP 443  ◄──────── Admin Browser          │
│                     (Caddy)             (HTTPS only)          │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### 5.2 Port Matrix

```
┌─────────────┬──────────┬───────────┬────────────────────────────┐
│ Service     │ Port     │ Protocol  │ Notes                      │
├─────────────┼──────────┼───────────┼────────────────────────────┤
│ Caddy       │ 443      │ HTTPS     │ Frontend + API reverse prx │
│ FastAPI     │ 8000     │ HTTP      │ Internal only (behind Caddy│
│ PostgreSQL  │ 5432     │ TCP       │ Internal only              │
│ Redis       │ 6379     │ TCP       │ Internal only              │
│ RouterOS    │ 8728     │ TCP       │ CHRGuard → CHR (plaintext) │
│ RouterOS    │ 8729     │ TCP+TLS   │ CHRGuard → CHR (encrypted) │
│ SMTP        │ 587      │ TCP+TLS   │ CHRGuard → Postal/SMTP     │
└─────────────┴──────────┴───────────┴────────────────────────────┘
```

---

## 6. Celery Task Architecture

### 6.1 Task Graph

```
┌─────────────────────────────────────────────────────────┐
│                   Celery Beat Schedule                    │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ poll_all_chr          │ every 5 seconds              │ │
│  │ check_blackhole_expiry │ every 30 seconds            │ │
│  │ sync_baselines_to_db  │ every 5 minutes              │ │
│  │ cleanup_old_data      │ daily at 03:00 UTC           │ │
│  │ health_check_chrs     │ every 60 seconds             │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

Task Chain (polling cycle):

  poll_all_chr
       │
       │ .si() (immutable signature)
       ▼
  evaluate_ips_batch(ip_samples)
       │
       ├──► [if spike] dispatch_alert.delay(ip_id, ...)
       │         │
       │         ├──► send_hosting_noc_email.delay(...)
       │         └──► send_isp_noc_email.delay(...)
       │
       └──► [if spike + auto_blackhole] push_blackhole.delay(ip_id, chr_id)
```

### 6.2 Task Queues

```
┌────────────────┬──────────────┬────────────────────────────┐
│ Queue          │ Concurrency  │ Tasks                      │
├────────────────┼──────────────┼────────────────────────────┤
│ default        │ 4            │ poll, evaluate, sync       │
│ critical       │ 2            │ blackhole push/remove      │
│ email          │ 2            │ alert email dispatch       │
│ maintenance    │ 1            │ cleanup, health check      │
└────────────────┴──────────────┴────────────────────────────┘
```

---

## 7. Security Architecture

### 7.1 Credential Flow

```
Admin enters CHR password in form
       │
       ▼
Frontend sends over HTTPS ──► FastAPI receives plaintext
       │
       ▼
crypto.encrypt(password, ENCRYPTION_KEY)
       │
       ▼
Stored as BYTEA in PostgreSQL (AES-256-GCM)
       │
       │  (at poll time)
       ▼
crypto.decrypt(password_enc, ENCRYPTION_KEY)
       │
       ▼
Used in-memory only for RouterOS API connection
       │
       ▼
Discarded after connection (not cached in Redis)
```

### 7.2 Authentication Flow

```
POST /api/auth/login { username, password }
       │
       ▼
bcrypt.verify(password, stored_hash)
       │
       ├── fail → 401
       │
       └── pass → Generate session token (UUID)
                   Store in Redis with 24h TTL
                   Set HttpOnly cookie
                          │
                          ▼
                   All subsequent requests:
                   Cookie → Redis lookup → user_id
                   Attach user to request context
```

---

## 8. Scalability Considerations

### 8.1 Current Capacity (Single Server)

```
┌──────────────────────────────────────────────────────────┐
│                     Single Server Profile                 │
│                                                           │
│  CHR Nodes:        up to 20                               │
│  Total IPs:        up to 5,000                            │
│  Poll interval:    5 seconds                              │
│  Samples/day:      5,000 × 17,280 = 86.4M rows           │
│  DB size/month:    ~50 GB (with compression)              │
│  Redis memory:     ~100 MB (baselines + cache)            │
│  WebSocket conns:  up to 50 concurrent                    │
│                                                           │
│  Minimum hardware: 4 vCPU, 8 GB RAM, 200 GB NVMe         │
│  Recommended:      8 vCPU, 16 GB RAM, 500 GB NVMe        │
└──────────────────────────────────────────────────────────┘
```

### 8.2 Future Scaling Path

```
Phase 1 (current): Single Docker Compose deployment
Phase 2: Separate DB to dedicated PostgreSQL instance
Phase 3: Add TimescaleDB extension for traffic_samples
Phase 4: sFlow/NetFlow collector replaces API polling (10× more IPs)
Phase 5: Multiple CHRGuard workers behind load balancer (if needed)
```

---

## 9. Docker Compose Architecture

```yaml
# docker-compose.yml structure (not full file)
services:
  caddy:        # Reverse proxy, auto-TLS
  api:          # FastAPI application
  worker:       # Celery worker (default + critical queues)
  worker-email: # Celery worker (email queue)
  beat:         # Celery Beat scheduler
  postgres:     # PostgreSQL 16
  redis:        # Redis 7
  frontend:     # Next.js (build stage only, static served by Caddy)

volumes:
  pg_data:      # PostgreSQL persistent storage
  redis_data:   # Redis persistent storage (AOF for baseline durability)
```

---

## 10. Monitoring & Observability

### 10.1 Health Endpoints

```
GET /api/health          → { status, db, redis, celery_workers }
GET /api/health/detailed → { per_chr_status, last_poll_times, queue_depths }
```

### 10.2 Metrics to Track

```
┌──────────────────────────────────┬────────────────────────────┐
│ Metric                          │ Alert Threshold             │
├──────────────────────────────────┼────────────────────────────┤
│ poll_cycle_duration_seconds      │ > 4.5s (approaching limit) │
│ chr_connection_failures_total    │ > 3 consecutive            │
│ detection_latency_seconds        │ > 35s                      │
│ blackhole_push_failures_total    │ any                        │
│ email_send_failures_total        │ > 3 in 5 minutes           │
│ websocket_connections_active     │ monitoring only             │
│ db_pool_exhausted_total          │ any                        │
│ celery_queue_depth               │ > 100 tasks                │
└──────────────────────────────────┴────────────────────────────┘
```
