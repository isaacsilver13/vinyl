import hmac
import logging
import math
import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException, Path, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from typing import Optional
from . import database, models, schemas
from .error_log import install as install_error_log, recent_errors
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from datetime import datetime, timezone

install_error_log()

logger = logging.getLogger(__name__)

# SQLite's INTEGER storage class is a signed 64-bit int -- see schemas.py for
# the matching bound on request-body integer fields. user_id arrives as a
# path parameter rather than a body field, so it needs the same bound applied
# via Path() instead of Field().
_SQLITE_INT_MIN = -(2**63)
_SQLITE_INT_MAX = 2**63 - 1


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("VINYL_API_ENV", "local") != "local" and not os.environ.get("VINYL_API_KEY"):
        raise RuntimeError(
            "VINYL_API_KEY must be set when VINYL_API_ENV is not 'local' "
            "(refusing to start with write endpoints unauthenticated)."
        )
    # Schema creation/migration is handled entirely by migrate_or_stamp.py
    # (run as a separate step before this process starts -- see Dockerfile
    # CMD/entrypoint.sh and tests/conftest.py). Do NOT call
    # database.init_db() (Base.metadata.create_all) here: with real Alembic
    # migrations now in place, create_all must not be a second, uncoordinated
    # source of schema truth -- it would silently re-create any table/column
    # a future migration intentionally drops or renames.
    yield


def _docs_urls(is_local: bool) -> dict:
    """FastAPI docs_url/redoc_url/openapi_url kwargs for the given environment.

    /docs, /redoc, and the raw OpenAPI schema are dev conveniences for an
    internal write-only API sink -- don't serve them publicly in production.
    Pulled into its own function (rather than inlined at app construction)
    so the on/off behavior can be unit tested without reloading this module.
    """
    if is_local:
        return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


_is_local_env = os.environ.get("VINYL_API_ENV", "local") == "local"
app = FastAPI(title="Vinyl API (dev)", lifespan=lifespan, **_docs_urls(_is_local_env))


def _json_safe_float(value: float):
    """Stringify NaN/Infinity so they survive Starlette's strict json.dumps.

    Rejecting a NaN/Infinity price (schemas.py's allow_inf_nan=False) makes
    Pydantic echo the raw rejected float back in the 422 error detail's
    "input" field. Starlette's JSONResponse serializes with allow_nan=False,
    so without this, encoding that error response itself raises and turns a
    422 into an unhandled 500 -- this keeps the rejection a clean 422.
    """
    if value != value or math.isinf(value):  # NaN != NaN by definition
        return str(value)
    return value


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors(), custom_encoder={float: _json_safe_float})},
    )


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


@app.get("/health/errors", dependencies=[Depends(require_api_key)])
def health_errors() -> dict[str, object]:
    # Gated behind the same bearer-key auth as the write endpoints: this
    # ring buffer captures every ERROR-level record logged anywhere on the
    # root logger (not just the sanitized 500-handlers below), which can
    # include messages from dependencies containing things like connection
    # strings -- it must not be publicly readable.
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
    # Deduplicate by listing_id within this request, keeping the last
    # occurrence. SessionLocal is autoflush=False, so a naive per-row
    # "does this exist?" query inside the loop below would not see
    # earlier inserts from this same request/loop, and two listings
    # sharing a listing_id would both be added and blow up the unique
    # constraint on commit -- discarding the whole batch.
    deduped_listings: dict[str, schemas.ListingIn] = {}
    for lst in payload.listings:
        deduped_listings[lst.listing_id] = lst
    try:
        for lst in deduped_listings.values():
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
    except Exception:
        db.rollback()
        logger.exception("Failed to persist bulk listings for release_id=%s", payload.release_id)
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()

    return {"saved": saved}


@app.post("/users/{user_id}/plays", dependencies=[Depends(require_api_key)])
def log_play(payload: schemas.PlayIn, user_id: int = Path(ge=_SQLITE_INT_MIN, le=_SQLITE_INT_MAX)):
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
    except Exception:
        db.rollback()
        logger.exception("Failed to log play for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()

    return {"id": obj.id, "user_id": obj.user_id, "release_id": obj.release_id}
