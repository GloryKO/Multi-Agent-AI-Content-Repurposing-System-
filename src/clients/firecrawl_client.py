from __future__ import annotations

from firecrawl import Firecrawl
from tenacity import RetryError

from src.config import settings
from src.utils.cache import DiskCache
from src.utils.retry import UpstreamFailure, exhausted, with_retries

_cache = DiskCache("firecrawl")
_app: Firecrawl | None = None


def _get_app() -> Firecrawl:
    global _app
    if _app is None:
        _app = Firecrawl(api_key=settings.firecrawl_api_key or "missing-key")
    return _app


@with_retries(exceptions=(Exception,))
def _scrape(url: str):
    return _get_app().scrape(url, formats=["markdown"])


def _extract_markdown(result) -> str:
    """Handle both Document objects (v2) and dict-shaped responses."""
    if hasattr(result, "markdown"):
        return result.markdown or ""
    if isinstance(result, dict):
        return result.get("markdown") or result.get("content") or ""
    return ""


def scrape(url: str) -> str:
    """Returns clean markdown content for a URL. Cached by URL."""
    cached = _cache.get({"url": url})
    if cached is not None:
        return cached["content"]

    try:
        result = _scrape(url)
    except RetryError as e:
        raise exhausted(e, "Firecrawl") from e

    content = _extract_markdown(result)
    if not content.strip():
        raise UpstreamFailure(f"Firecrawl returned empty content for {url}")

    _cache.set({"url": url}, {"content": content})
    return content
