from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime


class ListingIn(BaseModel):
    listing_id: str
    price: Optional[float] = None
    currency: Optional[str] = None
    condition: Optional[str] = None
    sleeve_condition: Optional[str] = Field(None, alias="sleeve")
    ships_from: Optional[str] = None
    seller: Optional[str] = None
    listing_url: Optional[str] = Field(None, alias="url")
    last_fetched: Optional[datetime] = None
    price_usd: Optional[float] = None
    ships_to_us: Optional[str] = None
    shipping_notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BulkListings(BaseModel):
    release_id: int
    listings: List[ListingIn]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PlayIn(BaseModel):
    release_id: int
    played_at: Optional[datetime] = None
    source: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
