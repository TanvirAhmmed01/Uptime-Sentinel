# Uptime Sentinel

A self-hosted website monitoring tool in a single Python file. It checks whether your sites are up, records every check in SQLite, warns you before TLS certificates expire, and emails you the moment a site goes down or comes back.



---

## Features

- **HTTP checks** — per-site polling interval, response time and status code recorded on every check
- **TLS expiry monitoring** — reads the certificate directly from the socket and warns when fewer than 14 days remain
- **Email alerts on state change** — one mail when a site goes `DOWN`, one when it recovers, so a long outage never spams your inbox
- **7-day statistics** — uptime percentage, check counts and average response time, computed in SQL
- **Web dashboard** — dark, responsive, auto-refreshing; add and remove sites, pause monitoring, clear history
- **Persistent history** — everything lives in a local `sentinel.db` SQLite file that survives restarts
- **Zero dependencies** — `http.server`, `sqlite3`, `ssl`, `smtplib` and `urllib` only

## Quick start

```bash
git clone https://github.com/<your-username>/uptime-sentinel.git
cd uptime-sentinel
python uptime_sentinel.py
```

The dashboard opens automatically at **http://127.0.0.1:5000**. On the first run the database is created and seeded with two example sites (Google and GitHub) so there is something to look at straight away — delete them with the **✕** on each card.

Press `Ctrl+C` in the terminal to stop.

**Requirements:** Python 3.8 or newer. Nothing else.

## Usage

| Action | How |
|---|---|
| Add a site | Fill in the name, URL and interval (seconds), then **Add website**. A missing `https://` is added for you. |
| Remove a site | **✕** on the site card — this also deletes its check history. |
| Force a round of checks | **Check all now** |
| Pause / resume | **Stop monitoring** / **Start monitoring** |
| Wipe statistics | **Clear history** (keeps the sites, drops the checks) |

The page refreshes itself every 15 seconds, and the activity log at the bottom holds the 50 most recent events.

## Email alerts

1. Create a [Google App Password](https://support.google.com/accounts/answer/185833) (a normal Gmail password will not work with SMTP).
2. Set `SMTP_USER` and `SMTP_PASSWORD` near the top of `uptime_sentinel.py`.
3. Enter the destination address in the dashboard, press **Save**, then **Send test alert** to confirm delivery.

Leave the address empty to disable alerts. Any SMTP provider works — change `SMTP_HOST` and `SMTP_PORT` accordingly.

> Alerts fire on a *transition*, so a site must have been checked at least once before its first alert can be sent.

## Configuration

All settings are constants at the top of the file:

| Constant | Default | Purpose |
|---|---|---|
| `PORT` | `5000` | Dashboard port |
| `TIMEOUT` | `10` | Seconds before an HTTP or TLS connection is treated as failed |
| `SSL_WARN_DAYS` | `14` | Certificate expiry warning threshold |
| `REFRESH` | `15` | Dashboard auto-refresh interval, in seconds |
| `DB_FILE` | `sentinel.db` | SQLite database path |
| `FIRST_RUN_SITES` | Google, GitHub | Sites seeded on the very first run |

## How it works

```
┌──────────────┐        ┌─────────────────┐        ┌──────────────┐
│  Browser     │ ─────▶ │  ThreadingHTTP  │ ─────▶ │  SQLite      │
│  (dashboard) │ ◀───── │  Server         │ ◀───── │  sentinel.db │
└──────────────┘        └─────────────────┘        └──────────────┘
                                 ▲                        ▲
                                 │                        │
                        ┌────────────────┐                │
                        │ monitor_loop   │ ───────────────┘
                        │ (daemon thread)│
                        └────────────────┘
                                 │
                        ┌────────────────┐
                        │ SMTP alerts    │
                        └────────────────┘
```

A background daemon thread ticks once per second and runs any site whose interval has elapsed, so sites with different intervals never block each other. The HTTP server runs on the main thread and renders the current state on every request; writes use POST followed by a 303 redirect, so refreshing the page never resubmits a form. All user-supplied text is HTML-escaped before it reaches the page, and every SQL statement is parameterised.

### Schema

```sql
sites    (id, name, url, interval)
checks   (site_id, time, status, code, seconds, error)
settings (key, value)
```

Uptime and average response time are aggregated on read with a single windowed query over the last seven days, so no derived state has to be kept in sync.

## Limitations

- Binds to `127.0.0.1` only and has no authentication — it is designed for local or trusted-network use. Put it behind a reverse proxy with auth before exposing it.
- SMTP credentials live in the source file; move them to environment variables before committing anything real.
- Checks are sequential within a tick, so a few dozen sites is a comfortable ceiling.

## Roadmap

- [ ] Credentials via environment variables
- [ ] Response-time chart per site
- [ ] Webhook alerts (Discord / Slack)
- [ ] Keyword matching in the response body, not just status codes
- [ ] Configurable retry before a site is declared down

## License

MIT — see [LICENSE](LICENSE).

## Author

**Md Tanvir Ahmmed**
