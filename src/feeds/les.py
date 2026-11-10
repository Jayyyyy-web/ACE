"""Import road-authority live video from Live-Environment-Streams.

Live-Environment-Streams (https://github.com/william-ricchiuti/Live-Environment-Streams,
CC BY 4.0, by William Ricchiuti) lists about 6,900 public live camera streams
from road authorities in the US, Indonesia, Thailand, Norway, Taiwan and
Germany. What sets it apart: every source has had its terms reviewed
(SOURCES-REVIEW.md in that repo). A source is listed only if its operator
publishes the feed under an open licence or, for public-sector operators,
for the public with no restriction found; sources whose terms forbid reuse
are left out. Its URLs carry no tokens, credentials or session keys, and
each one sits on its own operator's servers.

ACE takes the live video (HLS and MJPEG; short refreshed MP4 clips aren't
live) with a real location, and keeps each camera's attribution, which the
map shows as its publisher. Among them: Norway's Statens vegvesen (NLOD
licence), Thailand's Department of Highways, a dozen Indonesian city
transport offices (Pekanbaru, Magelang, Cianjur, Palembang, Cirebon and
more), and US agencies (Caltrans, Seattle, Maryland, Minnesota, Louisiana,
Delaware, Hawaii, Iowa, Virginia).

The list is downloaded once and cached in data/cache/ for a week.
"""

from __future__ import annotations

import hashlib

from src.feeds.cache import cached_json
from src.feeds.formats import with_format

URL = "https://raw.githubusercontent.com/william-ricchiuti/Live-Environment-Streams/main/streams.geojson"
LICENCE_NOTE = "Live-Environment-Streams (CC BY 4.0)"

ISO3 = {"US": "USA", "ID": "IDN", "TH": "THA", "NO": "NOR", "TW": "TWN", "DE": "DEU"}
TYPES = {"hls": "hls", "mjpeg": "stream"}
# Keelung's cameras already come from data.gov.tw (source "keelung").
SKIP_FAMILIES = {"tdx_city_cctv"}


def convert(data: dict) -> list[dict]:
    cameras = []
    for feat in data.get("features", []):
        p = feat.get("properties") or {}
        kind = TYPES.get(p.get("url_type"))
        url = (p.get("url") or "").strip()
        family = p.get("source_family") or ""
        if (not kind or not url.startswith(("https://", "http://")) or family in SKIP_FAMILIES
                or p.get("source_url_requires") or p.get("coordinates_quality") == "country_centroid"):
            continue
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        src = "les-" + family
        cc = (p.get("country_code") or "").upper()
        cameras.append(with_format({
            "id": f"{src}:{hashlib.sha1(url.encode()).hexdigest()[:10]}",
            "source": src,
            "category": "traffic" if (p.get("environment") or "traffic") == "traffic" else "webcam",
            "country": ISO3.get(cc, cc or "other"),
            "region": p.get("display_name") or None,
            "county": None,
            "road": None,
            "direction": None,
            "description": p.get("name") or None,
            "lat": float(coords[1]),
            "lon": float(coords[0]),
            "stream_url": url,
            "url_type": kind,
            "encoding": "H.264" if kind == "hls" else "JPEG",
            "format": "M3U8" if kind == "hls" else "MJPEG",
            # The credit each operator asks for, shown in the map.
            "publisher": p.get("attribution") or None,
        }))
    return cameras


def fetch_all() -> list[dict]:
    print("Fetching Live-Environment-Streams (licence-reviewed road-authority video)...")
    try:
        data = cached_json(URL, "live-environment-streams.geojson")
    except Exception as e:
        print(f"  ! skipped: {type(e).__name__}: {e}")
        return []
    cameras = convert(data if isinstance(data, dict) else {})
    seen, unique = set(), []
    for c in cameras:
        if c["stream_url"] not in seen:
            seen.add(c["stream_url"])
            unique.append(c)
    print(f"  {len(unique)} live streams from {len({c['source'] for c in unique})} sources")
    return unique
