import sys, os
import pytest
from pydantic import ValidationError

# Ensure repo root is on sys.path so `vinyl_api` package imports during tests
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from vinyl_api import schemas
from datetime import datetime


def test_bulk_listings_valid():
    payload = {
        "release_id": 123,
        "listings": [
            {"listing_id": "abc", "price": 12.5, "currency": "USD"},
        ],
    }
    obj = schemas.BulkListings(**payload)
    assert obj.release_id == 123
    assert len(obj.listings) == 1


def test_bulk_listings_extra_fields_rejected():
    payload = {
        "release_id": 123,
        "listings": [
            {"listing_id": "abc", "price": 12.5, "currency": "USD", "extra": 1},
        ],
    }
    with pytest.raises(ValidationError):
        schemas.BulkListings(**payload)


def test_playin_validation():
    payload = {"release_id": 42}
    obj = schemas.PlayIn(**payload)
    assert obj.release_id == 42

    # extra fields rejected
    with pytest.raises(ValidationError):
        schemas.PlayIn(**{"release_id": 42, "bad": 1})
