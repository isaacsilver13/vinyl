"""Simple HTTP client for the local Vinyl API used by scheduled scripts.

This is intentionally minimal: it reads `VINYL_API_URL` and `VINYL_API_KEY` from
the environment and POSTs to `/listings/bulk` for demo purposes.
"""
from __future__ import annotations

import hashlib
import os
import requests
from typing import List, Dict, Any
from urllib.parse import urlparse

_LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def _api_url() -> str:
    url = os.environ.get("VINYL_API_URL", "http://127.0.0.1:8000")
    app_env = os.environ.get("VINYL_APP_ENV", "local").strip().lower()
    if app_env == "local" and urlparse(url).hostname not in _LOCAL_HOSTS:
        raise RuntimeError(
            f"VINYL_API_URL={url!r} points outside localhost while VINYL_APP_ENV=local "
            "(refusing to let local dev write to a non-local API). Set "
            "VINYL_APP_ENV=production if this is intentional."
        )
    return url


def _api_key() -> str | None:
    return os.environ.get("VINYL_API_KEY")


def _headers() -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    api_key = _api_key()
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def post_listings_bulk(release_id: int, listings: List[Dict[str, Any]]) -> Dict[str, Any]:
    url = f"{_api_url().rstrip('/')}/listings/bulk"
    # strip any fields not in the allowed ListingIn schema to satisfy strict validation
    allowed = {
        "listing_id",
        "price",
        "currency",
        "condition",
        "sleeve",
        "sleeve_condition",
        "ships_from",
        "seller",
        "url",
        "listing_url",
        "last_fetched",
        "price_usd",
        "ships_to_us",
        "shipping_notes",
    }
    cleaned = []
    for lst in listings:
        # coerce mapping-like rows (e.g., SQL row mapping) to dict
        if not isinstance(lst, dict):
            try:
                lst = dict(lst)
            except Exception:
                continue

        cl = {k: v for k, v in lst.items() if k in allowed}

        # ensure listing_id exists - skip otherwise
        if not cl.get("listing_id"):
            # try common alternatives
            if lst.get("id"):
                cl["listing_id"] = str(lst.get("id"))
            elif lst.get("listing_url"):
                # Stable, process-independent id: Python's built-in hash() is
                # salted per-process (PYTHONHASHSEED), so it produced a
                # different value every run and made the same real-world
                # listing look "new" each time.
                cl["listing_id"] = hashlib.sha256(
                    lst.get("listing_url").encode("utf-8")
                ).hexdigest()
            else:
                # skip entries without an identifier
                continue

        # normalize last_fetched to ISO str if datetime
        lf = cl.get("last_fetched")
        if lf is not None:
            import datetime as _dt
            if isinstance(lf, _dt.datetime):
                cl["last_fetched"] = lf.isoformat()

        cleaned.append(cl)
    payload = {"release_id": release_id, "listings": cleaned}
    resp = requests.post(url, json=payload, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def log_play(user_id: int, release_id: int, played_at: str | None = None, source: str | None = None, notes: str | None = None) -> Dict[str, Any]:
    url = f"{_api_url().rstrip('/')}/users/{user_id}/plays"
    payload = {"release_id": release_id}
    if played_at:
        payload["played_at"] = played_at
    if source:
        payload["source"] = source
    if notes:
        payload["notes"] = notes

    resp = requests.post(url, json=payload, headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()
