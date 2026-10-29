"""Fetch Taiwan's public traffic camera (CCTV) list from TDX.

Pulls the freeway network plus every city/county network, normalises them
into one simple format, and saves the result to data/cameras.json.

Run it with:
    python -m src.feeds.cameras              # everything
    python -m src.feeds.cameras NewTaipei    # just one or more cities
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import requests

from src.feeds.tdx_auth import TDXAuthError, get_auth

BASE_URL = "https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/CCTV"

# TDX city codes.
CITIES = [
    "Taipei", "NewTaipei", "Keelung", "Taoyuan", "Hsinchu", "HsinchuCounty",
    "MiaoliCounty", "Taichung", "ChanghuaCounty", "NantouCounty", "YunlinCounty",
    "Chiayi", "ChiayiCounty", "Tainan", "Kaohsiung", "PingtungCounty",
    "YilanCounty", "HualienCounty", "TaitungCounty", "PenghuCounty",
    "KinmenCounty", "LienchiangCounty",
]

OUTPUT_PATH = Path("data/cameras.json")

# Small pause between requests so we stay well under TDX's rate limits.
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 3


def _get_json(url: str) -> dict | None:
    """GET a TDX endpoint, retrying politely on rate limits. Returns None on failure."""
    auth = get_auth()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                params={"$format": "JSON"},
                headers=auth.headers(),
                timeout=30,
            )
        except requests.RequestException as e:
            print(f"  ! network error ({e}); attempt {attempt}/{MAX_RETRIES}")
            time.sleep(2 * attempt)
            continue

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            wait = 5 * attempt
            print(f"  ! rate limited, waiting {wait}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        if resp.status_code == 404:
            return None  # This source has no CCTV data published.

        print(f"  ! HTTP {resp.status_code} from {url}")
        return None
    return None


def _normalise(raw: dict, source: str) -> dict:
    """Turn one raw TDX CCTV record into our own simple format."""
    return {
        "id": f"{source}:{raw.get('CCTVID')}",
        "source": source,
        "road": raw.get("RoadName"),
        "direction": raw.get("RoadDirection"),
        "description": raw.get("SurveillanceDescription"),
        "lat": raw.get("PositionLat"),
        "lon": raw.get("PositionLon"),
        "stream_url": raw.get("VideoStreamURL") or raw.get("VideoImageURL"),
        "refresh_rate": raw.get("ImageRefreshRate"),
    }


def fetch_source(source: str) -> list[dict]:
    """Fetch cameras for 'Freeway' or one city code."""
    url = f"{BASE_URL}/Freeway" if source == "Freeway" else f"{BASE_URL}/City/{source}"
    data = _get_json(url)
    if not data:
        return []

    records = data.get("CCTVs", []) if isinstance(data, dict) else data
    cameras = [_normalise(r, source) for r in records]
    # Drop cameras with no location or no feed; they're useless on a map.
    return [c for c in cameras if c["lat"] and c["lon"] and c["stream_url"]]


def fetch_all(sources: list[str] | None = None) -> list[dict]:
    sources = sources or ["Freeway", *CITIES]
    all_cameras: list[dict] = []
    for source in sources:
        print(f"Fetching {source}...")
        cameras = fetch_source(source)
        print(f"  {len(cameras)} cameras")
        all_cameras.extend(cameras)
        time.sleep(REQUEST_DELAY_SECONDS)
    return all_cameras


def save(cameras: list[dict], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cameras, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    sources = sys.argv[1:] or None
    try:
        cameras = fetch_all(sources)
    except TDXAuthError as e:
        print(f"Auth problem: {e}")
        sys.exit(1)

    if not cameras:
        print("No cameras returned. Check your keys and connection.")
        sys.exit(1)

    save(cameras)

    print(f"\nFound {len(cameras):,} cameras. Saved to {OUTPUT_PATH}")
    for source, count in Counter(c["source"] for c in cameras).most_common():
        print(f"  {source:<18} {count:>5}")

    print("\nExample camera:")
    print(json.dumps(cameras[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
