# Changelog

Notable changes to this repo. Each entry is dated by when the work landed in
the working tree (not necessarily when it was deployed/committed).

## 2026-09-14 — Manager sign-off fixes

Fixes required by the Manager's final sign-off review of the 2026-09-13
tester-review fixes below. All changes left uncommitted in the working tree
per process; see git history/PR description for the actual commit(s).

### Must-fix (deploy-blocking)

- **`.github/workflows/app-daily-refresh.yml`:** the daily refresh's
  `flyctl ssh console --command "python /app/refresh_all.py --force"` ran as
  root (Fly's SSH console default), conflicting with `/data` now being
  appuser-owned per the 2026-09-13 entrypoint.sh fix — any file it wrote
  landed root-owned, and the app itself couldn't write to it again until the
  next restart re-ran entrypoint.sh's chown. Now runs the refresh command via
  `setpriv --reuid=appuser --regid=appuser --init-groups python /app/refresh_all.py --force`,
  matching the mechanism `entrypoint.sh` itself now uses (see next item).
- **`api/entrypoint.sh`, `app/entrypoint.sh`:** replaced `su -s /bin/sh -c
  '...' appuser` with `setpriv --reuid=appuser --regid=appuser --init-groups
  <program>`. util-linux's `su` forwards SIGTERM to its child but then
  SIGKILLs it ~2s later regardless of what the child does, so uvicorn/
  streamlit never got a real graceful-shutdown window on deploy or Fly's
  `auto_stop_machines`. `setpriv` execs directly into its target program
  (given as its own final positional argument — there's no separate
  `--exec` flag, an initial draft of this fix incorrectly included one and
  it was caught by an actual `docker run` smoke test, not just `docker
  build`) instead of forking a supervised child, so uvicorn/streamlit itself
  ends up as PID 1 with no wrapping su layer, and signals reach it directly.
  `setpriv` ships in util-linux, already present on `python:3.12-slim`'s
  Debian base — no new package needed. Also caught by the `docker run` smoke
  test (see Verification below): unlike `su`, `setpriv` changes process
  credentials but not `$HOME`, which stayed `/root` — `app/entrypoint.sh`'s
  streamlit then tried (and, as appuser, failed with `PermissionError`) to
  read `/root/.streamlit/secrets.toml` before it could bind its port. Both
  entrypoint.sh scripts now explicitly `export HOME=/home/appuser` (and
  `USER=appuser`) before the `setpriv exec`.
- **`app/requirements.txt`:** added an explicit `requests==2.34.2` pin.
  `requests` is imported directly by `vinyl_api_client.py` and
  `discogs_api.py` but was absent from `requirements.txt`, floating in
  unpinned via cloudscraper/python3-discogs-client's transitive dependency
  despite the whole point of the 2026-09-13 pinning pass. Version confirmed
  by inspecting what actually resolves in the built `app/Dockerfile` image;
  matches the version already pinned in `api/vinyl_api/requirements.txt`.
- **`api/alembic.ini`, `api/migrate_or_stamp.py`:** a plain `alembic revision
  --autogenerate` run from `api/` (the documented developer workflow)
  ModuleNotFoundError'd on `vinyl_api` (`env.py`'s `import vinyl_api.models`
  only worked by accident when invoked via `migrate_or_stamp.py`, which
  happens to put `api/` on `sys.path` itself). Added `prepend_sys_path = .`
  (plus `path_separator = os` to avoid alembic's related deprecation
  warning) to `alembic.ini`, resolved relative to cwd — so this still
  requires running `alembic` from `api/`, matching the documented workflow.
  Also had `migrate_or_stamp.py` explicitly set `script_location` via
  `cfg.set_main_option(...)` built from its own file location (`_HERE`), so
  its behavior no longer depends on the caller's cwd at all. Verified by
  reproducing the ModuleNotFoundError before the fix and confirming a plain
  `alembic revision --autogenerate` from `api/` no longer hits it after (see
  PR/session notes for the exact repro commands); no migration file was
  committed from that check.
- **`api/vinyl_api/error_log.py`, `api/tests/conftest.py`:** the
  `/health/errors` ring buffer is process-wide module state that was never
  reset between tests, so `test_health_errors_returns_a_list` only passed
  because of test collection order (it happened to run before a later test
  logged an error). Added `error_log.clear()` and a new autouse
  `_reset_error_log_ring_buffer` fixture in `conftest.py` that calls it
  before every test. Also added a regression test
  (`test_health_errors_isolated_from_a_prior_tests_logged_error` in
  `test_api.py`) that logs an error immediately before
  `test_health_errors_returns_a_list` runs, so the isolation is actually
  exercised rather than just asserted in a docstring. Separately,
  `conftest.py`'s `tempfile.mkdtemp()` for the temp test DB directory was
  never cleaned up (leaked a temp dir per pytest run); added an explicit
  `shutil.rmtree(..., ignore_errors=True)` cleanup in a `pytest_unconfigure`
  hook. Kept `mkdtemp()` rather than switching to
  `tempfile.TemporaryDirectory()` because its own `cleanup()` raised on
  Windows here — SQLAlchemy never explicitly disposes its engine, so the
  sqlite file handle is still open when cleanup runs; `ignore_errors=True`
  tolerates that instead.
- **`app/database.py` (`create_price_change_alerts`), `app/refresh_all.py`:**
  a pending (not-yet-emailed) price-change alert's `change_pct` is
  recomputed against the row's *original* baseline `prev_price_usd` when
  refreshed — correct in general, but if a price moves e.g. 10→8 (alert
  created at -20%) then back 8→10 before the email sends, the pending row
  ends up at price=10, change_pct=0.0 and would still be emailed later as a
  no-op "Prev: 10 | Now: 10 | Change: 0.0%" alert. `create_price_change_alerts`
  now takes an explicit `threshold_pct` (the caller's own alert-creation
  threshold — `refresh_all.py`'s `_PRICE_CHANGE_PCT`) and, when refreshing a
  still-pending row, deletes it instead of updating it in place if the
  recomputed change vs. the original baseline has fallen back under that
  threshold. A future swing back past the threshold still creates a fresh
  alert via the existing `INSERT OR IGNORE` path, correctly treated as a new
  baseline rather than a continuation. Verified with a manual scripted
  repro of the 10→8→10 sequence (row is deleted, `get_pending_listing_alerts`
  returns empty) and a second repro confirming a still-above-threshold
  further drop (10→8→5) still updates in place as before.

### UX fixes

- **`app/app.py`:** the four Refresh-All step failure messages ("Check the
  logs for details.") were operator-facing language on an end-user Streamlit
  surface — a vinyl-catalog user has no log access. Replaced with wording
  that names the most likely real cause (expired Discogs token / temporary
  Discogs rate limit) and a concrete next step ("Try again in a minute."),
  per step. The underlying exception is still logged server-side exactly as
  before.
- **`app/app.py`, `app/database.py`:** registration's generic "Could not
  create account. Please try again." was shown even for a
  `sqlite3.IntegrityError` (username already taken via the case-insensitive
  UNIQUE constraint) — a case where retrying identically can never succeed.
  Now catches that case specifically and says "That username is already
  taken — please choose another." Also fixed a related stuck-account edge
  case: if `create_user` succeeded but the following `init_user_db` call
  failed, the `users` row was left behind with no working per-user DB, and
  every future registration attempt with that username would hit the UNIQUE
  constraint with no way to recover. Registration now rolls back the just-
  created user row (new `db.delete_user`) if `init_user_db` fails, so the
  username becomes available again instead of being permanently stuck.
- **`app/app.py`:** the four Refresh-All steps set their progress bar to
  100% inside the `except` block before showing the error, which reads as
  "finished successfully, then something else broke." Changed to
  `_pN.empty()` (clears the bar) so the UI honestly communicates "stopped
  partway" instead of "completed."

### Verification

- `cd api && python -m pytest -q` — passing (see PR/session notes for the
  exact count, now including the new error-log-isolation regression test).
- `docker build` for both `api/Dockerfile` and `app/Dockerfile` — both
  succeed after the `setpriv` entrypoint change.
- `docker run` smoke test (previously never done — only `docker build` had
  been exercised) for both images, each with a scratch volume mounted at
  `/data`: confirmed the process starts as `appuser` (not root), can write
  to `/data`, and responds on its port. See PR/session notes for exact
  commands and output.

## 2026-09-13 — Tester-review fixes (post-remediation-pass follow-up)

Fixes for issues a functional/security review found in the previous
remediation pass (see `docs/reviews/2026-09-13-codebase-review.md` for the
original review). All changes below were left uncommitted in the working
tree per process; see git history/PR description for the actual commit(s).

### Critical / High

- **`api/Dockerfile`, `app/Dockerfile`:** both now chown the Fly-mounted
  `/data` volume at container **runtime** via a new `entrypoint.sh` in each
  service, not just at build time. A real Fly volume mount (like a fresh
  Docker named volume) replaces whatever ownership was baked into the image
  at that path with a fresh root-owned directory — the previous build-time-only
  `chown /app` (api) / `chown /app /data` (app) never actually applied to the
  real mounted volume, so the container crashed on every real start before
  `uvicorn`/`streamlit` came up. Both Dockerfiles now start as root and drop
  to `appuser` via `su -s /bin/sh -c '...' appuser` inside `entrypoint.sh`,
  after fixing `/data`'s ownership.
- **`app/database.py` (`create_price_change_alerts`):** a still-pending price
  alert (not yet emailed) silently dropped every further price update instead
  of refreshing its price — so by the time the alert email actually sent, it
  could report a stale price from several updates ago. Pending rows now get
  their `price_usd`/`change_pct` refreshed in place (keeping the original
  `prev_price_usd` baseline so "percent changed" doesn't drift with every
  tick), without touching `email_sent_at`. As a side effect, this also makes
  within-batch duplicate `listing_id`s in `create_price_change_alerts`
  consistently keep the *last* occurrence, matching the API bulk-insert
  endpoint's dedup behavior.
- **`api/migrate_or_stamp.py`:** a pre-Alembic database was being stamped to
  `"head"` instead of to its actual baseline revision — harmless today (only
  one migration exists) but would have silently marked a never-migrated prod
  DB as fully migrated the moment a second migration shipped, without that
  migration's DDL ever running. Now stamps to the baseline revision
  (looked up dynamically from the migration history, not hardcoded) and then
  always continues on to `alembic upgrade head` in the same run, so
  migrations added after the baseline actually apply. Also fixed the
  pre-existing-table detection to require *all* expected tables present
  (was a set intersection, which could treat a DB with only one of two
  expected tables as "fully pre-existing" and stamp it without ever creating
  the missing table); a genuinely partial pre-Alembic DB now falls through to
  a normal `upgrade head`, which fails loudly instead of silently
  under-migrating.
- **`api/vinyl_api/main.py`:** removed the `database.init_db()`
  (`Base.metadata.create_all`) call from the startup lifespan. With real
  Alembic migrations now in place, `migrate_or_stamp.py` is the single
  schema-creation path; leaving `create_all` in the startup path too would
  silently re-create anything a future migration intentionally drops or
  renames. `api/tests/conftest.py` now runs the same `migrate_or_stamp.py`
  step against its temp test DB so the test suite still gets a real,
  migration-created schema.

### Security

- **`api/vinyl_api/main.py`:** `/health/errors` now requires the same
  bearer-key auth as the write endpoints. It mirrors every ERROR-level log
  record process-wide (not just the two sanitized 500-handlers), so it was
  previously a way to read arbitrary dependency error messages — which can
  contain things like connection strings — with zero auth.
- **`api/vinyl_api/main.py`:** `/docs`, `/redoc`, and `/openapi.json` are now
  only served when `VINYL_API_ENV=local` (the default); disabled everywhere
  else. This is an internal write-only API sink and shouldn't expose its
  schema/interactive docs publicly.
- **`app/app.py`:** raw DB exception text (e.g.
  `UNIQUE constraint failed: users.username`) no longer reaches the browser
  via `st.error(f"...: {e}")` at registration, the four Refresh-All steps, or
  any of the five "Log Play" sites. All now log the real exception
  server-side and show a generic user-facing message instead, matching how
  `api/`'s 500-handlers already work.
- **`app/.env.example`, `app/README_SMTP.md`:** replaced a real personal
  Discogs username and a real Gmail address used as example values with
  generic placeholders.
- **`api/vinyl_api/requirements.txt`, `api/requirements-dev.txt`,
  `app/requirements.txt`:** pinned every dependency to an exact version
  (previously fully unpinned in `api/`, `>=` floors only in `app/`) so a
  `flyctl deploy` (which re-resolves dependencies at deploy time) can't
  install something CI never actually tested.

### Functional (small)

- **`api/vinyl_api/schemas.py`, `api/vinyl_api/main.py`:** integer fields
  that get written to a SQLite `INTEGER` column (`release_id`, and the
  `user_id` path parameter) are now bounded to SQLite's signed-64-bit range,
  so an absurdly large value is a normal 422 instead of a 500 from an
  unhandled DB-layer error. Price fields now reject `NaN`/`Infinity`
  (`allow_inf_nan=False`); a custom `RequestValidationError` handler was
  added so rejecting a `NaN`/`Infinity` input doesn't itself crash while
  serializing the rejected value back into the error response (Starlette's
  default JSON response can't encode a raw `NaN`/`Infinity` float). Empty
  `listing_id` is rejected (`min_length=1`). The bulk listings payload is
  capped at 5000 listings per request to bound the endpoint's per-row-SELECT
  (N+1) cost against the small Fly machine's healthcheck timeout.
- **`app/database.py`:** `users.username` is now `COLLATE NOCASE`, so
  `Alice`/`alice` can't both register (defense in depth alongside app.py's
  existing case-insensitive check at the registration form).

See `docs/reviews/2026-09-13-codebase-review.md` for the original review
these fixes (and the prior remediation pass) respond to.
