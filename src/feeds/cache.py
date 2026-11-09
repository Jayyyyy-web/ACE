"""Small on-disk cache for third-party camera lists.

Some sources publish their whole camera list as one large file, and some ask
users not to download it too often. Rather than re-download on every run,
keep a copy in data/cache/ and refresh it when it is older than max_age_days.
If a refresh fails (offline, or the source is down), the old copy is used.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from src.feeds.http import session

CACHE_DIR = Path("data/cache")


def _age_days(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 86400


def cached_bytes(url: str, name: str, max_age_days: float = 7,
                 check: Callable[[bytes], object] | None = None) -> bytes:
    """Return the body of url, using data/cache/<name> if it is fresh.

    check(body) may raise to reject a bad download (an error page, say)
    before it replaces the old copy.
    """
    path = CACHE_DIR / name
    if path.exists() and _age_days(path) < max_age_days:
        return path.read_bytes()
    try:
        resp = session.get(url, timeout=180)
        resp.raise_for_status()
        body = resp.content
        if check:
            check(body)
    except Exception as e:
        if path.exists():
            print(f"  (couldn't refresh, using the copy from {_age_days(path):.0f} days ago: "
                  f"{type(e).__name__})")
            return path.read_bytes()
        raise
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def cached_text(url: str, name: str, max_age_days: float = 7,
                check: Callable[[str], object] | None = None) -> str:
    """Like cached_bytes, decoded as UTF-8."""
    decode = lambda body: body.decode("utf-8-sig")  # noqa: E731
    body = cached_bytes(url, name, max_age_days,
                        check=(lambda b: check(decode(b))) if check else decode)
    return decode(body)


def cached_json(url: str, name: str, max_age_days: float = 7):
    """Return parsed JSON from url, using data/cache/<name> if it is fresh."""
    return json.loads(cached_text(url, name, max_age_days, check=json.loads))
