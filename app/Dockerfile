# syntax=docker/dockerfile:1
FROM python:3.12-slim

# System deps (for cloudscraper / bcrypt native wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Persistent data lives on a Fly volume mounted at /data
ENV VINYL_DATA_DIR=/data

# Run as a non-root user for the app process itself. /data and entrypoint.sh's
# +x bit are set up here, but ownership of /data is NOT the final word: a real
# Fly volume mount replaces this directory with a fresh, root-owned one at
# runtime, so build-time chown alone doesn't survive deployment. entrypoint.sh
# re-chowns /data on every container start (while still root) before dropping
# to appuser -- see entrypoint.sh for why.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data \
    && chmod +x /app/entrypoint.sh

# Expose Streamlit default port
EXPOSE 8501

# Streamlit config: disable telemetry, listen on all interfaces
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true

# Deliberately stay root here (no USER directive): entrypoint.sh needs root to
# chown the mounted volume before it execs into the app as appuser itself.
ENTRYPOINT ["./entrypoint.sh"]
