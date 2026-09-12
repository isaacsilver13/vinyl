from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from .database import Base
from datetime import datetime, timezone


def _utcnow():
    return datetime.now(timezone.utc)


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(String, unique=True, index=True, nullable=False)
    release_id = Column(Integer, index=True, nullable=False)
    price = Column(Float)
    currency = Column(String(8))
    condition = Column(String(64))
    sleeve_condition = Column(String(64))
    ships_from = Column(String(128))
    seller = Column(String(256))
    listing_url = Column(String(1024))
    last_fetched = Column(DateTime)
    price_usd = Column(Float)
    ships_to_us = Column(String(64))
    shipping_notes = Column(Text)
    created_at = Column(DateTime, default=_utcnow)


class Play(Base):
    __tablename__ = "plays"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    release_id = Column(Integer, index=True, nullable=False)
    played_at = Column(DateTime, nullable=False)
    source = Column(String(128))
    notes = Column(Text)
    created_at = Column(DateTime, default=_utcnow)
