import os
import shutil
import sys
import tempfile

import pytest

# Ensure repo root (the `api/` directory) is on sys.path so `vinyl_api` and
# `tests` import cleanly regardless of how pytest is invoked (mirrors the
# manual sys.path setup in test_schemas.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# `vinyl_api.database` reads VINYL_API_DATABASE_URL at *import time*
# (`DB_URL = os.environ.get(...)` at module level), so this must be set
# before anything imports `vinyl_api` -- including other test modules such
# as test_api.py, which does `from vinyl_api.main import app` at the top of
# the file. conftest.py is guaranteed to be imported by pytest before any
# test module in this directory is collected, so setting the env var here
# (at module import time, not inside a fixture function) is what actually
# guarantees ordering; a fixture would run too late, after collection has
# already imported the app against the default DB_URL.
#
# Without this, tests run against the repo's default
# sqlite:///./vinyl_api_dev.db, so state accumulates across local `pytest`
# runs (e.g. test_health_metrics_reflects_activity can fail on a second run).
# Using a fresh temp file per test session keeps every run isolated.
#
# mkdtemp() (not TemporaryDirectory) plus an explicit ignore_errors cleanup
# below -- SQLAlchemy's engine (and its underlying sqlite3 connections) isn't
# explicitly disposed anywhere in this test session, so on Windows the DB
# file can still be handle-locked at interpreter/session teardown time.
# TemporaryDirectory's own .cleanup() raises in that case (it doesn't ignore
# per-file removal errors); shutil.rmtree(..., ignore_errors=True) is the
# more robust choice here -- best-effort cleanup that never turns an
# otherwise-green test run into a failure, while still actually removing the
# directory on every OS/session where nothing has it locked (i.e. always on
# Linux/macOS, and Windows whenever the engine happens to have already
# released its handle).
_tmp_dir_path = tempfile.mkdtemp(prefix="vinyl_api_test_")
_tmp_db_path = os.path.join(_tmp_dir_path, "test.db").replace(os.sep, "/")
os.environ["VINYL_API_DATABASE_URL"] = f"sqlite:///{_tmp_db_path}"


def pytest_unconfigure(config):  # noqa: ARG001 -- pytest hook signature
    shutil.rmtree(_tmp_dir_path, ignore_errors=True)


# vinyl_api.main's startup lifespan no longer calls database.init_db()
# (Base.metadata.create_all) -- Alembic (via migrate_or_stamp.py) is now the
# single source of schema truth, matching production's
# `python migrate_or_stamp.py && uvicorn ...` startup sequence (see
# Dockerfile/entrypoint.sh). So the test suite has to run that same step
# against this session's temp DB itself, before anything imports
# vinyl_api.main and starts querying tables that wouldn't otherwise exist.
import migrate_or_stamp  # noqa: E402
from vinyl_api import error_log  # noqa: E402

migrate_or_stamp.main()


@pytest.fixture(autouse=True)
def _reset_error_log_ring_buffer():
    """Reset the process-wide /health/errors ring buffer before each test.

    error_log._recent_errors is module-level state shared across the whole
    test process, not per-request or per-test. Without this, a test that logs
    an ERROR (e.g. test_health_errors_reflects_logged_errors) leaks that
    entry into every test that runs after it, so assertions like
    `errors == []` in test_health_errors_returns_a_list only pass because of
    where pytest happens to order tests, not because the behavior is
    actually correct.
    """
    error_log.clear()
