from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

# SQLite's INTEGER storage class is a signed 64-bit int. A plain Pydantic
# `int` field has no upper/lower bound, so a request with e.g. release_id
# way outside this range currently passes validation (422 territory) and
# instead blows up as an unhandled OverflowError/sqlite3 error down in the DB
# layer -- a 500 instead of a 422. Bound every DB-backed integer field to
# this range so out-of-range values are rejected as ordinary validation
# errors.
_SQLITE_INT_MIN = -(2**63)
_SQLITE_INT_MAX = 2**63 - 1


class ListingIn(BaseModel):
    listing_id: str = Field(min_length=1)
    price: Optional[float] = Field(default=None, allow_inf_nan=False)
    currency: Optional[str] = None
    condition: Optional[str] = None
    sleeve_condition: Optional[str] = Field(None, alias="sleeve")
    ships_from: Optional[str] = None
    seller: Optional[str] = None
    listing_url: Optional[str] = Field(None, alias="url")
    last_fetched: Optional[datetime] = None
    price_usd: Optional[float] = Field(default=None, allow_inf_nan=False)
    ships_to_us: Optional[str] = None
    shipping_notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BulkListings(BaseModel):
    release_id: int = Field(ge=_SQLITE_INT_MIN, le=_SQLITE_INT_MAX)
    # Bounds the request body itself (not just per-row validation) so a huge
    # payload can't pin the small Fly machine's CPU/memory past its
    # healthcheck timeout -- the bulk endpoint does one SELECT per row, so
    # this also caps the worst-case N+1 query count for a single request.
    listings: List[ListingIn] = Field(max_length=5000)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PlayIn(BaseModel):
    release_id: int = Field(ge=_SQLITE_INT_MIN, le=_SQLITE_INT_MAX)
    played_at: Optional[datetime] = None
    source: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
