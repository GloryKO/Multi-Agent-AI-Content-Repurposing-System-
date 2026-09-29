from __future__ import annotations

import requests
from tenacity import RetryError

from src.config import settings
from src.schemas import ImageResult
from src.utils.cache import DiskCache
from src.utils.retry import exhausted, with_retries

_ENDPOINT = "https://api.pexels.com/v1/search"
_cache = DiskCache("pexels")


@with_retries(exceptions=(requests.RequestException,))
def _search(query: str) -> dict:
    resp = requests.get(
        _ENDPOINT,
        headers={"Authorization": settings.pexels_api_key},
        params={"query": query, "per_page": 1, "orientation": "landscape"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def find_image(query: str, alt_text: str) -> ImageResult | None:
    """Returns the top relevant, commercially-free image for a query, or
    None if nothing is found (image is a nice-to-have, never a hard
    dependency for pipeline success)."""
    cached = _cache.get({"query": query})
    if cached is None:
        try:
            cached = _search(query)
        except RetryError as e:
            raise exhausted(e, "Pexels") from e
        _cache.set({"query": query}, cached)

    photos = cached.get("photos") or []
    if not photos:
        return None

    photo = photos[0]
    return ImageResult(
        url=photo["src"]["large"],
        photographer=photo["photographer"],
        photographer_url=photo["photographer_url"],
        alt_text=alt_text,
    )
