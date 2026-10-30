"""Import US DOT cameras from the 'seeallthethings' list.

Source: https://github.com/baywolf88/seeallthethings (last updated 2018, no
stated licence). That repo is a mixed OSINT list; ACE imports ONLY its
government department-of-transportation feeds:

  South Carolina file -> SCDOT highway cameras (HLS video)
  DC Area file        -> VDOT / DDOT / SHA / Montgomery County, via
                         TrafficLand still images

It deliberately drops the repo's private-camera material. The file has a
header of Shodan search queries and Google "dork" links (insecam.org,
opentopia.com, ip-24.net) for finding unsecured private cameras; those are
query strings, not feeds, and never parse into entries. As a safeguard,
_BLOCKED_HOSTS below is refused even if the format ever changes: ACE does not
pull cameras whose owners did not choose to publish them.

The list is from 2018, so most links are dead (TrafficLand tokens expire).
Run the scanner to find the few that still work.
"""

from __future__ import annotations

import hashlib
import json
import re

from src.feeds.formats import with_format
from src.feeds.http import session

BASE = "https://raw.githubusercontent.com/baywolf88/seeallthethings/master/"
SC_FILE = "South%20Carolina"
DC_FILE = "DC%20Area"

# Hosts that serve unsecured private cameras — never imported, in any file.
_BLOCKED_HOSTS = ("insecam", "opentopia", "ip-24.net", "shodan")

# ISO regions / friendly source names per provider.
_PROVIDERS = {
    "SCDOT": ("South Carolina", "saat-scdot"),
    "VDOT": ("Virginia", "saat-vdot"),
    "DDOT": ("District of Columbia", "saat-ddot"),
    "SHA": ("Maryland", "saat-md-sha"),
    "Montgomery": ("Maryland", "saat-montgomery-md"),
}


def _blocked(url: str) -> bool:
    low = url.lower()
    return any(h in low for h in _BLOCKED_HOSTS)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "other"


def _record(url: str, lat: float, lon: float, name: str, provider: str, url_type: str) -> dict | None:
    if not url or _blocked(url) or lat is None or lon is None:
        return None
    region, source = _PROVIDERS.get(provider, ("other", f"saat-{_slug(provider)}"))
    fmt = "M3U8" if url_type == "hls" else "IMAGE_STREAM"
    digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    return with_format({
        "id": f"{source}:{digest}",
        "source": source,
        "category": "traffic",
        "country": "USA",
        "region": region,
        "county": None,
        "road": None,
        "direction": None,
        "description": name or None,
        "lat": lat,
        "lon": lon,
        "stream_url": url,
        "url_type": url_type,
        "encoding": "H.264" if url_type == "hls" else "JPEG",
        "format": fmt,
    })


def _parse_sc(text: str) -> list[dict]:
    """South Carolina: blocks separated by a 'coordinates' marker, each with
    lon, lat, a label, an 'N:  name' line, an .m3u8 URL, 'SCDOT', city, rtmp."""
    out = []
    blocks = text.split("coordinates")
    for block in blocks[1:]:  # blocks[0] is the Shodan/dork header
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 4:
            continue
        try:
            lon, lat = float(lines[0]), float(lines[1])
        except ValueError:
            continue
        name = next((re.sub(r"^\d+:\s*", "", ln) for ln in lines if re.match(r"^\d+:\s", ln)), "")
        m3u8 = next((ln for ln in lines if ".m3u8" in ln and ln.startswith("http")), None)
        if not m3u8:
            continue  # rtmp-only entries can't play in a browser; skip
        rec = _record(m3u8, lat, lon, name, "SCDOT", "hls")
        if rec:
            out.append(rec)
    return out


def _parse_dc(text: str) -> list[dict]:
    """DC Area: entries begin with name:"...", carry provider:"...", a
    location:{...} JSON block with latitude/longitude, then a feed URL line."""
    out = []
    # Each entry starts at a name:" and runs until the next one.
    entries = re.split(r'(?=name:")', text)
    for entry in entries:
        if 'name:"' not in entry:
            continue
        name = (re.search(r'name:"([^"]*)"', entry) or [None, ""])[1]
        provider = (re.search(r'provider:"([^"]*)"', entry) or [None, ""])[1]
        lat = re.search(r'latitude:\s*(-?\d+\.?\d*)', entry)
        lon = re.search(r'longitude:\s*(-?\d+\.?\d*)', entry)
        url = re.search(r'https?://\S+', entry)
        if not (lat and lon and url):
            continue
        rec = _record(url.group(0).rstrip(",").strip(), float(lat.group(1)),
                      float(lon.group(1)), name, provider, "image")
        if rec:
            out.append(rec)
    return out


def _fetch(path: str) -> str:
    resp = session.get(BASE + path, timeout=45)
    resp.raise_for_status()
    return resp.content.decode("utf-8", "ignore")


def fetch_all() -> list[dict]:
    print("Fetching seeallthethings US DOT cameras (SCDOT, VDOT/DDOT/SHA)...")
    cameras: list[dict] = []
    for path, parser, label in ((SC_FILE, _parse_sc, "South Carolina"),
                                (DC_FILE, _parse_dc, "DC area")):
        try:
            cams = parser(_fetch(path))
        except Exception as e:  # one file failing shouldn't stop the run
            print(f"  ! {label} skipped: {type(e).__name__}: {e}")
            continue
        print(f"  {label}: {len(cams)} DOT cameras")
        cameras += cams

    # De-duplicate by feed URL across both files.
    seen, unique = set(), []
    for c in cameras:
        if c["stream_url"] in seen:
            continue
        seen.add(c["stream_url"])
        unique.append(c)
    print(f"  {len(unique)} total (2018 list — run the scanner to find live ones)")
    return unique
