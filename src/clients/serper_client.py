from __future__ import annotations

import requests
from tenacity import RetryError

from src.config import settings
from src.utils.cache import DiskCache
from src.utils.retry import exhausted, with_retries

_ENDPOINT = "https://google.serper.dev/search"
_cache = DiskCache("serper")


@with_retries(exceptions=(requests.RequestException,))
def _search(keyword: str) -> dict:
    resp = requests.post(
        _ENDPOINT,
        headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
        json={"q": keyword},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def search(keyword: str) -> dict:
    """Raw Serper response for a keyword: organic results + People Also Ask. Cached."""
    cached = _cache.get({"keyword": keyword})
    if cached is not None:
        return cached

    try:
        data = _search(keyword)
    except RetryError as e:
        raise exhausted(e, "Serper") from e

    _cache.set({"keyword": keyword}, data)
    return data
