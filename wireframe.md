# Wireframes — Xiguard

## Design Language

- **Theme**: Dark NOC-grade interface (charcoal background, muted borders, high-contrast status colors)
- **Color Coding**: 
  - `NORMAL` → green (#22c55e)
  - `ALERT` → amber (#f59e0b) with pulse animation
  - `BLACKHOLED` → red (#ef4444) 
  - `RECOVERING` → blue (#3b82f6)
  - `OFFLINE` → gray (#6b7280)
- **Typography**: Monospace for IPs/traffic values, sans-serif for labels
- **Layout**: Fixed sidebar (240px) + fluid content area

---

## 1. Login Screen

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│                                                              │
│                                                              │
│                                                              │
│                    ┌──────────────────────┐                   │
│                    │                      │                   │
│                    │     ◆ Xiguard       │                   │
│                    │     MikroTik DDoS    │                   │
│                    │     Monitoring       │                   │
│                    │                      │                   │
│                    │  ┌────────────────┐  │                   │
│                    │  │ Username       │  │                   │
│                    │  └────────────────┘  │                   │
│                    │                      │                   │
│                    │  ┌────────────────┐  │                   │
│                    │  │ Password       │  │                   │
│                    │  └────────────────┘  │                   │
│                    │                      │                   │
│                    │  ┌────────────────┐  │                   │
│                    │  │    Sign In     │  │                   │
│                    │  └────────────────┘  │                   │
│                    │                      │                   │
│                    └──────────────────────┘                   │
│                                                              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Dashboard (Main Monitoring View)

This is the primary screen. NOC operators will have this open 24/7.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ Xiguard                                              admin ▼  │ 🔔 3    │
├────────────────┬─────────────────────────────────────────────────────────────┤
│                │                                                             │
│  ◉ Dashboard   │  CHR Node Health                                            │
│                │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  □ CHR Nodes   │  │ ● Rajpura   │ │ ● Mumbai    │ │ ○ Pune      │           │
│                │  │ 768 IPs     │ │ 512 IPs     │ │ OFFLINE     │           │
│  □ IP Pools    │  │ 2ms poll    │ │ 5ms poll    │ │ last: 3m ago│           │
│                │  └─────────────┘ └─────────────┘ └─────────────┘           │
│  □ Alerts      │                                                             │
│                │  ┌──────────────────────────────────────────────────────┐   │
│  □ Settings    │  │  Aggregate Inbound Traffic                     1h ▼ │   │
│                │  │                                                      │   │
│                │  │  1.2 Gbps ┤                              ╱╲         │   │
│                │  │           ┤                            ╱    ╲        │   │
│                │  │  800 Mbps ┤       ╱╲                 ╱      ╲       │   │
│                │  │           ┤     ╱    ╲             ╱         ╲      │   │
│                │  │  400 Mbps ┤───╱───────╲──────────╱────────────╲──── │   │
│                │  │           ┤ ╱           ╲      ╱               ╲    │   │
│                │  │    0 Mbps ┤╱              ╲──╱                      │   │
│                │  │           ┼───┬───┬───┬───┬───┬───┬───┬───┬───┬──  │   │
│                │  │           10:00   10:15   10:30   10:45   11:00     │   │
│                │  │                                                      │   │
│                │  │  ── baseline    ── actual    ▓▓ above threshold      │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
│                │  ┌───────────────────────────────┐ ┌────────────────────┐   │
│                │  │ IP Status Grid          filter │ │ Live Alert Feed    │   │
│                │  │                                │ │                    │   │
│                │  │ ┌──────────────────────────┐   │ │ ● 10:31 CRITICAL  │   │
│                │  │ │ 162.141.0.15      ALERT  │   │ │   162.141.0.15    │   │
│                │  │ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓░░ 1.2 Gbps│   │ │   DDoS detected   │   │
│                │  │ │ baseline: 50 Mbps  25.0× │   │ │   25× baseline    │   │
│                │  │ │        [Blackhole] [View] │   │ │                    │   │
│                │  │ └──────────────────────────┘   │ │ ● 10:28 WARNING   │   │
│                │  │ ┌──────────────────────────┐   │ │   162.141.0.44    │   │
│                │  │ │ 162.141.0.44    NORMAL   │   │ │   Spike detected  │   │
│                │  │ │ ▓▓▓░░░░░░░░░░░  120 Mbps│   │ │   3.2× baseline   │   │
│                │  │ │ baseline: 45 Mbps  2.7×  │   │ │                    │   │
│                │  │ │                    [View] │   │ │ ○ 10:25 INFO      │   │
│                │  │ └──────────────────────────┘   │ │   162.141.0.90    │   │
│                │  │ ┌──────────────────────────┐   │ │   Blackhole lifted │   │
│                │  │ │ 162.141.0.90 BLACKHOLED  │   │ │   Traffic normal   │   │
│                │  │ │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  0 bps  │   │ │                    │   │
│                │  │ │ blackholed 6m ago         │   │ │ ● 10:20 CRITICAL  │   │
│                │  │ │    [Unblackhole]   [View] │   │ │   162.141.0.90    │   │
│                │  │ └──────────────────────────┘   │ │   DDoS detected   │   │
│                │  │                                │ │                    │   │
│                │  │ showing 3 of 1280 IPs          │ │  [View All Alerts] │   │
│                │  └───────────────────────────────┘ └────────────────────┘   │
│                │                                                             │
│                │  Top Attacked IPs (Last 24h)                                │
│                │  ┌──────────────────────────────────────────────────────┐   │
│                │  │ IP              │ Attacks │ Total Duration │ Status  │   │
│                │  ├─────────────────┼─────────┼────────────────┼─────────│   │
│                │  │ 162.141.0.15    │    12   │    4h 23m      │ ALERT   │   │
│                │  │ 162.141.0.90    │     8   │    2h 10m      │ BLKHLD  │   │
│                │  │ 162.141.0.201   │     5   │    1h 45m      │ NORMAL  │   │
│                │  │ 151.243.144.12  │     3   │      48m       │ NORMAL  │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
├────────────────┴─────────────────────────────────────────────────────────────┤
│ Polling: 5s │ Last cycle: 1.8s │ 1,280 IPs monitored │ 2 alerts active     │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. CHR Nodes Management

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ Xiguard                                              admin ▼  │ 🔔 3    │
├────────────────┬─────────────────────────────────────────────────────────────┤
│                │                                                             │
│  □ Dashboard   │  CHR Nodes                                    [+ Add Node] │
│                │                                                             │
│  ◉ CHR Nodes   │  ┌────────────────────────────────────────────────────────┐ │
│                │  │ Name          │ Host       │ Port │ IPs  │ Status │ ⚡  │ │
│  □ IP Pools    │  ├───────────────┼────────────┼──────┼──────┼────────┼────│ │
│                │  │ Rajpura Edge  │ 10.0.0.1   │ 8728 │  768 │ ● ON   │ ✎ 🗑│ │
│  □ Alerts      │  │ Mumbai Core   │ 10.0.1.1   │ 8728 │  512 │ ● ON   │ ✎ 🗑│ │
│                │  │ Pune Transit  │ 10.0.2.1   │ 8729 │  256 │ ○ OFF  │ ✎ 🗑│ │
│  □ Settings    │  └────────────────────────────────────────────────────────┘ │
│                │                                                             │
│                │                                                             │
│                │  ═══════════════════════════════════════════════════════    │
│                │                                                             │
│                │  ADD / EDIT CHR NODE                                        │
│                │  ┌──────────────────────────────────────────────────────┐   │
│                │  │                                                      │   │
│                │  │  Name          ┌──────────────────────────────────┐  │   │
│                │  │                │ Rajpura Edge CHR                 │  │   │
│                │  │                └──────────────────────────────────┘  │   │
│                │  │                                                      │   │
│                │  │  Host          ┌──────────────────────────────────┐  │   │
│                │  │                │ 10.0.0.1                         │  │   │
│                │  │                └──────────────────────────────────┘  │   │
│                │  │                                                      │   │
│                │  │  API Port      ┌──────────┐                         │   │
│                │  │                │ 8728     │   ☐ Use SSL (8729)      │   │
│                │  │                └──────────┘                         │   │
│                │  │                                                      │   │
│                │  │  Username      ┌──────────────────────────────────┐  │   │
│                │  │                │ xiguard                         │  │   │
│                │  │                └──────────────────────────────────┘  │   │
│                │  │                                                      │   │
│                │  │  Password      ┌──────────────────────────────────┐  │   │
│                │  │                │ ••••••••                         │  │   │
│                │  │                └──────────────────────────────────┘  │   │
│                │  │                                                      │   │
│                │  │  Description   ┌──────────────────────────────────┐  │   │
│                │  │                │ Primary edge router — Rajpura DC │  │   │
│                │  │                └──────────────────────────────────┘  │   │
│                │  │                                                      │   │
│                │  │       [Test Connection]    [Cancel]    [Save Node]   │   │
│                │  │                                                      │   │
│                │  │  ┌──────────────────────────────────────────────┐    │   │
│                │  │  │ ● Connection successful — RouterOS 7.14.3   │    │   │
│                │  │  │   Uptime: 45d 12h, CPU: 12%, RAM: 34%       │    │   │
│                │  │  └──────────────────────────────────────────────┘    │   │
│                │  │                                                      │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
└────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 4. IP Pools Management

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ Xiguard                                              admin ▼  │ 🔔 3    │
├────────────────┬─────────────────────────────────────────────────────────────┤
│                │                                                             │
│  □ Dashboard   │  IP Pools                                     [+ Add Pool] │
│                │                                                             │
│  □ CHR Nodes   │  ┌────────────────────────────────────────────────────────┐ │
│                │  │ CIDR             │ CHR Node     │ IPs │ Multi │ Auto │ │ │
│  ◉ IP Pools    │  ├──────────────────┼──────────────┼─────┼───────┼──────│ │ │
│                │  │ 162.141.0.0/24   │ Rajpura Edge │ 256 │  3.0× │  ✓   │▶│ │
│  □ Alerts      │  │ 162.141.1.0/24   │ Rajpura Edge │ 256 │  3.0× │  ✓   │▶│ │
│                │  │ 162.141.2.0/24   │ Rajpura Edge │ 256 │  5.0× │  ✓   │▶│ │
│  □ Settings    │  │ 151.243.144.0/24 │ Mumbai Core  │ 256 │  3.0× │  ✗   │▶│ │
│                │  │ 151.243.146.0/24 │ Mumbai Core  │ 256 │  3.0× │  ✓   │▶│ │
│                │  └────────────────────────────────────────────────────────┘ │
│                │                                                             │
│                │  ═══ Pool Detail: 162.141.0.0/24 ═══════════════════════   │
│                │                                                             │
│                │  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│                │  │ 256 Total  │  │  2 ALERT   │  │ 1 BLKHLD   │            │
│                │  │    IPs     │  │            │  │            │            │
│                │  └────────────┘  └────────────┘  └────────────┘            │
│                │                                                             │
│                │  Settings                                                   │
│                │  ┌──────────────────────────────────────────────────────┐   │
│                │  │ Multiplier:     [3.0×    ▼]  Eval Window: [30s   ▼] │   │
│                │  │ Auto-Blackhole: [✓ On     ]  Duration:    [10min ▼] │   │
│                │  │                                          [Save]     │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
│                │  IPs in Pool                        filter: [All States ▼] │
│                │  ┌──────────────────────────────────────────────────────┐   │
│                │  │ IP Address      │ State     │ Current  │ Baseline   │   │
│                │  ├─────────────────┼───────────┼──────────┼────────────│   │
│                │  │ 162.141.0.1     │ ● NORMAL  │  12 Mbps │   15 Mbps │   │
│                │  │ 162.141.0.2     │ ● NORMAL  │   8 Mbps │   10 Mbps │   │
│                │  │ ...             │           │          │            │   │
│                │  │ 162.141.0.15    │ ◉ ALERT   │ 1.2 Gbps │   50 Mbps │   │
│                │  │                 │           │   ▼ expand             │   │
│                │  │   ┌──────────────────────────────────────────────┐  │   │
│                │  │   │ Traffic: 162.141.0.15              last 1h  │  │   │
│                │  │   │                                              │  │   │
│                │  │   │  1.2G ┤                         ╱──          │  │   │
│                │  │   │       ┤                       ╱               │  │   │
│                │  │   │  800M ┤                     ╱                 │  │   │
│                │  │   │       ┤                   ╱                   │  │   │
│                │  │   │  400M ┤                 ╱                     │  │   │
│                │  │   │       ┤───────────────╱── baseline (50M)      │  │   │
│                │  │   │    0  ┤──────────────────────────────────     │  │   │
│                │  │   │       10:00    10:15    10:30    11:00        │  │   │
│                │  │   │                                              │  │   │
│                │  │   │  [Blackhole Now]  [View Full History]         │  │   │
│                │  │   └──────────────────────────────────────────────┘  │   │
│                │  │ 162.141.0.16    │ ● NORMAL  │  22 Mbps │   20 Mbps │   │
│                │  │ ...             │           │          │            │   │
│                │  │ 162.141.0.90    │ ◉ BLKHLD  │   0 bps  │   35 Mbps │   │
│                │  │ ...             │           │          │            │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
└────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 5. Alert History

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ Xiguard                                              admin ▼  │ 🔔 3    │
├────────────────┬─────────────────────────────────────────────────────────────┤
│                │                                                             │
│  □ Dashboard   │  Alerts                                                     │
│                │                                                             │
│  □ CHR Nodes   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│                │  │ 47 Total │  │ 12 CRIT  │  │ 23 WARN  │  │ 12 INFO  │   │
│  □ IP Pools    │  │ (24h)    │  │          │  │          │  │          │   │
│                │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│  ◉ Alerts      │                                                             │
│                │  Filters                                                    │
│  □ Settings    │  ┌──────────────────────────────────────────────────────┐   │
│                │  │ Severity: [All ▼]  IP: [________]  Date: [Last 24h▼]│   │
│                │  │ Type: [All ▼]      Pool: [All ▼]   [Apply]  [Reset] │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
│                │  ┌──────────────────────────────────────────────────────┐   │
│                │  │ Time     │Sev │ IP            │ Type        │ Action │   │
│                │  ├──────────┼────┼───────────────┼─────────────┼────────│   │
│                │  │ 10:31:15 │ !! │ 162.141.0.15  │ DDoS Det.   │ BLKHLD │   │
│                │  │          │    │ 1.2G vs 50M baseline (25×)  │        │   │
│                │  │          │    │ ✉ Hosting: ✓  ISP: ✓        │  [ACK] │   │
│                │  ├──────────┼────┼───────────────┼─────────────┼────────│   │
│                │  │ 10:28:44 │ !  │ 162.141.0.44  │ Spike Det.  │ ALERT  │   │
│                │  │          │    │ 144M vs 45M baseline (3.2×) │        │   │
│                │  │          │    │ ✉ Hosting: ✓  ISP: ✓        │  [ACK] │   │
│                │  ├──────────┼────┼───────────────┼─────────────┼────────│   │
│                │  │ 10:25:00 │ ℹ  │ 162.141.0.90  │ Recovered   │   —    │   │
│                │  │          │    │ Traffic normalized after BH  │        │   │
│                │  │          │    │ ✉ Hosting: ✓  ISP: ✓        │   ✓    │   │
│                │  ├──────────┼────┼───────────────┼─────────────┼────────│   │
│                │  │ 10:20:12 │ !! │ 162.141.0.90  │ DDoS Det.   │ BLKHLD │   │
│                │  │          │    │ 890M vs 35M baseline (25×)  │        │   │
│                │  │          │    │ ✉ Hosting: ✓  ISP: ✓        │   ✓    │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
│                │  ═══ Alert Detail (expanded) ═══════════════════════════   │
│                │  ┌──────────────────────────────────────────────────────┐   │
│                │  │ Alert ID:   a3f2e1d0-...                             │   │
│                │  │ IP:         162.141.0.15                             │   │
│                │  │ Pool:       162.141.0.0/24 → Rajpura Edge CHR        │   │
│                │  │ Detected:   2026-05-24 10:31:15 UTC                  │   │
│                │  │ Baseline:   50,000,000 bps (50 Mbps)                 │   │
│                │  │ Peak:       1,250,000,000 bps (1.25 Gbps)            │   │
│                │  │ Multiplier: 25.0× (threshold: 3.0×)                  │   │
│                │  │ Action:     Auto-blackhole applied                    │   │
│                │  │                                                      │   │
│                │  │ Emails Sent:                                          │   │
│                │  │   Hosting NOC: ✓ noc@xitenodes.com (10:31:16)        │   │
│                │  │   ISP NOC:     ✓ noc@gtel.in (10:31:16)              │   │
│                │  │                                                      │   │
│                │  │ [View Traffic Graph]  [View Email Content]            │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
└────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 6. Settings — Mail Configuration

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ Xiguard                                              admin ▼  │ 🔔 3    │
├────────────────┬─────────────────────────────────────────────────────────────┤
│                │                                                             │
│  □ Dashboard   │  Settings → Mail Configuration                             │
│                │                                                             │
│  □ CHR Nodes   │  ┌─────────────────────┬─────────────────────┐             │
│                │  │   Hosting NOC ◉     │   ISP NOC  ○        │             │
│  □ IP Pools    │  └─────────────────────┴─────────────────────┘             │
│                │                                                             │
│  □ Alerts      │  ┌──────────────────────────────────────────────────────┐   │
│                │  │                                                      │   │
│  ◉ Settings    │  │  ☐ Enabled                                           │   │
│    ├ General   │  │                                                      │   │
│    └ Mail ◉    │  │  SMTP Host     ┌──────────────────────────────────┐  │   │
│                │  │                │ postal.netpool.in                │  │   │
│                │  │                └──────────────────────────────────┘  │   │
│                │  │                                                      │   │
│                │  │  SMTP Port     ┌──────┐   ☑ Use TLS                  │   │
│                │  │                │ 587  │                              │   │
│                │  │                └──────┘                              │   │
│                │  │                                                      │   │
│                │  │  Username      ┌──────────────────────────────────┐  │   │
│                │  │                │ xiguard@netpool.in              │  │   │
│                │  │                └──────────────────────────────────┘  │   │
│                │  │                                                      │   │
│                │  │  Password      ┌──────────────────────────────────┐  │   │
│                │  │                │ ••••••••                         │  │   │
│                │  │                └──────────────────────────────────┘  │   │
│                │  │                                                      │   │
│                │  │  From Address  ┌──────────────────────────────────┐  │   │
│                │  │                │ alerts@xiguard.netpool.in       │  │   │
│                │  │                └──────────────────────────────────┘  │   │
│                │  │                                                      │   │
│                │  │  To (one per line)                                    │   │
│                │  │  ┌──────────────────────────────────────────────┐    │   │
│                │  │  │ noc@xitenodes.com                           │    │   │
│                │  │  │ rudranil@netpool.in                         │    │   │
│                │  │  │                                              │    │   │
│                │  │  └──────────────────────────────────────────────┘    │   │
│                │  │                                                      │   │
│                │  │  CC (optional)                                        │   │
│                │  │  ┌──────────────────────────────────────────────┐    │   │
│                │  │  │ ops@netpool.in                               │    │   │
│                │  │  │                                              │    │   │
│                │  │  └──────────────────────────────────────────────┘    │   │
│                │  │                                                      │   │
│                │  │  Email Preview (Hosting NOC template):               │   │
│                │  │  ┌──────────────────────────────────────────────┐    │   │
│                │  │  │ Subject: [Xiguard ALERT] DDoS detected     │    │   │
│                │  │  │          on {ip_address}                     │    │   │
│                │  │  │                                              │    │   │
│                │  │  │ ALERT: Volumetric DDoS Attack Detected      │    │   │
│                │  │  │                                              │    │   │
│                │  │  │ Target IP:    {ip_address}                   │    │   │
│                │  │  │ Pool:         {pool_cidr}                   │    │   │
│                │  │  │ CHR Node:     {chr_name}                    │    │   │
│                │  │  │ ...                                          │    │   │
│                │  │  └──────────────────────────────────────────────┘    │   │
│                │  │                                                      │   │
│                │  │       [Send Test Email]     [Cancel]     [Save]       │   │
│                │  │                                                      │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
└────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 7. Settings — General

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ◆ Xiguard                                              admin ▼  │ 🔔 3    │
├────────────────┬─────────────────────────────────────────────────────────────┤
│                │                                                             │
│  □ Dashboard   │  Settings → General                                         │
│                │                                                             │
│  □ CHR Nodes   │  Detection Defaults                                         │
│                │  ┌──────────────────────────────────────────────────────┐   │
│  □ IP Pools    │  │                                                      │   │
│                │  │  Default Multiplier         ┌──────┐                 │   │
│  □ Alerts      │  │  (spike = baseline × N)     │ 3.0  │ ×               │   │
│                │  │                              └──────┘                 │   │
│  ◉ Settings    │  │                                                      │   │
│    ├ General ◉ │  │  Evaluation Window          ┌──────┐                 │   │
│    └ Mail      │  │  (sustained spike duration) │  30  │ seconds         │   │
│                │  │                              └──────┘                 │   │
│                │  │                                                      │   │
│                │  │  Baseline EWMA Span          ┌──────┐                │   │
│                │  │  (samples for averaging)     │ 720  │ samples        │   │
│                │  │  (= 1 hour at 5s interval)   └──────┘                │   │
│                │  │                                                      │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
│                │  Blackhole Defaults                                         │
│                │  ┌──────────────────────────────────────────────────────┐   │
│                │  │                                                      │   │
│                │  │  Auto-Blackhole              ┌──────────┐            │   │
│                │  │                              │ Enabled ▼│            │   │
│                │  │                              └──────────┘            │   │
│                │  │                                                      │   │
│                │  │  Blackhole Duration           ┌──────┐               │   │
│                │  │                              │  600  │ seconds       │   │
│                │  │                              └──────┘ (10 min)       │   │
│                │  │                                                      │   │
│                │  │  Recovery Observation         ┌──────┐               │   │
│                │  │  (monitor after unblackhole) │   60  │ seconds       │   │
│                │  │                              └──────┘                │   │
│                │  │                                                      │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
│                │  Polling                                                     │
│                │  ┌──────────────────────────────────────────────────────┐   │
│                │  │                                                      │   │
│                │  │  Poll Interval               ┌──────┐                │   │
│                │  │                              │   5   │ seconds       │   │
│                │  │                              └──────┘                │   │
│                │  │                                                      │   │
│                │  │  Alert Dedup Window           ┌──────┐               │   │
│                │  │  (no repeat for same IP)     │  300  │ seconds       │   │
│                │  │                              └──────┘ (5 min)        │   │
│                │  │                                                      │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
│                │  Data Retention                                             │
│                │  ┌──────────────────────────────────────────────────────┐   │
│                │  │  Traffic Samples:   30 days                          │   │
│                │  │  Alert History:     90 days                          │   │
│                │  │  Audit Log:        365 days                          │   │
│                │  │  DB Size:          ~12 GB (current)                  │   │
│                │  └──────────────────────────────────────────────────────┘   │
│                │                                                             │
│                │                             [Reset to Defaults]    [Save]   │
│                │                                                             │
└────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 8. Alert Email Previews

### 8.1 Hosting NOC Email (HTML rendered)

```
┌──────────────────────────────────────────────────────────────────┐
│ From: alerts@xiguard.netpool.in                                 │
│ To: noc@xitenodes.com                                            │
│ Subject: [Xiguard ALERT] DDoS detected on 162.141.0.15         │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  ⚠  VOLUMETRIC DDoS ATTACK DETECTED                      │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Target IP:       162.141.0.15                                   │
│  Pool:            162.141.0.0/24                                 │
│  CHR Node:        Rajpura Edge CHR (10.0.0.1)                    │
│  Detected:        2026-05-24 10:31:15 UTC                        │
│                                                                  │
│  ┌─── Traffic Analysis ───────────────────────────────────────┐  │
│  │  Baseline:     50 Mbps                                     │  │
│  │  Current:      1.25 Gbps                                   │  │
│  │  Multiplier:   25.0× threshold (configured: 3.0×)          │  │
│  │  Peak:         1.25 Gbps                                   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Action Taken:    ● Auto-Blackhole Applied                       │
│  Blackhole Exp:   2026-05-24 10:41:15 UTC (10 min)               │
│                                                                  │
│  ─────────────────────────────────────                           │
│  Automated alert from Xiguard                                   │
│  NETPOOL Technologies Pvt. Ltd.                                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 8.2 ISP NOC Email (formal)

```
┌──────────────────────────────────────────────────────────────────┐
│ From: alerts@xiguard.netpool.in                                 │
│ To: noc@gtel.in                                                  │
│ Subject: [URGENT] Manual scrubbing requested — 162.141.0.15      │
│          — AS215228                                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Dear NOC Team,                                                  │
│                                                                  │
│  We are observing a possible volumetric DDoS attack targeting    │
│  the following IP address on our network:                        │
│                                                                  │
│      IP Address:       162.141.0.15                              │
│      AS Number:        AS215228 (NETPOOL Technologies)           │
│      Approx. Volume:   ~1.25 Gbps inbound                       │
│      Detection Time:   2026-05-24 10:31:15 UTC                   │
│      Attack Type:      Volumetric (25× baseline deviation)       │
│                                                                  │
│  We kindly request immediate manual scrubbing for this IP        │
│  with immediate effect. We have applied a local blackhole        │
│  as an interim measure.                                          │
│                                                                  │
│  Please acknowledge receipt of this request and provide          │
│  an estimated time for scrubbing activation.                     │
│                                                                  │
│  Regards,                                                        │
│  NETPOOL Technologies NOC                                        │
│  noc@netpool.in | +91-XXXXXXXXXX                                 │
│  AS215228 | https://netpool.in                                   │
│                                                                  │
│  ─────────────────────────────────────                           │
│  Automated alert — Xiguard DDoS Monitoring                      │
│  Ref: ALT-a3f2e1d0                                               │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 9. Responsive Behavior Notes

| Breakpoint | Behavior |
|------------|----------|
| ≥1280px | Full layout: sidebar + content side by side |
| 1024–1279px | Sidebar collapses to icons only (64px) |
| 768–1023px | Sidebar becomes hamburger menu overlay |
| <768px | Not a primary target (NOC panel), but forms stack vertically |

---

## 10. Interaction Patterns

### 10.1 Real-time Updates
- Dashboard traffic data updates every 5 seconds via WebSocket (no page refresh)
- IP cards animate smoothly between states (color transitions, pulse on ALERT)
- Alert feed auto-scrolls to newest, with "X new alerts" banner if scrolled up

### 10.2 Blackhole Actions
- Manual blackhole shows confirmation dialog: "Blackhole 162.141.0.15? This will drop all traffic to this IP."
- Success: toast notification + card updates to BLACKHOLED state
- Failure: error toast with retry option

### 10.3 CHR Connection Test
- Shows spinner while testing
- Success: green banner with RouterOS version, uptime, CPU/RAM
- Failure: red banner with error message (timeout, auth failed, unreachable)

### 10.4 Email Test
- Sends to configured recipients with "[TEST]" prefix in subject
- Shows delivery status inline (sent/failed with error detail)
