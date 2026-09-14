# Vinyl Codebase Review — 2026-09-13

Full review of `api/` (FastAPI backend) and `app/` (Streamlit frontend) at commit `b980e2b`, run as six parallel area reviews synthesized here. See the review plan at `docs/superpowers/plans/2026-09-13-full-codebase-review.md` for scope/methodology.

## Top 5 blockers / quick wins

1. **Spotify "Connect" is completely broken.** `app/spotify_helper.py` imports `save_pkce_verifier`/`get_pkce_verifier` from `app/database.py` — neither function exists there. Any user clicking "Connect Spotify" hits an `ImportError`. Trivial to verify (`grep -n pkce app/database.py` returns nothing) and fix (add the two functions, a small `spotify_pkce` table or in-memory store).
2. **Price-change alerts permanently stop after the first one per listing.** `create_price_change_alerts` in `app/database.py` does `INSERT OR IGNORE` keyed on `(user_id, listing_id, alert_type)`. Once one `price_change` row exists for a listing, every later price change on that same listing is silently dropped — no error, no email, forever. This defeats the feature's purpose.
3. **`VINYL_API_KEY` likely isn't set on the `vinyl-catalog` (app) side in production.** The API requires the key in prod (`VINYL_API_ENV=production` in `api/fly.toml`), but nothing in `app/fly.toml`, `app-deploy.yml`, or the README shows it being set as a Fly secret on the *app* — only on the API. If it's missing, every write from the Streamlit app to the API (listing sync, play logging) is failing with 401 right now. **Recommend checking this first**: `fly secrets list -a vinyl-catalog`.
4. **CI doesn't gate deploy.** `api-ci.yml` (tests) and `api-deploy.yml` (deploy) both trigger on push to `main` with no dependency between them — a failing test suite doesn't stop or delay the deploy. One-line fix: make deploy a `workflow_run` off CI success, or merge into one workflow with a `needs:` dependency.
5. **`app/scripts/deploy_status.ps1` is fully broken.** It resolves a sibling folder `..\vinyl_api`, which no longer exists after the repo consolidation (the folder is now `api/`, with the `vinyl_api` package one level deeper). Every invocation crashes immediately, even for `-Service app`. One-line path fix.

Also worth immediate attention (not quick, but high-impact): the **"Log" button** in the Play Log tab's "due for a spin" list skips the API sync every other log-play button performs, silently diverging local history from the API's — and a **duplicate `listing_id` within one bulk-sync request drops the entire batch**, not just the duplicate row (see Backend findings below).

---

## Backend (`api/`)

### Blocker / High
- **CI doesn't gate deploy** — `api-ci.yml` and `api-deploy.yml` both fire on `push: main` independently; a broken build can deploy while tests are still failing. (`.github/workflows/api-ci.yml`, `api-deploy.yml`)
- **`VINYL_API_KEY` has no verified path to being set on the app side** — see Top 5 #3.
- **Duplicate `listing_id` in one bulk request drops the whole batch, not just the dupe.** `SessionLocal` has `autoflush=False`; the per-listing check-then-insert loop in `post_listings_bulk` doesn't see its own pending inserts, so two rows with the same `listing_id` in one payload both attempt insert, the DB's unique constraint rejects the second, and the `except`/`rollback` discards the *entire* batch. (`api/vinyl_api/main.py:93-119`, `database.py:9`)
- **Alembic migrations are non-functional** — no `alembic.ini`, no `versions/`, `env.py` is a placeholder. Production schema is created once via `create_all` and never evolves; the next `models.py` change that alters an existing table will hard-fail in prod with `no such column`. (`api/vinyl_api/alembic/`, `database.py:20-23`)
- **`POST /users/{user_id}/plays` has zero test coverage.** (`api/tests/test_api.py`)
- **Tests aren't isolated from the dev SQLite file** — rerunning `pytest` locally without deleting `vinyl_api_dev.db` produces a spurious failure in `test_health_metrics_reflects_activity`. (`api/tests/test_api.py:103-116`)
- **CI never builds the Docker image** — a `Dockerfile`/`requirements.txt` break is only caught at Fly deploy time, not in CI.

### Medium
- TOCTOU race: concurrent bulk requests introducing the same new `listing_id` can both pass the `one_or_none()` check before either commits, causing one request's entire batch to 500. (`main.py:93-118`)
- Raw exception text (`str(exc)`) is returned in 500 responses — internal DB/driver detail leaks to any caller with a valid API key. (`main.py:122,150`)
- No test for a wrong-but-present bearer key, or for malformed/invalid request bodies via HTTP (422 path).
- `/health/errors` capture path is untested — only the empty case is checked.
- Dockerfile runs as root (no `USER` directive).
- `requirements.txt` has no version pins; base image `python:3.12-slim` floats on patch/OS updates.

### Verified sound (checked, no issue found)
- `require_api_key` auth logic and the keyless-local fallback — correctly gated by the `VINYL_API_ENV` startup check, uses `hmac.compare_digest`.
- DB sessions are always closed via `try/finally`, no leak-on-exception.
- `/health/errors` doesn't currently capture tracebacks/payloads — the ring buffer only stores level/timestamp/message.
- No nullable-field mismatch between `PlayIn` and `Play` (the `None` case is substituted before it would violate NOT NULL).
- Per-app Fly deploy tokens are correctly scoped, matching the intent of commit `b980e2b`.

---

## Frontend (`app/`)

### Blocker / High
- **Spotify connect fully broken** — see Top 5 #1. (`app/spotify_helper.py:61,65,143,146`)
- **Price-change alerts stop firing forever after the first one per listing** — see Top 5 #2. (`app/database.py:850-904`, `refresh_all.py:356-363`)
- **"Log" button in the Play Log "due for a spin" list skips the API sync** every other log-play button performs — local history and the API's diverge silently for anyone using this control. (`app/app.py:849-856`, contrast with `:560-569, 607-616, 666-681, 825-837`)
- **`deploy_status.ps1` fully broken** post-repo-consolidation — see Top 5 #5.
- **Username-based SQLite file path is only whitespace-stripped**, not charset-restricted — a username containing `/` or `\` crashes registration with an uncaught, unhandled exception (and Streamlit's default `showErrorDetails` shows the raw traceback to the user). Also case-sensitive uniqueness check allows `"Bob"`/`"bob"` to collide on case-insensitive filesystems. (`app/app.py:138-139,164`, `database.py`'s `get_conn`)
- **No timeout on any Spotify HTTP call** (`exchange_code`, `refresh_access_token`, `_spotify_get`) — a slow/unreachable Spotify endpoint can hang the process indefinitely. Contrast with `discogs_api.py`, which sets timeouts everywhere. (`app/spotify_helper.py:102,130,183`)
- **Fallback `listing_id` uses `str(hash(url))`**, which is not stable across process restarts (Python randomizes string hashing per-process). Every scheduled run that hits this fallback path creates a "new" row in the API for the same real listing, accumulating duplicates forever. (`app/vinyl_api_client.py:64`)
- **Local `db.log_play()` calls are unguarded** (no try/except) while the adjacent API-sync calls are — an unhandled DB error (e.g. WAL lock contention with a background job) surfaces a raw traceback to the end user, since `.streamlit/config.toml` never sets `showErrorDetails = "none"`.
- **Schema evolution via silently-swallowed `ALTER TABLE ... ADD COLUMN` statements** wrapped in bare `except: pass` — genuine failures (locked file, disk full) are indistinguishable from "column already exists" and surface later as an unrelated `no such column` error deep in a sync job. (`app/database.py:226-245`)
- **Daily refresh cron has no failure notification** — if the scheduled job fails (API outage, expired token, locked DB), the only signal is a red GitHub Actions run; nobody is told the collection has gone stale, despite the app already having SMTP infra it could reuse. (`.github/workflows/app-daily-refresh.yml`)
- **All five Streamlit tabs execute their full body on every rerun**, and several of the heaviest DB calls aren't wrapped in `@st.cache_data` (a 200-row play fetch, a 10-year date-count scan, an N+1 per-wantlist-item query loop) — every click anywhere in the app re-runs all of this regardless of which tab is visible. Gets worse as data grows. (`app/app.py:727-729,926-927,1183-1187`)

### Medium
- Discogs token field on the registration form isn't masked (`type="password"` missing) unlike the adjacent password fields, despite being a long-lived credential. (`app/app.py:122-123`)
- Registration email has no format validation before being persisted, unlike every other registration field. (`app/app.py:126-129,173`)
- `except Exception: pass` in the startup sync check discards all errors with zero logging. (`app/app.py:220-234`)
- Two divergent "daily refresh" implementations (`app-daily-refresh.yml`'s direct `refresh_all.py --force` call vs. `daily_refresh_and_alerts.py`'s `--force --no-alerts` + separate `send_listing_alerts.py`) that already behave differently and can drift further.
- `README.md`'s documented `PROJECT_ROOT` override isn't honored by `run_daily_refresh.ps1` (only the Python wrapper reads it).
- Secrets required for `vinyl-catalog` (Discogs, registration, `VINYL_API_KEY`) aren't enumerated as a single authoritative list anywhere — `.env.example` only shows the `fly secrets set` command for SMTP vars.
- `node_modules/` isn't excluded by `.gitignore`/`.dockerignore`, despite `test_send.js` instructing `npm install` right in `app/` — a Docker build from that directory would ship `node_modules` into the image.
- Both Dockerfiles (`api/`, `app/`) run as root; `app/Dockerfile`'s image also has a compiler on board (`gcc`, `libffi-dev`), raising the stakes of that.
- Hardcoded PII: `app/set_isilver_email.py` and `app/scripts/add_isilver_user.py` have a real email/username baked in. Confirmed **not** wired into any CI/scheduled path — genuinely dead one-off scripts, but still shouldn't be in git history. Recommend deleting.
- Connections from `with get_conn(...) as conn:` are never explicitly `.close()`d (SQLite's context manager only commits/rolls back) — works today via CPython refcounting, but is fragile.
- No 429-specific backoff on direct per-listing Discogs enrichment calls (contrast with the scraping loop a few lines above, which does retry with backoff).
- Both Dockerfiles use floating base-image tags (`python:3.12-slim`) rather than a pinned digest.

### Low / maintainability
- `app/app.py` (1,230 lines) has clear, already-implicit module seams (login/registration, refresh dialog, five tab bodies) that aren't split out — a maintainability note, not a prescribed refactor.
- Daily-refresh cron comment ("4 AM ET") is only accurate half the year (DST).
- `jq -r '.[0].id'` in the daily-refresh workflow hardcodes "first machine" — fine today (`min_machines_running=0`), a latent trap if ever scaled.

### Verified sound (checked, no issue found)
- No SQL injection: all data-carrying queries in `app/database.py` use parameter binding; the one f-string-built statement only interpolates hardcoded column names, never external input.
- No `eval`/`exec`/`pickle` on external data anywhere in the data/integration layer.
- No `unsafe_allow_html=True` call renders untrusted Discogs/user data — all such usages are static CSS/markup.
- `vinyl_api_client.py` sends the bearer key correctly, sets explicit timeouts, and its callers wrap it in try/except.
- Discogs API calls all set explicit timeouts and load credentials from env vars, never hardcoded.
- Volume/env-var wiring (`VINYL_DATA_DIR=/data`) is consistent between `Dockerfile`, `fly.toml`, and the volume mount.
- Per-app Fly deploy tokens are correctly scoped and distinct between the two services' workflows.
- `package.json`/`test_send.js` are real, working SMTP-test tooling, not dead code — flagged only for missing `.gitignore` coverage, not for being vestigial.
- Refresh job (`refresh_all.py`) commits per-release/per-user and is safe to rerun after a partial failure; alert-sending is deduplicated via `email_sent_at` and a send failure can't crash the rest of the run.

---

## Security summary

| Credential | Loaded from | Notes |
|---|---|---|
| `VINYL_API_KEY` (api write auth) | Fly secret on `vinyl-api`; **unverified on `vinyl-catalog`** | See Top 5 #3 — check this first |
| Discogs token | Env var / Fly secret | Fine at rest; UI field for it isn't masked (Medium finding above) |
| Spotify client id/secret | Env var | Feature is currently non-functional (Blocker above) |
| SMTP credentials | Fly secret | Only credential with an explicit `fly secrets set` example in the docs |
| Registration code | Fly secret (per README) | Not enumerated alongside other required secrets |
| Personal email/username | **Hardcoded in `set_isilver_email.py` / `add_isilver_user.py`** | Confirmed dead code — recommend deleting from git history |

## Test coverage gaps

- `api/`: no test for `/users/{user_id}/plays`, no wrong-bearer-key test, no malformed-payload/422 test via HTTP, no test exercising the `/health/errors` capture path, local tests aren't DB-isolated.
- `app/`: **no automated tests exist anywhere in `app/`** (confirmed — no `test_*.py`/`*_test.py` files besides the unrelated `test_send.js` SMTP script). Given `app/` is ~5,400 lines carrying the product's core logic (refresh jobs, alerting, Discogs/Spotify integration, DB layer), this is the single largest structural gap in the codebase.

---

## Method note

Six read-only review agents ran in parallel against disjoint file sets (backend core, backend tests/deploy/CI, frontend UI, frontend data/integrations, frontend job scripts, app deploy/CI/misc), then this document synthesizes and dedupes their findings. Full per-agent prompts and scope are in `docs/superpowers/plans/2026-09-13-full-codebase-review.md`.
