Alembic migrations for Vinyl API

Quickstart:

1. Install alembic in your venv: `pip install alembic`
2. Set `VINYL_API_DATABASE_URL` environment variable if you want a non-default DB.
3. Initialize migration repository (if you don't already have one) from project root:

   alembic init vinyl_api/alembic

4. Edit `vinyl_api/alembic/env.py` if needed (it already references `vinyl_api.models`).
5. Generate a migration:

   alembic revision --autogenerate -m "create listings and plays"

6. Apply migrations:

   alembic upgrade head

Note: this is a minimal placeholder to help you run real Alembic commands locally.
