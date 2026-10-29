"""Import cameras from OpenTrafficCamMap.

OpenTrafficCamMap (https://github.com/AidanWelch/OpenTrafficCamMap) is an MIT-
licensed database of public traffic cameras compiled from transport
authorities' own camera lists. Its data lives in one JSON file per country:

    {"<state>": {"<county>": [ {description, latitude, longitude, url,
                                encoding, format, direction?, updateRate?,
                                markedForReview?}, ... ]}}

Skipped on import:
  - cameras marked for review (the project flags them as possibly wrong)
  - cameras at (0, 0), which the project says are bad coordinates
  - "UNIQUE_*" formats that need special per-agency handling to view

The dataset is crowdsourced and not updated every day, so some links will be
dead. Run the scanner to find out which ones work.
"""

from __future__ import annotations

import hashlib
import json
import re

from src.feeds.formats import FORMAT_TO_URL_TYPE, with_format
from src.feeds.http import session

RAW_URL = "https://raw.githubusercontent.com/AidanWelch/OpenTrafficCamMap/master/cameras/{country}.json"
COUNTRIES = ["USA"]  # countries OpenTrafficCamMap currently publishes


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "other"


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def convert(country: str, data: dict) -> tuple[list[dict], dict]:
    """Turn OpenTrafficCamMap's nested JSON into ACE camera records."""
    cameras: list[dict] = []
    skipped = {"marked for review": 0, "bad location": 0, "unsupported format": 0, "no url": 0}
    prefix = "us" if country == "USA" else country.lower()

    for region, counties in data.items():
        for county, items in (counties or {}).items():
            for cam in items or []:
                url = (cam.get("url") or "").strip()
                fmt = (cam.get("format") or "").upper()
                lat, lon = _float(cam.get("latitude")), _float(cam.get("longitude"))
                if not url:
                    skipped["no url"] += 1
                    continue
                if cam.get("markedForReview"):
                    skipped["marked for review"] += 1
                    continue
                if lat is None or lon is None or (abs(lat) < 0.01 and abs(lon) < 0.01):
                    skipped["bad location"] += 1
                    continue
                url_type = FORMAT_TO_URL_TYPE.get(fmt)
                if not url_type:
                    skipped["unsupported format"] += 1
                    continue

                # Stable ID from the stream URL, so re-imports keep the same IDs.
                digest = hashlib.sha1(url.encode()).hexdigest()[:10]
                update_rate = cam.get("updateRate")
                cameras.append(with_format({
                    "id": f"{prefix}-{_slug(region)}:{digest}",
                    "source": f"{prefix}-{_slug(region)}",
                    "category": "traffic",
                    "country": country,
                    "region": region,
                    "county": county,
                    "road": None,
                    "direction": cam.get("direction"),
                    "description": cam.get("description"),
                    "lat": lat,
                    "lon": lon,
                    "stream_url": url,
                    "url_type": url_type,
                    "encoding": cam.get("encoding"),
                    "format": fmt,
                    "update_rate": int(update_rate) if str(update_rate or "").isdigit() else None,
                }))
    return cameras, skipped


def fetch_country(country: str) -> list[dict]:
    resp = session.get(RAW_URL.format(country=country), timeout=60)
    resp.raise_for_status()
    cameras, skipped = convert(country, json.loads(resp.content.decode("utf-8-sig")))
    skipped_text = ", ".join(f"{v} {k}" for k, v in skipped.items() if v)
    print(f"  {len(cameras)} cameras" + (f" (skipped {skipped_text})" if skipped_text else ""))
    return cameras


def fetch_all(countries: list[str] | None = None) -> list[dict]:
    cameras: list[dict] = []
    for country in countries or COUNTRIES:
        print(f"Fetching OpenTrafficCamMap {country}...")
        try:
            cameras += fetch_country(country)
        except Exception as e:  # one failing country shouldn't stop the run
            print(f"  ! skipped: {e}")
    return cameras
