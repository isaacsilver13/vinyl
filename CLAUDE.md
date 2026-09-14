# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

One repo, two independently deployed Fly.io services for tracking a vinyl record collection (consolidated from formerly-separate `vinyl_api`/`vinyl_app` repos — some file paths and comments elsewhere may still say `vinyl_api`, which no longer exists as a sibling folder):

- `api/` — FastAPI write-sink service (`vinyl-api` on Fly.io), SQLite on a persistent Fly volume. Only ever receives writes (bulk listing sync, play logging) from `app/`; never reads from it.
- `app/` — Streamlit collection app (`vinyl-catalog` on Fly.io). Talks to Discogs, Spotify, and `api/`.

They stay one repo (same owner/data domain, `app/` is `api/`'s only consumer) but deploy and CI independently — each has its own Dockerfile, `fly.toml`, dependencies, and path-filtered GitHub Actions workflows (`api-ci.yml`/`api-deploy.yml` trigger only on `api/**` changes; `app-deploy.yml`/`app-daily-refresh.yml` only on `app/**` or schedule).

## Commands

API (from `api/`):
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m uvicorn vinyl_api.main:app --reload --port 8003
python -m pytest -q                       # full suite
python -m pytest tests/test_api.py::test_name   # single test
python -m compileall -q vinyl_api tests   # what CI runs before tests
```
Set `VINYL_API_DATABASE_URL` for a non-default DB (local default: `sqlite:///./vinyl_api_dev.db`). `VINYL_API_KEY` unset enables keyless local dev; set it to require a bearer token on write endpoints, matching prod.

App (from `app/`):
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```
Run the API separately alongside it (`VINYL_API_URL=http://127.0.0.1:8003`, matching the port above). There is no automated test suite under `app/` (the only `app/package.json`/`test_send.js` pair is an unrelated Node SMTP-test helper, not a frontend build — don't treat it as one). The daily refresh job (`python scripts/daily_refresh_and_alerts.py`, or `refresh_all.py --force`) syncs collection/wantlist/suggestions/listings and sends alert emails inline.

## Architecture notes

- **Alembic is now real and is the single source of schema truth for `api/`.** `api/migrate_or_stamp.py` runs `alembic upgrade head` before `uvicorn` starts (see `api/Dockerfile` / `api/entrypoint.sh`, and `api/tests/conftest.py` for how the test suite does the equivalent). It detects a pre-Alembic database (has the `listings`/`plays` tables but no `alembic_version` table) and stamps it to the baseline revision — not `"head"` — before continuing on to `upgrade head`, so a migration added after the baseline still actually runs against an existing prod DB instead of being silently skipped. `vinyl_api.main`'s startup lifespan deliberately does **not** call `database.init_db()` (`create_all`) anymore; don't add it back; the whole point of the Alembic migration is that create_all is no longer a second, uncoordinated source of schema truth. Add new schema changes as a new `api/vinyl_api/alembic/versions/000N_*.py` migration, not as a `models.py`-only change.
- Both `api/Dockerfile` and `app/Dockerfile` chown their Fly-mounted `/data` volume **at container runtime** via `entrypoint.sh` (root at container start, then `setpriv --reuid=appuser --regid=appuser --init-groups <program>` to drop privileges), not just at build time — a real Fly volume mount (like a fresh Docker named volume) replaces whatever ownership was baked into the image at that path with a fresh root-owned directory, so a build-time-only `chown` doesn't survive a real deploy. `setpriv` (not `su -s`) is deliberate: `su` forwards SIGTERM but then SIGKILLs its child ~2s later regardless, which never gives uvicorn/streamlit a real graceful-shutdown window; `setpriv` execs directly into its target program (there's no separate `--exec` flag — the program is just its final positional argument) so it becomes PID 1 itself with no wrapping su/shell layer. The daily-refresh workflow's `flyctl ssh console` command uses the same `setpriv` pattern for the same reason (that SSH session is root by default). Keep both Dockerfiles' entrypoint pattern (and the workflow's) in sync if you touch any of them.
- `api`'s `/docs`, `/redoc`, and `/openapi.json` are only served when `VINYL_API_ENV=local` (default); they're disabled in any other environment (see `_docs_urls()` in `main.py`). `/health/errors` requires the same bearer-key auth as the write endpoints (`require_api_key`) — it mirrors every ERROR-level log record process-wide, not just the two sanitized 500-handlers, so it must never be publicly reachable.
- `app/database.py`'s `users.username` column is `COLLATE NOCASE` so `Alice`/`alice` can't both register (they'd otherwise land in two separate per-user SQLite files that collide on case-insensitive filesystems) — this only applies to tables created fresh after that change; an existing production `users` table needs a one-time manual rebuild to pick up the new collation (SQLite can't `ALTER` a column's collation in place).
- `app/database.py` handles its own lightweight schema evolution via `ALTER TABLE ... ADD COLUMN` calls, tolerating only the "column already exists" `OperationalError` (checked by message) and logging anything else instead of silently swallowing it — when adding a column here, follow the existing pattern rather than reintroducing a bare `except: pass`.
- `app/vinyl_api_client.py` is the only thing in `app/` that talks to `api/` — auth, timeouts, and retry behavior for that boundary live there.
- A full two-sided code review (backend + frontend) was written today to `docs/reviews/2026-09-13-codebase-review.md` — read it before touching `app/spotify_helper.py`, `app/database.py`'s alert/price-change logic, or anything Spotify/alert-related, since it documents several confirmed-broken paths in those areas with exact line numbers. (Note: the bulk-listing dedup-within-a-batch issue and the price-change-alert stale-price issue it documents have since been fixed — see `CHANGELOG.md`.)
