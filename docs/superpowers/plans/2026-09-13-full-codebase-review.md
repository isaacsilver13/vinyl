# Vinyl Full Codebase Review Plan

> **For agentic workers:** This is a review/audit plan, not a build plan — there
> is no code to TDD. Execute each task by reading the listed files and
> producing the described findings, then hand results to Task 7 for synthesis.
> Recommended execution: dispatch Tasks 1-6 as independent read-only
> subagents in parallel (they touch disjoint file sets), then run Task 7
> once all six reports are in.

**Goal:** Produce one prioritized report of bugs, security issues,
deployment blockers, and improvement suggestions covering both services in
this repo — `api/` (FastAPI backend) and `app/` (Streamlit frontend).

**Architecture:** Two independently deployed Fly.io services sharing one
repo. `api/` is a small (~460 line) FastAPI + SQLAlchemy + SQLite
write-sink. `app/` is a much larger (~5,400 line) Streamlit app that reads
Discogs/Spotify APIs, sends SMTP alerts, keeps its own SQLite database, and
calls `api/` only for writes (listing sync, play logging). `app/` never
reads from `api/`.

**Tech stack:** Python 3, FastAPI, SQLAlchemy, Pydantic, Streamlit, SQLite,
Alembic, Fly.io, GitHub Actions, smtplib.

**Spec:** none — this plan's target is the current state of the repository
at commit `b980e2b`, not a written spec.

## Global Constraints (apply to every task below)

- Read-only review — do not modify application code while reviewing.
- For every finding, record: file path + line number, a one-sentence
  description of the defect or opportunity, a concrete failure scenario or
  benefit, and a severity: **Blocker** / **High** / **Medium** / **Low**.
- Blocker = breaks prod or a security hole; High = real bug or bad
  practice with user-visible impact; Medium = correctness/maintainability
  risk without immediate impact; Low = style/nice-to-have.
- Call out missing test coverage explicitly — it's a category of finding,
  not just an aside.
- Don't flag purely stylistic preferences (formatting, naming taste)
  unless they cause a real confusion/bug risk.

---

### Task 1: Backend core (`api/vinyl_api/`)

**Files:**
- Read: `api/vinyl_api/main.py`
- Read: `api/vinyl_api/database.py`
- Read: `api/vinyl_api/models.py`
- Read: `api/vinyl_api/schemas.py`
- Read: `api/vinyl_api/error_log.py`
- Read: `api/vinyl_api/alembic/` (all files — env.py, versions/*)
- Read: `api/vinyl_api/requirements.txt`

**Focus:**
- Auth: `require_api_key` in `main.py` — is the keyless-local fallback safe
  given how `VINYL_API_ENV` is set in prod? Any bypass path?
- DB session handling: every endpoint manually opens/closes a
  `SessionLocal()` — check for leak-on-exception paths, and whether
  FastAPI `Depends` for session injection would be safer than the current
  manual try/finally pattern.
- `post_listings_bulk`: does a bad row abort the whole batch (partial
  commit risk), and is `saved` counting listings that failed validation
  before the loop?
- `models.py`/`schemas.py`: nullable fields, type mismatches between
  Pydantic schema and SQLAlchemy model, missing indexes/uniqueness
  constraints (e.g. `listing_id` uniqueness enforced at DB level or just
  queried?).
- Alembic migrations: do they match current `models.py`? Any drift?
- `error_log.py`: what does `install_error_log()` actually capture, and
  could `/health/errors` leak sensitive data (stack traces, payloads) to
  anyone who can call it — note it's unauthenticated in `main.py`.

- [ ] **Step 1:** Read all files listed above in full.
- [ ] **Step 2:** Write findings as a markdown list under a `## Task 1:
      Backend core` heading, one bullet per finding, in the format from
      Global Constraints.
- [ ] **Step 3:** Note any question you can't resolve from the code alone
      (e.g. "is `VINYL_API_ENV` actually set to non-local in the Fly
      deploy config?" — cross-check `api/fly.toml` and
      `.github/workflows/api-deploy.yml` if needed even though those
      belong to Task 2).

---

### Task 2: Backend tests, Docker, deploy, CI (`api/`)

**Files:**
- Read: `api/tests/test_api.py`
- Read: `api/tests/test_schemas.py`
- Read: `api/Dockerfile`
- Read: `api/fly.toml`
- Read: `api/.dockerignore`, `api/.env.example`
- Read: `.github/workflows/api-ci.yml`
- Read: `.github/workflows/api-deploy.yml`
- Read: `api/README.md` (cross-check claims against actual code/config)

**Focus:**
- Test coverage: which endpoints/branches in `main.py` (from Task 1) have
  no test? Especially error paths (bad bearer key, malformed payload,
  DB failure) and `/health/ready`, `/health/metrics`, `/health/errors`.
- CI: does `api-ci.yml` actually run `pytest`? Does it block deploy on
  failure? Path filters — do they correctly scope to `api/` only, per the
  root README's claim?
- Deploy: single Fly machine + SQLite on a volume — what happens on a
  scale-to-two-machines event (README says move to Postgres before
  scaling — is anything in `fly.toml` currently silently allowing
  `min_machines_running`/autoscaling above 1?). Secrets referenced in
  `fly.toml` vs `api-deploy.yml` — is `VINYL_API_KEY` actually wired
  through the deploy workflow (recent commit `b980e2b` mentions fixing a
  "missing Fly deploy secret" — verify the fix is complete and there's no
  second missing secret).
- Dockerfile: base image pinning, running as non-root, layer caching for
  `requirements.txt`.

- [ ] **Step 1:** Read all files listed above in full.
- [ ] **Step 2:** Cross-reference `VINYL_API_KEY` / `VINYL_API_ENV` handling
      across `fly.toml`, `api-deploy.yml`, and `main.py`'s lifespan check
      from Task 1 to confirm prod can't start unauthenticated.
- [ ] **Step 3:** Write findings under `## Task 2: Backend tests/deploy/CI`.

---

### Task 3: Frontend UI layer (`app/`)

**Files:**
- Read: `app/app.py` (1,230 lines — the main Streamlit UI/routing)
- Read: `app/charts.py`
- Read: `app/styles.py`
- Read: `app/.streamlit/config.toml`

**Focus:**
- `app.py` is large for a single file — identify natural seams (pages,
  tabs, sections) that are already implicit in the code but not split
  into modules; note as a Medium/Low maintainability finding rather than
  prescribing a specific refactor.
- Streamlit anti-patterns: unbounded use of `st.session_state`, expensive
  calls (DB queries, API calls, chart builds) not wrapped in
  `@st.cache_data`/`@st.cache_resource`, recomputation on every rerun.
- Input validation on any user-entered forms (search, add-to-collection,
  user registration if present) before it reaches `database.py` (Task 4).
- Error surfacing to the user: are exceptions from `discogs_api.py`,
  `spotify_helper.py`, or `vinyl_api_client.py` caught and shown
  meaningfully, or do they crash the whole page?
- Any hardcoded secrets, user IDs, or environment-specific values in
  `app.py` or `styles.py`.

- [ ] **Step 1:** Read all files listed above in full.
- [ ] **Step 2:** Write findings under `## Task 3: Frontend UI layer`.

---

### Task 4: Frontend data & external integrations (`app/`)

**Files:**
- Read: `app/database.py` (1,113 lines)
- Read: `app/discogs_api.py`
- Read: `app/spotify_helper.py`
- Read: `app/vinyl_api_client.py`
- Read: `app/utils.py`

**Focus:**
- `database.py`: raw SQL vs parameterized queries (SQL injection risk),
  schema/migration story (is there one, or does the schema drift
  silently?), connection lifecycle (opened per call vs pooled/shared),
  transaction boundaries around multi-step writes.
- `discogs_api.py` / `spotify_helper.py`: rate-limit handling and backoff
  on 429s, timeout configuration on outbound HTTP calls, retry logic,
  credential loading (env vars vs hardcoded), error propagation.
- `vinyl_api_client.py`: does it send the bearer key from `VINYL_API_KEY`
  correctly, handle non-2xx responses from `api/`, and time out?
- Any use of `eval`/`exec`/`pickle` on external data, or unsanitized data
  from Discogs/Spotify flowing into SQL or HTML rendered by Streamlit
  (`st.markdown(..., unsafe_allow_html=True)` XSS-style risk).

- [ ] **Step 1:** Read all files listed above in full.
- [ ] **Step 2:** Write findings under `## Task 4: Frontend data & integrations`.

---

### Task 5: Frontend jobs & standalone scripts (`app/`)

**Files:**
- Read: `app/fetch_listings.py`
- Read: `app/probe_listings.py`
- Read: `app/refresh_all.py`
- Read: `app/send_listing_alerts.py`
- Read: `app/add_user.py`
- Read: `app/set_isilver_email.py`
- Read: `app/scripts/add_isilver_user.py`
- Read: `app/scripts/daily_refresh_and_alerts.py`
- Read: `app/scripts/run_daily_refresh.ps1`
- Read: `app/scripts/deploy_status.ps1`
- Read: `app/README_SMTP.md`, `app/COPILOT_LOW_COST_WORKFLOW.md` (context
  only, to check code matches documented behavior)

**Focus:**
- Personal/hardcoded identifiers: `add_isilver_user.py`,
  `set_isilver_email.py` — one-off scripts with a specific user baked in;
  flag if they're wired into any automated path (cron/CI) vs. genuinely
  one-off, and whether hardcoded PII (email) belongs in version control.
- `refresh_all.py` / `daily_refresh_and_alerts.py`: idempotency (safe to
  re-run after partial failure?), what happens on a Discogs/Spotify
  outage mid-run — partial writes, no writes, or a hang?
- `send_listing_alerts.py`: SMTP credential handling, whether a failure to
  send blocks the rest of the refresh job, duplicate-alert risk on rerun.
- PowerShell scripts: hardcoded paths, whether they'll work outside the
  original author's machine (relates to `PROJECT_ROOT` env var mentioned
  in `app/README.md`).

- [ ] **Step 1:** Read all files listed above in full.
- [ ] **Step 2:** Write findings under `## Task 5: Frontend jobs & scripts`.

---

### Task 6: App deploy, CI, and JS/misc (`app/`, `.github/`)

**Files:**
- Read: `app/Dockerfile`
- Read: `app/fly.toml`
- Read: `app/package.json`, `app/package-lock.json` (why does a Streamlit
  app have an npm package? — check `test_send.js`)
- Read: `app/test_send.js`
- Read: `.github/workflows/app-deploy.yml`
- Read: `.github/workflows/app-daily-refresh.yml`
- Read: `app/.dockerignore`, `app/.env.example`

**Focus:**
- Same secret-wiring check as Task 2 but for `vinyl-catalog`: Discogs,
  SMTP, registration, and `VINYL_API_KEY`/`VINYL_API_URL` — are they all
  actually set as Fly secrets referenced correctly in `app-deploy.yml`,
  matching what `app/README.md` claims?
- `app-daily-refresh.yml`: does the schedule match what
  `daily_refresh_and_alerts.py` (Task 5) expects; failure notification if
  the scheduled run fails silently.
- Why `package.json`/`test_send.js` exist next to a pure-Python app —
  dead code, leftover experiment, or an actual dependency of something
  (e.g. a Node-based SMTP test)? Flag if it looks orphaned.
- Dockerfile: same checks as Task 2 (base image, non-root, layer caching)
  plus whether the persistent volume mount (`vinyl_data` at `/data`) lines
  up with what `database.py` (Task 4) actually opens.

- [ ] **Step 1:** Read all files listed above in full.
- [ ] **Step 2:** Write findings under `## Task 6: App deploy/CI/misc`.

---

### Task 7: Cross-cutting synthesis (depends on Tasks 1-6)

**Inputs:** the six findings sections produced above.

- [ ] **Step 1:** Merge all findings into one document, sorted Blocker →
      High → Medium → Low, each still tagged with its originating area and
      file:line.
- [ ] **Step 2:** Add a short "Security summary" subsection: enumerate
      every secret/credential in the system (Discogs, Spotify, SMTP,
      `VINYL_API_KEY`, registration) and where each is loaded from
      (env var, Fly secret, hardcoded) — flag any that aren't Fly
      secrets in production.
- [ ] **Step 3:** Add a short "Test coverage gaps" subsection listing
      modules with zero tests today (everything in `app/` has none per
      the repo listing — confirm this and call it out as one finding
      rather than repeating it six times).
- [ ] **Step 4:** Add a "Top 5 blockers/quick wins" subsection at the very
      top of the report, chosen by impact vs. effort, for the user to
      act on first.
- [ ] **Step 5:** Present the final report to the user (in-conversation or
      as a file/artifact per user preference) — do not commit it to the
      repo unless the user asks.

---

## Execution Handoff

Tasks 1-6 touch disjoint files and have no dependencies on each other —
dispatch them as parallel read-only subagents (e.g. `feature-dev:code-reviewer`
or `general-purpose`), each briefed with its task's Files/Focus section
above verbatim. Task 7 runs after all six return, in the main session,
since it needs every result in context to rank and dedupe findings.
