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


def test_health_errors_returns_a_list(client):
    response = client.get("/health/errors")
    assert response.status_code == 200
    assert response.json()["errors"] == []


def test_non_local_env_refuses_to_start_without_key(monkeypatch):
    import asyncio

    monkeypatch.setenv("VINYL_API_ENV", "production")
    monkeypatch.delenv("VINYL_API_KEY", raising=False)

    async def _enter():
        async with lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="VINYL_API_KEY must be set"):
        asyncio.run(_enter())
