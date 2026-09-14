# vinyl_app

Streamlit application for the Vinyl catalog. This repository is one half of the `Vinyl` GitHub Project; the independent FastAPI service lives in `vinyl_api`.

## Local development

Create a Python environment and install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

The app stores its local data under `VINYL_DATA_DIR`, which defaults to the repository directory. Keep `.env` and local databases out of Git.

Run the API separately from the `vinyl_api` repository:

```powershell
$env:VINYL_API_URL = 'http://127.0.0.1:8003'
$env:VINYL_API_KEY = ''
python -m uvicorn vinyl_api.main:app --reload --port 8003
```

For the deployed app, set `VINYL_API_URL` to `https://vinyl-api.fly.dev` and set the same `VINYL_API_KEY` on both Fly applications.

## Refresh jobs

Run the daily refresh (collection/wantlist/suggestions/listings sync, with alert emails sent inline) from any working directory:

```powershell
python scripts/daily_refresh_and_alerts.py
```

This mirrors production: it calls `refresh_all.py --force`, which handles alert-sending itself. The Windows-only wrapper is available at `scripts/run_daily_refresh.ps1`. Set `PROJECT_ROOT` when invoking the scripts from a separate scheduler.

## Deployment

The Streamlit Fly.io application is `vinyl-catalog`. Its deployment configuration is in `fly.toml` and uses the `vinyl_data` persistent volume mounted at `/data`. The container's `entrypoint.sh` fixes `/data`'s ownership at every start (a Fly volume mount can arrive root-owned regardless of what the image sets at build time) before dropping to the unprivileged `appuser` the app actually runs as.

```powershell
fly deploy
```

Set the following through Fly secrets (never commit `.env` files, database files, or tokens):

- `DISCOGS_TOKEN` — Discogs personal access token
- `DISCOGS_USERNAME` — Discogs account username
- `REGISTRATION_CODE` — invite code required to create a new account via the web UI
- `VINYL_API_KEY` — must match the key set on the `vinyl-api` Fly app
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `ALERT_FROM_EMAIL` — SMTP delivery for listing-alert digest emails

Optional, only needed if the corresponding feature is used:

- `DISCOGS_APP_NAME` — custom User-Agent string sent to Discogs (defaults to `VinylCatalogApp/1.0`)
- `SMTP_USE_TLS`, `ALERT_FROM_NAME`, `SMTP_DEBUG` — additional SMTP tuning
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_REDIRECT_URI` — Spotify integration

`VINYL_API_URL` is already set as a plain (non-secret) `[env]` value in `fly.toml` and does not need to be set via `fly secrets set`.

```powershell
fly secrets set DISCOGS_TOKEN=... DISCOGS_USERNAME=... REGISTRATION_CODE=... VINYL_API_KEY=... SMTP_HOST=... SMTP_PORT=... SMTP_USERNAME=... SMTP_PASSWORD=... ALERT_FROM_EMAIL=... -a vinyl-catalog
```
