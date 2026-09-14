# vinyl_api

Standalone FastAPI service for the Vinyl catalog application.

## Local development

From this repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m uvicorn vinyl_api.main:app --reload --port 8003
```

The API listens on `http://127.0.0.1:8003` for the dashboard-compatible local
profile. Check `http://127.0.0.1:8003/health` for a startup check.

Run tests with:

```powershell
python -m pytest -q
```

Set `VINYL_API_DATABASE_URL` to use a different database. Local development
defaults to `sqlite:///./vinyl_api_dev.db`. Set `VINYL_API_KEY` to require a
bearer token for write endpoints; leaving it unset enables keyless local
development.

Schema is managed entirely by Alembic — run `python migrate_or_stamp.py`
against a fresh local DB before starting the server for the first time (the
Dockerfile/`entrypoint.sh` does this automatically in containers; the test
suite does the equivalent itself in `tests/conftest.py`). `main.py`'s startup
path does **not** call `Base.metadata.create_all()` any more, so an
unmigrated DB will fail with "no such table" until `migrate_or_stamp.py` has
run against it at least once. To add a schema change, add a new revision
under `vinyl_api/alembic/versions/`, not just a `models.py` edit.

`/docs`, `/redoc`, and `/openapi.json` are only served when
`VINYL_API_ENV=local` (the default) — they're disabled in any other
environment. `/health/errors` requires the same bearer key as the write
endpoints.

## Fly.io deployment

The production configuration is in `fly.toml` and uses one Fly machine with a
persistent volume mounted at `/data`:

```powershell
fly launch --no-deploy
fly volumes create vinyl_api_data --region ewr --size 1
fly secrets set VINYL_API_KEY='replace-with-a-secret'
fly deploy
```

The API database is `sqlite:////data/vinyl_api.db`. SQLite plus one machine is
appropriate for the initial deployment. Back up the Fly volume before
maintenance, and move to managed Postgres before scaling the API horizontally.

The Vinyl Streamlit app must use these settings when calling the deployed
service:

```env
VINYL_API_URL=https://vinyl-api.fly.dev
VINYL_API_KEY=the-same-secret-configured-on-fly
```

## API surface

- `GET /health` - unauthenticated health check
- `GET /health/ready` - unauthenticated DB connectivity check
- `GET /health/metrics` - unauthenticated activity/freshness counters
- `GET /health/errors` - bearer key required when configured; recent
  ERROR-level log records (kept in-memory only, last 50)
- `POST /listings/bulk` - persist listings; bearer key required when configured
- `POST /users/{user_id}/plays` - log a play; bearer key required when configured
