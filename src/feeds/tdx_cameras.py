"""Fetch Taiwan's traffic camera (CCTV) list from TDX (needs TDX keys in .env).

Covers the freeway network plus every city/county. Use src.feeds.cameras
to run it; this module only does the TDX part.
"""

from __future__ import annotations

import time

import requests

from src.feeds.formats import with_format
from src.feeds.http import session
from src.feeds.tdx_auth import get_auth

BASE_URL = "https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/CCTV"

# TDX city codes.
CITIES = [
    "Taipei", "NewTaipei", "Keelung", "Taoyuan", "Hsinchu", "HsinchuCounty",
    "MiaoliCounty", "Taichung", "ChanghuaCounty", "NantouCounty", "YunlinCounty",
    "Chiayi", "ChiayiCounty", "Tainan", "Kaohsiung", "PingtungCounty",
    "YilanCounty", "HualienCounty", "TaitungCounty", "PenghuCounty",
    "KinmenCounty", "LienchiangCounty",
]

# TDX city code -> OpenStreetMap city/county name.
CITY_NAMES = {
    "Taipei": "臺北市", "NewTaipei": "新北市", "Keelung": "基隆市", "Taoyuan": "桃園市",
    "Hsinchu": "新竹市", "HsinchuCounty": "新竹縣", "MiaoliCounty": "苗栗縣", "Taichung": "臺中市",
    "ChanghuaCounty": "彰化縣", "NantouCounty": "南投縣", "YunlinCounty": "雲林縣", "Chiayi": "嘉義市",
    "ChiayiCounty": "嘉義縣", "Tainan": "臺南市", "Kaohsiung": "高雄市", "PingtungCounty": "屏東縣",
    "YilanCounty": "宜蘭縣", "HualienCounty": "花蓮縣", "TaitungCounty": "臺東縣",
    "PenghuCounty": "澎湖縣", "KinmenCounty": "金門縣", "LienchiangCounty": "連江縣",
}

# Small pause between requests so we stay well under TDX's rate limits.
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 3


def _get_json(url: str) -> dict | None:
    """GET a TDX endpoint, retrying politely on rate limits. Returns None on failure."""
    auth = get_auth()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(
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
    refresh = raw.get("ImageRefreshRate")
    return with_format({
        "id": f"tdx-{source}:{raw.get('CCTVID')}",
        "source": f"tdx-{source}",
        "category": "traffic",
        "country": "TWN",
        "region": CITY_NAMES.get(source, "other"),
        "county": None,
        "road": raw.get("RoadName"),
        "direction": raw.get("RoadDirection"),
        "description": raw.get("SurveillanceDescription"),
        "lat": raw.get("PositionLat"),
        "lon": raw.get("PositionLon"),
        "stream_url": raw.get("VideoStreamURL") or raw.get("VideoImageURL"),
        "url_type": "stream",
        "refresh_rate": refresh,
        "update_rate": int(refresh) * 1000 if isinstance(refresh, (int, float)) and refresh > 0 else None,
    })


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
