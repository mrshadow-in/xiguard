# Xiguard showcase — internal guide

> **Internal — showcase branch only.** This branch is a self-contained demo of
> Xiguard. Never merge it into `main` and never deploy it: it ships demo
> passwords and keys in `.env` on purpose.

This guide is written so you can run the showcase alone, with nobody to call.
Read it once end to end at home, do one full rehearsal, and keep the
[quick reference card](#quick-reference-card) open on the day.

---

## 1. What this branch is

A normal Xiguard install plus three extra containers, all started by one command:

| Container | What it is |
|---|---|
| `chr` | A **real MikroTik CHR** (RouterOS 7.20.4) booted inside the container with QEMU. Next to it runs a **traffic simulator** that streams NetFlow for ~440 customer servers on two prefixes, and an **attack control panel** to launch a DDoS on any of them. |
| `mailpit` | A local inbox. Both NOC alert emails land here instead of going out on the internet. |
| `showcase-init` | A one-shot setup job. It configures the CHR and registers it in Xiguard with its IP pools and mailboxes, then tests a blackhole push. **No manual setup is needed.** |

Xiguard really logs into the CHR over the RouterOS API and really installs and
removes blackhole routes on it — you can watch them appear in the router's own
web interface (WebFig).

**Why the traffic is simulated:** a free (unlicensed) CHR is limited to 1 Mbps
per interface, while Xiguard only reacts to spikes above 10 Mbps. Real packets
pushed through the router could never show an attack, so the simulator sends
the flow records the router would export, which lets it show a 2.4 Gbps flood.
Everything stays on the laptop: no traffic or email leaves it.

### Addresses and logins

| What | Address | Login |
|---|---|---|
| Xiguard panel | <http://localhost:8088> | `admin` / `showcase` |
| Attack control panel | <http://localhost:8090> | — |
| NOC mailboxes (Mailpit) | <http://localhost:8025> | — |
| CHR WebFig (router UI) | <http://localhost:8081> | `xiguard` / `xiguard-demo` |
| CHR Winbox (optional) | `127.0.0.1:8291` | `xiguard` / `xiguard-demo` |

Simulated prefixes: `203.0.113.0/24` and `198.51.100.0/24` (documentation
ranges). The named servers you attack on stage live in `203.0.113.0/24`:

| Host | IP | Normal traffic |
|---|---|---|
| web-01 | 203.0.113.10 | ~45 Mbps |
| **game-01** (best demo target) | 203.0.113.11 | ~180 Mbps |
| api-01 | 203.0.113.12 | ~22 Mbps |
| cdn-01 | 203.0.113.13 | ~320 Mbps |
| mail-01 | 203.0.113.14 | ~6 Mbps |
| vps-01 | 203.0.113.15 | ~12 Mbps |

---

## 2. Before the day (at home, with internet)

### What the laptop needs

- **Docker Desktop** (Windows or macOS) or Docker Engine (Linux), recent version.
- **8 GB RAM or more.** In Docker Desktop → Settings → Resources, give Docker at
  least **4 GB** memory. (On Windows with WSL 2 this is automatic: half your RAM.)
- **~8 GB free disk** for images.
- **Git.**
- Intel/AMD or Apple Silicon both work. The router is emulated in software, so
  it boots in about 25 seconds on a desktop and up to 2–3 minutes on a slow laptop.

### First-time setup (takes 15–30 minutes, needs internet)

```bash
git clone --branch showcase https://github.com/mrshadow-in/xiguard.git xiguard-showcase
cd xiguard-showcase
docker compose up -d --build
```

Clone into a **new folder**, not an existing Xiguard checkout: this branch has
its own `.env`, and git will refuse to switch an existing checkout that already
has one. Always use `git clone` — do not download the ZIP from GitHub (see
[CRLF problem](#the-chr-container-keeps-restarting-and-its-log-mentions-set-illegal-option-or-no-such-file)).

Then watch the setup job until it says **SHOWCASE READY**:

```bash
docker compose logs -f showcase-init
```

Press `Ctrl+C` to stop watching (the stack keeps running).

### Do one full rehearsal

Run the whole [demo script](#4-the-demo-script) once. While you do it, **record
your screen** (Windows: `Win+Alt+R` with Xbox Game Bar; macOS: `Cmd+Shift+5`).
If anything fails on the day, you can play that recording instead.

When you're done: `docker compose down` (keeps everything for next time).

---

## 3. On the day — starting up

No internet is needed once the first build is done. **Do not** run
`--build` or `docker compose pull` at the venue.

1. Start Docker Desktop and wait until it says *Engine running*.
2. Open a terminal in the `xiguard-showcase` folder.
3. Start everything:

    ```bash
    docker compose up -d
    ```

4. Wait for **SHOWCASE READY** (usually under 2 minutes):

    ```bash
    docker compose logs -f showcase-init
    ```

5. Open the five browser tabs from the [table above](#addresses-and-logins) and log in.

**Start at least 10 minutes before you present.** On the very first start the
IPs also need a 2-minute warm-up (state `SAMPLING`) before Xiguard will react
to an attack. On later starts they're already armed.

Turn off sleep on the laptop for the day; a laptop that sleeps mid-demo pauses
every container.

---

## 4. The demo script

A complete run takes about 5 minutes. What you say is in *italics*.

1. **Xiguard dashboard** (<http://localhost:8088>). Every IP of both prefixes is
    listed with live traffic, refreshing every 5 seconds.
    *"Xiguard watches every IP on the network. These numbers come from the
    router's NetFlow export, and each IP has learned its own normal traffic."*
2. **CHR Nodes** page: `CHR-Showcase` is **online**. **Polling** page: one
    exporter is actively sending flows.
3. **WebFig** (<http://localhost:8081>, `xiguard` / `xiguard-demo`) →
    **IP → Routes**. There are no blackhole routes yet. Optionally show
    **IP → Traffic Flow**: the router exports to Xiguard.
4. **Attack panel** (<http://localhost:8090>): size **2.4 Gbps**, duration
    **60 s**, type *UDP DNS amplification* → **Attack** on **game-01**.
    *"A 2.4 gigabit flood just hit our game server. Nobody is touching anything."*
5. Back on the **dashboard**, within 20–30 seconds game-01 turns
    **ALERT → BLACKHOLED**. (Xiguard waits for the flood to last 15 seconds so
    short bursts never trigger it.)
6. **WebFig → IP → Routes** (refresh): a new route
    `203.0.113.11/32` blackhole, comment *Xiguard auto-blackhole …*.
    *"Xiguard logged into the router and dropped only this one address. Every
    other customer is unaffected."*
7. **Mailpit** (<http://localhost:8025>): two emails arrived at the same moment —
    the technical alert to Netpool's NOC, and the formal scrubbing request to the
    upstream ISP with the IP, AS number and attack size.
8. **Alerts** page in Xiguard: the DDoS alert and the *blackhole applied* event.
9. **Recovery** (2 minutes after the block): Xiguard removes the route
    (refresh WebFig — it's gone), the IP goes **RECOVERING**, and after 30 clean
    seconds back to **NORMAL**. A recovery email arrives in Mailpit.
    Fill the wait with the architecture or the technical overview PDF
    (`docs/Xiguard-Technical-Overview.pdf`, also in this folder).

### Optional extras

- **Whitelist:** click `203.0.113.10` (web-01) on the dashboard to open its
  page, press **Whitelist (no-BH)**, then attack it. It raises the alert and
  sends the emails, but is **not** blackholed — that's how critical servers are
  protected from automatic blocking. Press **Remove from whitelist** afterwards.
- **Manual control:** on any IP's page, press **Blackhole** and then
  **Unblackhole**; the route appears and disappears in WebFig.
- **Two attacks at once:** attack game-01 and cdn-01 together; each is
  handled independently.

### Showcase timings vs production

The showcase is tuned so a full cycle fits in a few minutes.

| Setting | Showcase | Production default |
|---|---|---|
| Warm-up before an IP is armed | 2 min | 10 min |
| Attack must last | 15 s | 30 s |
| Blackhole duration | 2 min | 10 min |
| Clean time before back to NORMAL | 30 s | 60 s |
| Repeat-email suppression per IP | 60 s | 5 min |

---

## 5. Stopping and resetting

| Goal | Command |
|---|---|
| Stop everything, keep data | `docker compose down` |
| Start again | `docker compose up -d` |
| Wipe everything and start fresh (IPs warm up again for 2 min) | `docker compose down -v` then `docker compose up -d` |
| Restart only the router + simulator | `docker compose restart chr` then `docker compose up -d showcase-init` |
| Re-run the setup job | `docker compose up -d showcase-init` |
| See what's running | `docker compose ps` |
| Logs of one container | `docker compose logs --tail 50 <name>` (`chr`, `api`, `worker`, `worker-email`, `flow-collector`, `showcase-init`) |

---

## 6. What can go wrong — and the fix

Start with `docker compose ps`. Every service should be **Up**, except
`showcase-init`, which should show **Exited (0)**. Then find your symptom below.

### Docker Desktop won't start: "The file cannot be accessed by the system"

The error names a socket file, for example
`...\AppData\Local\Docker\run\dockerInference` or
`...\AppData\Local\docker-secrets-engine\engine.sock`. This happened on the
development desktop. On some Windows builds, socket files left over from the
last run can't be deleted, so Docker Desktop crashes on start.

1. Quit Docker Desktop (tray icon → Quit; or end *Docker Desktop* in Task Manager).
2. In PowerShell, move the stale folders aside (they're recreated automatically):

    ```powershell
    Rename-Item "$env:LOCALAPPDATA\Docker\run" "run.old-$(Get-Date -Format HHmmss)"
    Rename-Item "$env:LOCALAPPDATA\docker-secrets-engine" "docker-secrets-engine.old-$(Get-Date -Format HHmmss)"
    ```

3. `wsl --shutdown`, then start Docker Desktop again.

If it still fails, **don't** click *Reset to factory defaults* on the day — it
deletes all images and you'd need internet to rebuild. Use
[Plan B: Docker inside WSL](#plan-b-run-docker-inside-wsl-windows) instead, or
play your rehearsal recording.

### "port is already allocated" / "address already in use"

Another program uses one of the ports: 8088, 8090, 8025, 8081, 8291 or 2055 (UDP).
Common culprits: another Xiguard stack, a local dev server, Jenkins/Tomcat, a VPN client.

- Windows: `netstat -ano | findstr ":8088 "` (use the port from the error) →
  note the PID in the last column → close that program (Task Manager → Details).
- macOS/Linux: `sudo lsof -i :8088`.
- Another Docker stack: `docker ps`, then stop it with `docker stop <name>`.

Then `docker compose up -d` again.

### `showcase-init` shows "Exited (1)" — the setup failed

Read why: `docker compose logs showcase-init`. The last line says
`[showcase] FAILED: …`:

- **"CHR API never answered"** — the router didn't finish booting in 15 minutes.
  Check `docker compose logs --tail 20 chr`: you should see `MikroTik Login:`.
  If not, the laptop is too slow or short on memory: close other apps, give
  Docker more memory, `docker compose restart chr`, then
  `docker compose up -d showcase-init`.
- **"database never became ready"** — check `docker compose logs --tail 30 api`.
  Usually fixed by `docker compose up -d` again.
- **"blackhole self-test FAILED"** — the router refused the route. Run
  `docker compose down -v` then `docker compose up -d` to start from a clean router.

The setup job is safe to re-run any number of times: `docker compose up -d showcase-init`.

### The dashboard is empty, or every IP shows 0 traffic

The flow path is broken. In Xiguard open **Polling**: is an exporter listed and
is the packet count rising?

- Check the simulator: `docker compose logs --tail 20 chr | grep simulator`.
  You want `exporting to …:2055, N packets so far`. If you see
  `waiting for flow collector`, run `docker compose up -d` (the collector
  isn't running) and check `docker compose logs flow-collector`.
- No IPs at all → `showcase-init` didn't finish; see above.

### I launched an attack and nothing happens

- **The IP is still `SAMPLING`.** Fresh IPs need 2 minutes of warm-up. Wait until
  the dashboard shows `NORMAL`.
- **The attack panel showed a red error.** It refuses near-idle IPs on purpose:
  Xiguard ignores IPs whose normal traffic is under 1 Mbps, so they would never
  be blackholed. Use a host from the table.
- **The IP is whitelisted** (it alerts but never blackholes). Un-whitelist it.
- Give it up to 30 seconds: the 15-second confirmation plus a poll or two.

### Blackhole happened, but no email in Mailpit

- The same IP was alerted less than 60 seconds ago — repeat emails are
  suppressed. Attack a different host or wait a minute.
- Someone changed **Settings → Mail** in the panel. The setup job never
  overwrites changed mail settings. To restore: `docker compose down -v` and start again.
- `docker compose logs --tail 30 worker-email`.

### Xiguard shows a "blackhole failed" alert

Xiguard couldn't install the route on the router and rolled the IP back to
`ALERT`. Check **CHR Nodes**: if `CHR-Showcase` is offline, run
`docker compose restart chr`, wait for `MikroTik Login:` in its log, then
`docker compose up -d showcase-init`.

### Login to the Xiguard panel fails

The login is `admin` / `showcase`. If `.env` was changed after the first start,
the original password still applies (the admin account is only created on an
empty database). Reset with `docker compose down -v` and start again.

### The Xiguard panel shows "502 Bad Gateway", doesn't load, or shows a different site

- Check the address: the panel is on **`http://localhost:8088`**, not plain
  `http://localhost`. Plain `localhost` (port 80) may show another program's
  page — on the development desktop it showed Windows' IIS welcome page.
- Right after `up`, the web frontend needs ~30 seconds. Wait and refresh. If it
  persists: `docker compose logs --tail 30 frontend caddy`.

### The CHR container keeps restarting and its log mentions "set: illegal option" or "no such file"

The project was copied with Windows line endings (for example downloaded as a
ZIP). Delete the folder and `git clone` it again as in section 2 — the
repository forces the correct line endings on clone.

### Everything is slow / the fan is loud

The router is emulated in software, which uses CPU. Close other heavy apps,
plug in the charger, and use the laptop's performance power mode. It does not
affect the demo's correctness, only how fast pages respond.

### The laptop went to sleep

Wake it, wait 30 seconds, refresh the browser tabs. If traffic doesn't resume:
`docker compose restart chr`, wait for `MikroTik Login:`, then
`docker compose up -d showcase-init`.

### Plan B: run Docker inside WSL (Windows)

If Docker Desktop is broken on a Windows laptop but WSL works, you can run
Docker's own engine inside Ubuntu. This is how the showcase was tested on the
development desktop. Do this **at home** — it needs internet once.

```powershell
wsl --install -d Ubuntu-22.04            # skip if you already have Ubuntu
wsl -d Ubuntu-22.04 -u root -- sh -c "apt-get update && apt-get install -y docker.io docker-compose-v2 docker-buildx && systemctl enable --now docker"
```

If the last step complains about `systemctl`, turn on systemd once and retry:
`wsl -d Ubuntu-22.04 -u root -- sh -c "printf '[boot]\nsystemd=true\n' >> /etc/wsl.conf"`,
then `wsl --shutdown`.

Then run every `docker compose …` command from this guide inside Ubuntu, in
the cloned folder (your `C:` drive is at `/mnt/c`):

```powershell
wsl -d Ubuntu-22.04 -u root --cd /mnt/c/path/to/xiguard-showcase -- docker compose up -d --build
```

The browser addresses stay the same (`http://localhost:8088`, `:8090`, …).
Keep one WSL terminal window open during the demo so Ubuntu stays running.
If Docker Desktop is half-running it can hold the same ports — quit it first.

### Last resort

If nothing works and time is up: present the technical overview PDF
(`docs/Xiguard-Technical-Overview.pdf`, also in this folder) and play your rehearsal recording.

---

## Quick reference card

```text
START          docker compose up -d
READY?         docker compose logs -f showcase-init      → "SHOWCASE READY"
STATUS         docker compose ps                         (showcase-init = Exited (0) is normal)
STOP           docker compose down
FRESH START    docker compose down -v && docker compose up -d
RE-RUN SETUP   docker compose up -d showcase-init

Xiguard        http://localhost:8088     admin / showcase
Attack panel   http://localhost:8090
Mailboxes      http://localhost:8025
Router WebFig  http://localhost:8081     xiguard / xiguard-demo

Demo target    game-01  203.0.113.11  → 2.4 Gbps · 60 s
Timeline       20–30 s to blackhole · 2 min block · 30 s probation · NORMAL
```

---

## For whoever maintains this branch

- The showcase is additive: `docker-compose.override.yml` (auto-merged by
  Compose), `.env` (committed demo values), `.gitattributes`, `showcase/` and
  this guide. The only Xiguard code change is the polling fix described in its
  own commit (alert emails queued after commit; expired blackholes removed from
  the router), which belongs on `main` too. `git merge main` into `showcase`
  keeps it current.
- `showcase/chr/simulator.py` — flow simulator + attack panel
  (`python3 showcase/chr/simulator.py selftest` checks the NetFlow encoding).
- `showcase/provision.py` — the setup job; idempotent.
- Prefixes: `SHOWCASE_PREFIXES` in `.env` (each /16 or longer). The named demo
  hosts are at offsets .10–.15 of the first prefix. After changing prefixes,
  `docker compose down -v`.
- CHR version: `CHR_VERSION` build argument in `showcase/chr/Dockerfile`.
- On a Linux laptop you can speed the router up by passing `/dev/kvm` into the
  `chr` service (`devices: ["/dev/kvm"]`); the entrypoint uses it automatically.
