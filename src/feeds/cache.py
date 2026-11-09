"""Small on-disk cache for big third-party camera lists.

Some sources publish their whole camera list as one large JSON file. Rather
than re-download it on every run, keep a copy in data/cache/ and refresh it
when it is older than max_age_days.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from src.feeds.http import session

CACHE_DIR = Path("data/cache")


def cached_json(url: str, name: str, max_age_days: float = 7):
    """Return parsed JSON from url, using data/cache/<name> if it is fresh."""
    path = CACHE_DIR / name
    if path.exists() and time.time() - path.stat().st_mtime < max_age_days * 86400:
        return json.loads(path.read_text(encoding="utf-8"))

    resp = session.get(url, timeout=180)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig")
    data = json.loads(text)  # validate before replacing the old copy
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return data
