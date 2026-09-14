import pytest
from fastapi.testclient import TestClient

from vinyl_api.main import app, lifespan


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def listing_payload():
    return {
        "release_id": 123,
        "listings": [{"listing_id": "api-test", "price": 12.5, "currency": "USD"}],
    }


def test_health_is_public(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_writes_require_configured_api_key(client, monkeypatch):
    monkeypatch.setenv("VINYL_API_KEY", "test-secret")

    response = client.post("/listings/bulk", json=listing_payload())

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_writes_accept_configured_api_key(client, monkeypatch):
    monkeypatch.setenv("VINYL_API_KEY", "test-secret")

    response = client.post(
        "/listings/bulk",
        json=listing_payload(),
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"saved": 1}


def test_keyless_local_mode_allows_writes(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    response = client.post("/listings/bulk", json=listing_payload())

    assert response.status_code == 200
    assert response.json() == {"saved": 1}


def test_repeat_bulk_post_upserts_instead_of_duplicating(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)
    payload = {
        "release_id": 999,
        "listings": [
            {"listing_id": "upsert-test", "price": 10.0, "currency": "USD"}
        ],
    }

    first = client.post("/listings/bulk", json=payload)
    payload["listings"][0]["price"] = 20.0
    second = client.post("/listings/bulk", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200

    from vinyl_api import database, models

    db = database.SessionLocal()
    try:
        rows = (
            db.query(models.Listing)
            .filter(models.Listing.listing_id == "upsert-test")
            .all()
        )
    finally:
        db.close()

    assert len(rows) == 1
    assert rows[0].price == 20.0


def test_health_ready(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "healthy"


def test_health_metrics_reports_counts(client):
    response = client.get("/health/metrics")
    assert response.status_code == 200
    assert "listing_count" in response.json()
    assert "play_count" in response.json()


def test_health_metrics_reflects_activity(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)
    before = client.get("/health/metrics").json()["listing_count"]
    unique_payload = {
        "release_id": 999,
        "listings": [{"listing_id": "health-metrics-test", "price": 1.0, "currency": "USD"}],
    }
    client.post("/listings/bulk", json=unique_payload)

    response = client.get("/health/metrics")

    assert response.status_code == 200
    assert response.json()["listing_count"] == before + 1
    assert response.json()["data_freshness_at"] is not None


def test_health_errors_isolated_from_a_prior_tests_logged_error(client, monkeypatch):
    """Regression test for the ring buffer's process-wide state leaking across
    tests (see conftest.py's `_reset_error_log_ring_buffer` autouse fixture).

    Deliberately logs an error here, then relies on test collection order
    (this test runs immediately before test_health_errors_returns_a_list) to
    prove the *next* test doesn't see it. Without the autouse reset fixture,
    this ordering would make test_health_errors_returns_a_list fail.
    """
    monkeypatch.delenv("VINYL_API_KEY", raising=False)
    import logging

    logging.getLogger("vinyl_api.test").error("isolation-check: should not leak")

    response = client.get("/health/errors")
    assert response.status_code == 200
    assert any(
        "isolation-check: should not leak" in entry["message"]
        for entry in response.json()["errors"]
    )


def test_health_errors_returns_a_list(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)
    response = client.get("/health/errors")
    assert response.status_code == 200
    assert response.json()["errors"] == []


def test_health_errors_requires_configured_api_key(client, monkeypatch):
    monkeypatch.setenv("VINYL_API_KEY", "test-secret")

    response = client.get("/health/errors")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_health_errors_accepts_configured_api_key(client, monkeypatch):
    monkeypatch.setenv("VINYL_API_KEY", "test-secret")

    response = client.get(
        "/health/errors", headers={"Authorization": "Bearer test-secret"}
    )

    assert response.status_code == 200


def test_duplicate_listing_id_within_one_bulk_request_keeps_last(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)
    payload = {
        "release_id": 111,
        "listings": [
            {"listing_id": "dup-in-batch", "price": 5.0, "currency": "USD"},
            {"listing_id": "dup-in-batch", "price": 15.0, "currency": "USD"},
        ],
    }

    response = client.post("/listings/bulk", json=payload)

    assert response.status_code == 200
    assert response.json() == {"saved": 1}

    from vinyl_api import database, models

    db = database.SessionLocal()
    try:
        rows = (
            db.query(models.Listing)
            .filter(models.Listing.listing_id == "dup-in-batch")
            .all()
        )
    finally:
        db.close()

    assert len(rows) == 1
    assert rows[0].price == 15.0


def test_log_play_happy_path(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    response = client.post(
        "/users/42/plays",
        json={"release_id": 7, "source": "test-suite"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"id", "user_id", "release_id"}
    assert body["user_id"] == 42
    assert body["release_id"] == 7


def test_wrong_api_key_is_rejected(client, monkeypatch):
    monkeypatch.setenv("VINYL_API_KEY", "test-secret")

    response = client.post(
        "/listings/bulk",
        json=listing_payload(),
        headers={"Authorization": "Bearer not-the-right-key"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_malformed_bulk_payload_returns_422(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    # Missing the required "listing_id" field on the listing entry.
    response = client.post(
        "/listings/bulk",
        json={"release_id": 123, "listings": [{"price": 12.5}]},
    )

    assert response.status_code == 422


def test_out_of_range_release_id_returns_422_not_500(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    response = client.post(
        "/listings/bulk",
        json={
            "release_id": 10**30,  # far outside SQLite's signed 64-bit int range
            "listings": [{"listing_id": "range-test", "price": 1.0}],
        },
    )

    assert response.status_code == 422


def test_out_of_range_user_id_path_param_returns_422_not_500(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    response = client.post(
        f"/users/{10**30}/plays",
        json={"release_id": 1},
    )

    assert response.status_code == 422


def test_nan_price_is_rejected(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    # httpx's normal `json=` kwarg refuses to encode NaN/Infinity at all, so
    # send the (still-valid-per-json.loads) raw body directly to reproduce
    # what an actual non-strict client could send.
    response = client.post(
        "/listings/bulk",
        content=b'{"release_id": 1, "listings": [{"listing_id": "nan-test", "price": NaN}]}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_infinite_price_is_rejected(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    response = client.post(
        "/listings/bulk",
        content=b'{"release_id": 1, "listings": [{"listing_id": "inf-test", "price": Infinity}]}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_empty_listing_id_is_rejected(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    response = client.post(
        "/listings/bulk",
        json={"release_id": 1, "listings": [{"listing_id": "", "price": 1.0}]},
    )

    assert response.status_code == 422


def test_oversized_bulk_payload_is_rejected(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    response = client.post(
        "/listings/bulk",
        json={
            "release_id": 1,
            "listings": [
                {"listing_id": f"bulk-{i}", "price": 1.0} for i in range(5001)
            ],
        },
    )

    assert response.status_code == 422


def test_health_errors_reflects_logged_errors(client, monkeypatch):
    monkeypatch.delenv("VINYL_API_KEY", raising=False)
    import logging

    logging.getLogger("vinyl_api.test").error("boom: something went wrong")

    response = client.get("/health/errors")

    assert response.status_code == 200
    errors = response.json()["errors"]
    assert any("boom: something went wrong" in entry["message"] for entry in errors)


def test_docs_urls_disabled_outside_local_env():
    from vinyl_api.main import _docs_urls

    assert _docs_urls(True) == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }
    assert _docs_urls(False) == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


def test_non_local_env_refuses_to_start_without_key(monkeypatch):
    import asyncio

    monkeypatch.setenv("VINYL_API_ENV", "production")
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    async def _enter():
        async with lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="VINYL_API_KEY must be set"):
        asyncio.run(_enter())
