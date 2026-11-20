# Xiguard — admin user and router logins

This guide covers two things: creating or resetting a login for the **Xiguard
panel**, and logging into the **showcase router** (MikroTik CHR) with Winbox or
WebFig — see the [last section](#the-showcase-router-chr-logins-and-addresses).

## How the admin account normally appears

On the **very first start** (empty database), Xiguard creates one admin from
`.env`: `ADMIN_USERNAME` / `ADMIN_PASSWORD` (in the showcase: `admin` / `showcase`).

That happens **only once**. Changing `.env` later does not change the account,
and Xiguard has no sign-up page or user-management screen. So if the admin is
missing, its password is forgotten, or you need a second login, use the
commands below.

Run them in the project folder **while Xiguard is running** (`docker compose ps`
shows `postgres` as Up). They work in PowerShell, Terminal (macOS) and bash.

## 1. See which users exist

```bash
docker compose exec postgres psql -U xiguard -d xiguard -c "SELECT username, is_active, last_login FROM users;"
```

## 2. Create a user — or reset its password if it already exists

Replace `NEW-PASSWORD` (and `admin`, if you want a different username):

```bash
docker compose exec postgres psql -U xiguard -d xiguard -c "CREATE EXTENSION IF NOT EXISTS pgcrypto; INSERT INTO users (username, password_hash) VALUES ('admin', crypt('NEW-PASSWORD', gen_salt('bf', 12))) ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, is_active = true, updated_at = NOW();"
```

The output ends with `INSERT 0 1` (a `NOTICE: extension "pgcrypto" already exists`
line before it is normal). Log in with the new password (showcase panel:
<http://localhost:8088>). The same command creates the user if it's missing,
resets the password if it exists, and re-enables it if it was disabled.

**Password characters:** use only letters, digits and `- _ . @`. Quotes, `$`,
`!` and backticks break the command in some shells.

## 3. Disable a user (optional)

```bash
docker compose exec postgres psql -U xiguard -d xiguard -c "UPDATE users SET is_active = false WHERE username = 'olduser';"
```

## If something goes wrong

| You see | Fix |
|---|---|
| `service "postgres" is not running` | Start Xiguard first: `docker compose up -d`, wait a few seconds, retry. |
| `role "xiguard" does not exist` or `database "xiguard" does not exist` | Your `.env` uses other values. Put its `POSTGRES_USER` after `-U` and its `POSTGRES_DB` after `-d`. |
| `ERROR: syntax error` | A quote got lost. Copy the command again and check the password characters. |
| Login still says *Invalid credentials* | Usernames are case-sensitive. Run step 1 and check the user shows `is_active` = `t`. |

**Running Docker inside WSL (the showcase guide's Plan B)?** Put this in front
of each command, with your folder path, and keep `-e` (not `--`) so the quotes
survive:

```powershell
wsl -d Ubuntu-22.04 -u root --cd /mnt/c/path/to/xiguard-showcase -e docker compose exec postgres psql ...
```

---

## The showcase router (CHR): logins and addresses

The bundled MikroTik CHR has two accounts, both with full rights:

| Username | Password | Use it for |
|---|---|---|
| `xiguard` | `xiguard-demo` | **Use this on stage** for Winbox and WebFig. It is also the account Xiguard itself logs in with. |
| `admin` | *(empty — leave the field blank)* | The router's factory account. Works, but prefer `xiguard`. |

How to reach it **from the showcase laptop** (it is not reachable from other devices):

| Tool | Connect to |
|---|---|
| **Winbox** | **Connect To:** `127.0.0.1` (port 8291 is the default) → login `xiguard` / `xiguard-demo` |
| WebFig (browser) | <http://localhost:8081> → same login |

The router does not appear in Winbox's *Neighbors* list — type `127.0.0.1` by
hand. Download Winbox from <https://mikrotik.com/download> **at home**; the
venue may have no internet.

The router's own addresses (what you see under **IP → Addresses**):

| Address | Interface | What it is |
|---|---|---|
| `10.0.2.15/24` | `ether1` | The router's uplink inside its container. Not reachable from the laptop directly — use `127.0.0.1` as above. |
| `203.0.113.1/24` | `customers` | Gateway of the first customer prefix |
| `198.51.100.1/24` | `customers` | Gateway of the second customer prefix |

Inside Docker, Xiguard reaches the router as `chr`, RouterOS API port 8728.

**During the show, don't** change the `xiguard` password or delete that user,
or Xiguard loses access to the router and blackholes start failing. If it
happens anyway, `docker compose up -d showcase-init` puts it back (as long as
`admin` still has an empty password). The router starts fresh whenever its
container is recreated (for example after `docker compose down`), so any other
change made in Winbox is temporary.
