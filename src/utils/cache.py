"""
Minimal cache for external API responses, keyed by a hash of the
inputs. Not a general-purpose cache library on purpose — this pipeline
only needs "don't call Serper/Firecrawl twice for the same input" and
a stdlib-only implementation is one less dependency and one less
thing that can break in front of a client.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from src.config import settings


class DiskCache:
    def __init__(self, namespace: str):
        self.dir = Path(settings.cache_dir) / namespace
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(payload: Any) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()

    def get(self, payload: Any) -> Optional[Any]:
        if not settings.cache_enabled:
            return None
        path = self.dir / f"{self._key(payload)}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, payload: Any, value: Any) -> None:
        if not settings.cache_enabled:
            return
        path = self.dir / f"{self._key(payload)}.json"
        try:
            path.write_text(json.dumps(value, default=str))
        except OSError:
            pass  # cache is a nice-to-have, never let it break the pipeline
