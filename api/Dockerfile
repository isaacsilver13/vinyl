# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

COPY vinyl_api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY vinyl_api ./vinyl_api
COPY tests ./tests
COPY alembic.ini ./alembic.ini
COPY migrate_or_stamp.py ./migrate_or_stamp.py
COPY entrypoint.sh ./entrypoint.sh

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app \
    && chmod +x ./entrypoint.sh

# Deliberately stay root here: the Fly volume mounted at /data (see fly.toml)
# arrives root-owned at runtime regardless of what this build chowns, so
# entrypoint.sh fixes /data's ownership on every container start and then
# drops privileges to appuser itself before running migrations/uvicorn.
ENV VINYL_API_DATABASE_URL=sqlite:////data/vinyl_api.db
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
