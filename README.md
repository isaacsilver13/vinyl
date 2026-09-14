# Vinyl

Two independently deployed services for tracking a vinyl record collection, sharing one repository:

- **`api/`** — FastAPI write-sink service (`vinyl-api` on Fly.io). SQLite on a persistent Fly volume. See [`api/README.md`](api/README.md).
- **`app/`** — Streamlit collection app (`vinyl-catalog` on Fly.io). Talks to Discogs, Spotify, and `api/` for logging plays. See [`app/README.md`](app/README.md).

## Why one repo, two services

`app/` only ever calls `api/` for writes (bulk listing sync, play logging) and never reads from it — the two are decoupled enough to keep deploying as separate Fly apps, but related enough (same owner, same data domain, `app/` is `api/`'s only consumer) to not need separate repos and separate CI setups. Each subproject keeps its own `Dockerfile`, `fly.toml`, and `requirements`; nothing is shared at import time.

## CI/CD

Each subproject has its own path-filtered GitHub Actions workflows so a change to one never triggers a build/deploy of the other:

- `.github/workflows/api-ci.yml`, `api-deploy.yml` — triggered only by changes under `api/`
- `.github/workflows/app-deploy.yml`, `app-daily-refresh.yml` — triggered only by changes under `app/` (or on schedule)

## Local development

```powershell
# API
cd api
python -m pip install -r requirements-dev.txt
python -m uvicorn vinyl_api.main:app --reload --port 8003

# App (separate terminal)
cd app
$env:VINYL_API_URL = 'http://127.0.0.1:8003'
$env:VINYL_API_KEY = ''
streamlit run app.py
```

Production `app/` uses `https://vinyl-api.fly.dev` for `VINYL_API_URL` and the same secret value for `VINYL_API_KEY` on both Fly applications.

See [`CHANGELOG.md`](CHANGELOG.md) for notable fixes/changes to either service.
