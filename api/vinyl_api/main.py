import hmac
import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException
from typing import Optional
from . import database, models, schemas
from .error_log import install as install_error_log, recent_errors
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from datetime import datetime, timezone

install_error_log()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("VINYL_API_ENV", "local") != "local" and not os.environ.get("VINYL_API_KEY"):
        raise RuntimeError(
            "VINYL_API_KEY must be set when VINYL_API_ENV is not 'local' "
            "(refusing to start with write endpoints unauthenticated)."
        )
    database.init_db()
    yield


app = FastAPI(title="Vinyl API (dev)", lifespan=lifespan)


def require_api_key(authorization: Optional[str] = Header(default=None)) -> None:
    """Require the configured bearer key while allowing keyless local use."""
    expected_key = os.environ.get("VINYL_API_KEY")
    if not expected_key:
        return

    scheme, _, supplied_key = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(supplied_key, expected_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    db: Session = database.SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    finally:
        db.close()
    return {"status": "ok", "database": "healthy"}


@app.get("/health/metrics")
def health_metrics() -> dict[str, object]:
    db: Session = database.SessionLocal()
    try:
        last_listing_sync = db.query(func.max(models.Listing.last_fetched)).scalar()
        last_play_logged = db.query(func.max(models.Play.played_at)).scalar()
        listing_count = db.query(func.count(models.Listing.id)).scalar()
        play_count = db.query(func.count(models.Play.id)).scalar()
    finally:
        db.close()
    return {
        "last_activity_at": last_play_logged,
        "data_freshness_at": last_listing_sync,
        "listing_count": listing_count,
        "play_count": play_count,
    }


@app.get("/health/errors")
def health_errors() -> dict[str, object]:
    return {"errors": recent_errors()}


@app.post("/listings/bulk", dependencies=[Depends(require_api_key)])
def post_listings_bulk(payload: schemas.BulkListings):
    """Accept bulk listings for a release and persist them.

    This endpoint enforces `BulkListings` validation via Pydantic. Extra fields
    in the request will return a 422. Use this strict validation for data
    integrity; update clients to match the schema.
    """
    db: Session = database.SessionLocal()
    saved = 0
    try:
        for lst in payload.listings:
            existing = (
                db.query(models.Listing)
                .filter(models.Listing.listing_id == lst.listing_id)
                .one_or_none()
            )
            fields = dict(
                release_id=payload.release_id,
                price=lst.price,
                currency=lst.currency,
                condition=lst.condition,
                sleeve_condition=lst.sleeve_condition,
                ships_from=lst.ships_from,
                seller=lst.seller,
                listing_url=lst.listing_url,
                last_fetched=lst.last_fetched or datetime.now(timezone.utc),
                price_usd=lst.price_usd,
                ships_to_us=lst.ships_to_us,
                shipping_notes=lst.shipping_notes,
            )
            if existing:
                for key, value in fields.items():
                    setattr(existing, key, value)
            else:
                db.add(models.Listing(listing_id=lst.listing_id, **fields))
            saved += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()

    return {"saved": saved}


@app.post("/users/{user_id}/plays", dependencies=[Depends(require_api_key)])
def log_play(user_id: int, payload: schemas.PlayIn):
    """Log a play for a user.

    Payload: { release_id, played_at (optional ISO), source, notes }
    """
    db: Session = database.SessionLocal()
    try:
        played_at = payload.played_at or datetime.now(timezone.utc)
        obj = models.Play(
            user_id=user_id,
            release_id=payload.release_id,
            played_at=played_at,
            source=payload.source,
            notes=payload.notes,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()

    return {"id": obj.id, "user_id": obj.user_id, "release_id": obj.release_id}
