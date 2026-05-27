# Design Document — CHRGuard

## 1. Project Structure

```
chrguard/
├── CLAUDE.md                    # Claude Code project instructions
├── docker-compose.yml
├── .env.example
│
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app factory
│   │   ├── config.py            # Pydantic Settings
│   │   ├── database.py          # SQLAlchemy async engine + session
│   │   │
│   │   ├── models/              # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── chr_node.py
│   │   │   ├── ip_pool.py
│   │   │   ├── monitored_ip.py
│   │   │   ├── traffic_sample.py
│   │   │   ├── alert.py
│   │   │   ├── mail_config.py
│   │   │   └── user.py
│   │   │
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── chr_node.py
│   │   │   ├── ip_pool.py
│   │   │   ├── monitoring.py
│   │   │   ├── alert.py
│   │   │   └── mail_config.py
│   │   │
│   │   ├── api/                 # FastAPI routers
│   │   │   ├── __init__.py
│   │   │   ├── deps.py          # Dependency injection (auth, db session)
│   │   │   ├── auth.py          # Login, session management
│   │   │   ├── chr_nodes.py     # CRUD for CHR nodes
│   │   │   ├── ip_pools.py      # CRUD for IP pools
│   │   │   ├── monitoring.py    # Real-time status, per-IP data
│   │   │   ├── alerts.py        # Alert history, acknowledge
│   │   │   ├── mail_config.py   # SMTP settings
│   │   │   ├── actions.py       # Manual blackhole/unblackhole
│   │   │   └── ws.py            # WebSocket endpoint
│   │   │
│   │   ├── services/            # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── chr_api.py       # RouterOS API client wrapper
│   │   │   ├── baseline.py      # EWMA baseline calculation
│   │   │   ├── detector.py      # Spike detection engine
│   │   │   ├── mitigator.py     # Blackhole push/remove
│   │   │   ├── alerter.py       # Email dispatch (dual-target)
│   │   │   ├── crypto.py        # AES-256-GCM encrypt/decrypt
│   │   │   └── poller.py        # Traffic data collection orchestrator
│   │   │
│   │   └── tasks/               # Celery tasks
│   │       ├── __init__.py
│   │       ├── celery_app.py    # Celery config
│   │       ├── polling.py       # Periodic traffic polling task
│   │       ├── detection.py     # Spike evaluation task
│   │       ├── recovery.py      # Blackhole expiry check task
│   │       └── cleanup.py       # Data retention cleanup task
│   │
│   └── tests/
│       ├── conftest.py
│       ├── test_baseline.py
│       ├── test_detector.py
│       ├── test_chr_api.py
│       └── test_alerter.py
│
├── frontend/
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── next.config.js
│   │
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx           # Root layout (dark theme, sidebar)
│   │   │   ├── page.tsx             # Dashboard (redirect)
│   │   │   ├── login/page.tsx
│   │   │   ├── dashboard/page.tsx   # Main monitoring view
│   │   │   ├── chr-nodes/
│   │   │   │   ├── page.tsx         # List CHR nodes
│   │   │   │   └── [id]/page.tsx    # Edit CHR node
│   │   │   ├── ip-pools/
│   │   │   │   ├── page.tsx         # List/manage pools
│   │   │   │   └── [id]/page.tsx    # Pool detail + IPs
│   │   │   ├── alerts/page.tsx      # Alert history
│   │   │   └── settings/
│   │   │       ├── page.tsx         # General settings
│   │   │       └── mail/page.tsx    # Mail configuration
│   │   │
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   ├── Header.tsx
│   │   │   │   └── PageShell.tsx
│   │   │   ├── dashboard/
│   │   │   │   ├── TrafficOverview.tsx     # Aggregate traffic chart
│   │   │   │   ├── IPStatusGrid.tsx        # Per-IP status cards
│   │   │   │   ├── AlertFeed.tsx           # Live alert stream
│   │   │   │   ├── CHRHealthBar.tsx        # CHR node health indicators
│   │   │   │   └── TopTargetsTable.tsx     # Top attacked IPs
│   │   │   ├── monitoring/
│   │   │   │   ├── IPTrafficChart.tsx      # Per-IP traffic over time
│   │   │   │   ├── BaselineIndicator.tsx   # Baseline vs current gauge
│   │   │   │   └── StateTimeline.tsx       # IP state transitions
│   │   │   ├── forms/
│   │   │   │   ├── CHRNodeForm.tsx
│   │   │   │   ├── IPPoolForm.tsx
│   │   │   │   └── MailConfigForm.tsx
│   │   │   └── shared/
│   │   │       ├── StatusBadge.tsx
│   │   │       ├── ConfirmDialog.tsx
│   │   │       └── DataTable.tsx
│   │   │
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts      # WebSocket connection manager
│   │   │   ├── useTrafficData.ts    # Real-time traffic state
│   │   │   └── useAlerts.ts         # Alert stream consumer
│   │   │
│   │   ├── lib/
│   │   │   ├── api.ts               # Fetch wrapper + auth
│   │   │   ├── ws.ts                # WebSocket client
│   │   │   └── utils.ts             # Formatters (bps→human, etc.)
│   │   │
│   │   └── stores/
│   │       ├── trafficStore.ts      # Zustand: real-time traffic
│   │       └── alertStore.ts        # Zustand: alert feed
│   │
│   └── public/
│       └── favicon.ico
│
└── scripts/
    ├── init-db.sh
    ├── seed-demo.py
    └── test-chr-connection.py
```

---

## 2. API Design

### 2.1 Authentication

```
POST   /api/auth/login          # { username, password } → { session_token }
POST   /api/auth/logout         # Invalidate session
GET    /api/auth/me             # Current user info
```

### 2.2 CHR Nodes

```
GET    /api/chr-nodes                    # List all CHR nodes
POST   /api/chr-nodes                    # Add new CHR node
GET    /api/chr-nodes/{id}               # Get CHR node details
PUT    /api/chr-nodes/{id}               # Update CHR node
DELETE /api/chr-nodes/{id}               # Remove CHR node
POST   /api/chr-nodes/{id}/test          # Test RouterOS API connection
GET    /api/chr-nodes/{id}/status        # Live connection status + uptime
```

**Request: Create CHR Node**
```json
{
  "name": "Rajpura Edge CHR",
  "host": "10.0.0.1",
  "api_port": 8728,
  "username": "chrguard",
  "password": "secure_password",
  "use_ssl": false,
  "description": "Primary edge router — Rajpura DC"
}
```

**Response: CHR Node**
```json
{
  "id": "uuid",
  "name": "Rajpura Edge CHR",
  "host": "10.0.0.1",
  "api_port": 8728,
  "username": "chrguard",
  "use_ssl": false,
  "status": "online",
  "last_seen_at": "2026-05-24T10:30:00Z",
  "pool_count": 3,
  "monitored_ip_count": 768,
  "created_at": "2026-05-20T08:00:00Z"
}
```

### 2.3 IP Pools

```
GET    /api/ip-pools                     # List all pools
POST   /api/ip-pools                     # Create pool
GET    /api/ip-pools/{id}                # Pool detail + IP list
PUT    /api/ip-pools/{id}                # Update pool settings
DELETE /api/ip-pools/{id}                # Remove pool
GET    /api/ip-pools/{id}/ips            # List all IPs in pool with status
POST   /api/ip-pools/{id}/sync           # Re-sync IPs from CIDR (add missing, remove stale)
```

**Request: Create IP Pool**
```json
{
  "cidr": "162.141.0.0/24",
  "chr_node_id": "uuid",
  "description": "XiteNodes primary block",
  "multiplier": 3.0,
  "eval_window_sec": 30,
  "auto_blackhole": true,
  "blackhole_duration_sec": 600
}
```

### 2.4 Monitoring

```
GET    /api/monitoring/overview          # Aggregate stats: total IPs, alerts, blackholed count
GET    /api/monitoring/traffic           # All IPs with current traffic (paginated)
GET    /api/monitoring/traffic/{ip}      # Single IP traffic history + state
GET    /api/monitoring/blackholed        # Currently blackholed IPs
WS     /api/ws/traffic                   # WebSocket: real-time traffic + alerts
```

**WebSocket Message Types (server → client)**
```json
// Traffic update (every 5s)
{
  "type": "traffic_update",
  "data": {
    "ip": "162.141.0.15",
    "bps_in": 1250000000,
    "bps_out": 45000000,
    "pps_in": 980000,
    "baseline_bps": 50000000,
    "state": "ALERT",
    "chr_node": "Rajpura Edge CHR",
    "pool": "162.141.0.0/24"
  }
}

// Alert fired
{
  "type": "alert",
  "data": {
    "id": "uuid",
    "ip": "162.141.0.15",
    "severity": "critical",
    "type": "ddos_detected",
    "baseline_bps": 50000000,
    "peak_bps": 1250000000,
    "multiplier": 25.0,
    "action_taken": "auto_blackhole",
    "timestamp": "2026-05-24T10:31:15Z"
  }
}

// State change
{
  "type": "state_change",
  "data": {
    "ip": "162.141.0.15",
    "old_state": "ALERT",
    "new_state": "BLACKHOLED",
    "timestamp": "2026-05-24T10:31:16Z"
  }
}
```

### 2.5 Alerts

```
GET    /api/alerts                       # Alert history (paginated, filterable)
GET    /api/alerts/{id}                  # Alert detail
POST   /api/alerts/{id}/acknowledge      # Mark as acknowledged by operator
GET    /api/alerts/stats                 # Alert stats: count by severity, by day
```

### 2.6 Actions

```
POST   /api/actions/blackhole            # { ip: "x.x.x.x" } — manual blackhole
POST   /api/actions/unblackhole          # { ip: "x.x.x.x" } — manual remove
POST   /api/actions/test-email           # Send test email to both NOC groups
```

### 2.7 Settings

```
GET    /api/settings/mail                # Get mail configs (both NOC groups)
PUT    /api/settings/mail/{type}         # Update mail config (hosting_noc | isp_noc)
POST   /api/settings/mail/{type}/test    # Send test email
GET    /api/settings/general             # Global defaults (multiplier, window, etc.)
PUT    /api/settings/general             # Update global defaults
```

---

## 3. Component Design

### 3.1 Poller Service (`services/poller.py`)

The poller is the heartbeat of the system. It runs as a Celery periodic task every 5 seconds.

```
┌─────────────────────────────────────────────────────────┐
│                    Polling Cycle                         │
│                                                          │
│  1. Load all active CHR nodes from DB                    │
│  2. For each CHR (parallel via asyncio.gather):          │
│     a. Connect via RouterOS API                          │
│     b. Take /ip/accounting/snapshot                      │
│     c. Read snapshot data                                │
│     d. Aggregate per destination IP                      │
│     e. Calculate bps/pps from delta since last poll      │
│  3. Write traffic_samples to PostgreSQL (batch insert)   │
│  4. Publish to Redis pub/sub for WebSocket consumers     │
│  5. Trigger detection task for each updated IP           │
└─────────────────────────────────────────────────────────┘
```

**RouterOS Accounting Setup (prerequisite on each CHR):**
```routeros
/ip accounting set enabled=yes threshold=4096
/ip accounting web-access set accessible-via-web=yes
```

### 3.2 Detector Service (`services/detector.py`)

Runs after each polling cycle. Evaluates each IP against its baseline.

```python
class SpikeDetector:
    """
    Per-IP spike detection with EWMA baseline and configurable thresholds.
    
    State transitions:
      NORMAL → ALERT:       spike sustained for eval_window
      ALERT → BLACKHOLED:   auto_blackhole enabled (or manual)
      BLACKHOLED → RECOVERING: blackhole duration expires
      RECOVERING → NORMAL:  traffic below threshold for 60s
      RECOVERING → ALERT:   spike returns during recovery
    """
    
    async def evaluate(self, ip: MonitoredIP, sample: TrafficSample) -> StateTransition | None:
        # 1. Update baseline (skip if currently blackholed)
        # 2. Compare current vs threshold
        # 3. Check spike persistence (eval_window)
        # 4. Return state transition if applicable
        pass
```

### 3.3 Mitigator Service (`services/mitigator.py`)

Pushes blackhole routes to the target CHR via RouterOS API.

```python
class Mitigator:
    async def blackhole(self, ip: str, chr_node: CHRNode) -> bool:
        """Push /ip/route add dst-address={ip}/32 type=blackhole comment=CHRGuard"""
        async with routeros_connect(chr_node) as api:
            await api('/ip/route/add', **{
                'dst-address': f'{ip}/32',
                'type': 'blackhole',
                'comment': f'CHRGuard auto-blackhole {datetime.utcnow().isoformat()}'
            })
        return True
    
    async def unblackhole(self, ip: str, chr_node: CHRNode) -> bool:
        """Find and remove the CHRGuard blackhole route"""
        async with routeros_connect(chr_node) as api:
            routes = await api('/ip/route/print', **{
                '?dst-address': f'{ip}/32',
                '?type': 'blackhole',
                '?comment': 'CHRGuard*'
            })
            for route in routes:
                await api('/ip/route/remove', **{'.id': route['.id']})
        return True
```

### 3.4 Alerter Service (`services/alerter.py`)

Sends dual emails with different templates and tones.

```python
class Alerter:
    async def dispatch(self, alert: Alert, ip: MonitoredIP, pool: IPPool, chr: CHRNode):
        # 1. Render hosting NOC template (technical, detailed)
        hosting_html = self.render_hosting_template(alert, ip, pool, chr)
        
        # 2. Render ISP NOC template (formal, action-oriented)
        isp_html = self.render_isp_template(alert, ip, pool, chr)
        
        # 3. Send both concurrently
        hosting_config = await self.get_mail_config('hosting_noc')
        isp_config = await self.get_mail_config('isp_noc')
        
        await asyncio.gather(
            self.send_email(hosting_config, hosting_html, subject_hosting),
            self.send_email(isp_config, isp_html, subject_isp),
        )
        
        # 4. Update alert record with message IDs
```

### 3.5 WebSocket Manager (`api/ws.py`)

```python
class WSManager:
    """
    Manages WebSocket connections and broadcasts Redis pub/sub messages.
    
    Channels:
      chrguard:traffic   — per-IP traffic updates (5s interval)
      chrguard:alerts    — new alert notifications
      chrguard:state     — IP state transitions
    """
    
    def __init__(self):
        self.connections: set[WebSocket] = set()
        self.redis_sub = None
    
    async def broadcast(self, message: dict):
        dead = set()
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except WebSocketDisconnect:
                dead.add(ws)
        self.connections -= dead
```

---

## 4. Configuration Schema

### 4.1 Environment Variables (`.env`)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://chrguard:password@localhost:5432/chrguard

# Redis
REDIS_URL=redis://localhost:6379/0

# Security
SECRET_KEY=generate-a-random-64-char-hex-string
ENCRYPTION_KEY=generate-a-random-32-byte-base64-key

# Defaults
DEFAULT_MULTIPLIER=3.0
DEFAULT_EVAL_WINDOW_SEC=30
DEFAULT_BLACKHOLE_DURATION_SEC=600
BASELINE_EWMA_SPAN=720

# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
POLL_INTERVAL_SEC=5

# Data Retention
TRAFFIC_RETENTION_DAYS=30
ALERT_RETENTION_DAYS=90
```

---

## 5. Error Handling Strategy

### 5.1 CHR Connection Failures

```
CHR unreachable
  → Mark CHR status = "offline"
  → Emit WebSocket state change
  → Skip polling for this CHR
  → Retry on next cycle
  → After 3 consecutive failures: send degraded-monitoring alert email
```

### 5.2 Polling Failures

```
Accounting snapshot fails
  → Log error with CHR details
  → Carry forward last known traffic values (mark as stale)
  → Do NOT update baseline with stale data
  → Retry on next cycle
```

### 5.3 Blackhole Push Failures

```
Route push fails
  → Log error
  → Retry up to 3 times with 2s backoff
  → If all retries fail: send alert with action_taken="blackhole_failed"
  → Admin must manually intervene
```

### 5.4 Email Delivery Failures

```
SMTP send fails
  → Queue for retry (exponential backoff: 10s, 30s, 60s)
  → After 3 failures: log as failed, mark alert email_status="failed"
  → Alert is still valid — mitigation proceeds regardless of email status
```

---

## 6. Performance Considerations

### 6.1 Database

- **Traffic samples**: partitioned by `sampled_at` (daily partitions) with auto-drop after retention period
- **Batch inserts**: all samples from a polling cycle inserted in a single `INSERT ... VALUES` statement
- **Indexes**: composite index on `(ip_id, sampled_at DESC)` for time-range queries
- **Connection pool**: async SQLAlchemy with pool_size=10, max_overflow=20

### 6.2 Redis

- **Traffic counters**: `HSET chrguard:traffic:{ip} bps_in {value} bps_out {value} pps_in {value}` with 60s TTL
- **Baseline cache**: `SET chrguard:baseline:{ip} {ewma_value}` — persisted to DB every 5 minutes
- **Pub/sub**: separate channels for traffic, alerts, state changes to avoid noisy broadcasts

### 6.3 Polling Optimization

- All CHRs polled concurrently via `asyncio.gather`
- RouterOS API connections pooled (kept alive between cycles)
- Accounting data delta-calculated from previous snapshot to derive rates
- Max polling cycle time budget: 4 seconds (with 5s interval, leaves 1s buffer)

---

## 7. Testing Strategy

| Layer | Tool | Focus |
|-------|------|-------|
| Unit | pytest | Baseline EWMA math, spike detection logic, state machine transitions |
| Integration | pytest + testcontainers | DB queries, Redis pub/sub, Celery task chains |
| API | httpx + pytest | All REST endpoints, auth flows, validation |
| RouterOS Mock | Custom mock server | Simulated RouterOS API responses for polling tests |
| E2E | Playwright | Dashboard renders, WebSocket updates, form submissions |
| Load | Locust | 5,000 IPs × 5s polling cycle performance |
