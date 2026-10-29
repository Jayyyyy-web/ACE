"""Fetch public camera lists from data.gov.tw — no account, no API key.

Each source is a dataset on Taiwan's government open-data portal, published
under the Open Government Data License v1. Rather than hardcoding download
links (cities move their files around), we ask the data.gov.tw metadata API
for each dataset's current download URL every time we run.

Categories:
  traffic  road cameras (freeway + cities that publish stream URLs)
  water    flood, river and debris-flow cameras (useful for typhoon mode)

Not included on purpose:
  New Taipei City's cameras are included as "view-only": their dataset has
  locations but no stream links, so each one links to the city's official
  viewer page (url_type "viewer"), and nothing pulls their video automatically.

  Taipei City's own road cameras (dataset 121253) — the dataset has locations
  only, and using Taipei's live traffic images requires an application to
  the city. Stick to sources that publish stream URLs openly.
"""

from __future__ import annotations

import csv
import io
import json
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

from src.feeds.formats import tw_region, with_format
from src.feeds.http import session as _session

METADATA_URL = "https://data.gov.tw/api/v2/rest/dataset/{nid}"

# Rough bounding box for Taiwan, Penghu, Kinmen and Matsu.
LAT_RANGE = (21.5, 26.5)
LON_RANGE = (118.0, 122.5)


@dataclass(frozen=True)
class Source:
    key: str          # short name used in camera IDs, e.g. "keelung"
    nid: int          # data.gov.tw dataset ID
    category: str     # "traffic" or "water"
    label: str        # human-readable description
    prefer: str = ""  # preferred file format when a dataset offers several
    # For "view-only" sources: the dataset has no stream links, so we link to
    # the agency's own public viewer page for each camera instead. The AI and
    # the scanner skip these; they're for opening in a browser.
    viewer_url: str = ""     # e.g. "https://.../ShowFrame4CCTV/{id}"
    viewer_id_field: str = ""
    url_type: str = ""       # force a link type when the URL is misleading
    region: str = ""         # city/county when the whole source is in one place


SOURCES = [
    # Road traffic
    Source("freeway", 37665, "traffic", "Freeway Bureau (national freeways)", "XML"),
    Source("keelung", 59458, "traffic", "Keelung City", region="基隆市"),
    Source("chiayi-county", 122133, "traffic", "Chiayi County", region="嘉義縣"),
    Source("chiayi-city", 173813, "traffic", "Chiayi City", region="嘉義市"),
    Source("tainan", 166140, "traffic", "Tainan City", region="臺南市"),
    Source(
        "new-taipei", 158108, "traffic", "New Taipei City (view-only, official viewer)",
        viewer_url="https://atis.ntpc.gov.tw/ATIS/ShowFrame4CCTV/{id}",
        viewer_id_field="areacode",
        region="新北市",
    ),
    Source("taipei-mrt-works-1", 138749, "traffic", "Taipei MRT construction sites (Wanda line, 2nd office)"),
    Source("taipei-mrt-works-2", 138750, "traffic", "Taipei MRT construction sites (Xinyi east extension)"),
    Source("taipei-mrt-works-3", 145692, "traffic", "Taipei MRT construction sites (Wanda line, 1st office)"),
    # Water / disaster
    Source("wra-flood", 36687, "water", "Water Resources Agency flood-prevention cameras", "JSON"),
    Source("wra-river", 41567, "water", "Water Resources Agency river cameras", "JSON"),
    # Links look like images (ShowCCDImg) but are HTML pages wrapping the image.
    Source("debris-flow", 9327, "water", "Agriculture ministry debris-flow monitoring cameras", "JSON",
           url_type="page"),
]

# Every source names its fields differently. These lists say which field to
# look for, in order of preference. Matching ignores case.
FIELD_CANDIDATES = {
    "id": ["CCTVID", "cameraid", "ccdidentifier"],
    "url": ["VideoStreamURL", "VideoImageURL", "imageurl", "url", "影像連結網址", "來源網址"],
    "lat": ["PositionLat", "latitude_4326", "緯度", "wgsy", "lat", "latitude"],
    "lon": ["PositionLon", "longitude_4326", "經度", "wgsx", "lon", "lng", "longitude"],
    "road": ["RoadName", "rivername", "basinname"],
    "direction": ["RoadDirection"],
    "region": ["縣市", "countiesandcitieswherethemonitoringpointsarelocated"],
    "county": ["行政區", "district", "administrativedistrictwherethemonitoringpointislocated"],
    "description": [
        "SurveillanceDescription", "Location", "cameraname", "stationname",
        "攝影機名稱", "鏡頭位置", "架設或拍攝地點", "address",
    ],
}


class OpenDataError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Downloading
# --------------------------------------------------------------------------

def _resource_url(source: Source) -> tuple[str, str, str]:
    """Ask data.gov.tw for a dataset's current download URL.

    Returns (url, format, declared_encoding).
    """
    resp = _session.get(METADATA_URL.format(nid=source.nid), timeout=30)
    resp.raise_for_status()
    meta = resp.json()
    if not meta.get("success"):
        raise OpenDataError(f"data.gov.tw has no dataset {source.nid}")

    dists = [d for d in meta["result"].get("distribution", []) if d.get("resourceDownloadUrl")]
    if not dists:
        raise OpenDataError("dataset lists no download link")

    preferred = [d for d in dists if d.get("resourceFormat", "").upper() == source.prefer.upper()]
    dist = (preferred or dists)[0]
    return (
        dist["resourceDownloadUrl"],
        dist.get("resourceFormat", "").upper(),
        dist.get("resourceCharacterEncoding", ""),
    )


def _download(url: str) -> bytes:
    for attempt in range(1, 4):
        try:
            resp = _session.get(url, timeout=45)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as e:
            if attempt == 3:
                raise OpenDataError(f"download failed: {e}") from e
            time.sleep(2 * attempt)
    raise AssertionError("unreachable")


# --------------------------------------------------------------------------
# Parsing — turn CSV / JSON / XML into a list of flat dicts
# --------------------------------------------------------------------------

def _decode(raw: bytes, declared: str) -> str:
    encodings = ["utf-8-sig"]
    if "BIG5" in declared.upper():
        encodings.insert(0, "big5")
    encodings += ["big5", "cp950"]
    for enc in encodings:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def _parse_json(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Find the first list of records anywhere one level down (e.g. "CCTVs").
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
            if isinstance(value, dict):
                for inner in value.values():
                    if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                        return inner
    return []


def _local(tag: str) -> str:
    """Strip an XML namespace: '{http://...}CCTV' -> 'CCTV'."""
    return tag.rsplit("}", 1)[-1]


def _parse_xml(text: str) -> list[dict]:
    root = ET.fromstring(text.encode("utf-8"))
    records = []
    # A record is any element whose direct children are simple fields and
    # include something that looks like a coordinate.
    for el in root.iter():
        children = list(el)
        if not children:
            continue
        fields = {_local(c.tag): (c.text or "").strip() for c in children if len(c) == 0}
        names = {k.lower() for k in fields}
        if names & {"positionlat", "positionlon", "latitude", "longitude", "lat", "lon"}:
            records.append(fields)
    return records


def _parse(raw: bytes, fmt: str, declared_encoding: str) -> list[dict]:
    text = _decode(raw, declared_encoding).lstrip("﻿")
    stripped = text.lstrip()
    # Trust the content over the declared format; portals sometimes mislabel.
    if stripped.startswith("<"):
        return _parse_xml(text)
    if stripped.startswith(("[", "{")):
        return _parse_json(text)
    return _parse_csv(text)


# --------------------------------------------------------------------------
# Normalising into our camera format
# --------------------------------------------------------------------------

def _pick(record: dict, field: str):
    lowered = {str(k).lower(): v for k, v in record.items()}
    for name in FIELD_CANDIDATES[field]:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _in_taiwan(lat: float, lon: float) -> bool:
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]


def _url_type(url: str) -> str:
    """Guess what kind of link this is, so later code knows how to open it."""
    low = url.lower()
    path = low.split("?")[0]
    if any(s in low for s in ("image", "img", ".jpg", ".jpeg", ".png", "snapshot")):
        return "image"     # a still image that refreshes
    if path.endswith((".html", ".htm", ".asp", ".aspx", ".php")):
        return "page"      # a web page that embeds the camera, not a raw feed
    return "stream"        # a video / MJPEG stream


def _normalise(record: dict, source: Source, index: int) -> dict | None:
    viewer_id = None
    if source.viewer_url:
        lowered = {str(k).lower(): v for k, v in record.items()}
        viewer_id = str(lowered.get(source.viewer_id_field.lower()) or "").strip()
        url = source.viewer_url.format(id=viewer_id) if viewer_id else None
    else:
        url = _pick(record, "url")
    lat = _to_float(_pick(record, "lat"))
    lon = _to_float(_pick(record, "lon"))
    if not url or lat is None or lon is None:
        return None
    # Some datasets swap their x/y columns; fix it if the numbers say so.
    if not _in_taiwan(lat, lon) and _in_taiwan(lon, lat):
        lat, lon = lon, lat
    if not _in_taiwan(lat, lon):
        return None

    raw_id = viewer_id or _pick(record, "id") or index
    url = str(url).strip()
    description = _pick(record, "description")
    district = record.get("district") or record.get("行政區")
    if district and description and district not in description:
        description = f"{district} {description}"
    return with_format({
        "id": f"{source.key}:{raw_id}",
        "source": source.key,
        "category": source.category,
        "country": "TWN",
        "region": tw_region(source.region or _pick(record, "region")),
        "county": _pick(record, "county"),
        "road": _pick(record, "road"),
        "direction": _pick(record, "direction"),
        "description": description,
        "lat": lat,
        "lon": lon,
        "stream_url": url,
        "url_type": "viewer" if source.viewer_url else (source.url_type or _url_type(url)),
        "refresh_rate": None,
    })


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def fetch_source(source: Source) -> list[dict]:
    url, fmt, encoding = _resource_url(source)
    records = _parse(_download(url), fmt, encoding)
    cameras = [_normalise(r, source, i) for i, r in enumerate(records, start=1)]
    cameras = [c for c in cameras if c]

    # Drop exact duplicate feeds, and make IDs unique when a source reuses
    # them (the river dataset numbers cameras 1, 2, 3... per station).
    unique: dict[str, dict] = {}
    seen_urls: set[str] = set()
    for cam in cameras:
        if cam["stream_url"] in seen_urls:
            continue
        seen_urls.add(cam["stream_url"])
        base, n = cam["id"], 2
        while cam["id"] in unique:
            cam["id"] = f"{base}-{n}"
            n += 1
        unique[cam["id"]] = cam
    return list(unique.values())


def fetch_all(categories: set[str] | None = None) -> list[dict]:
    all_cameras: list[dict] = []
    for source in SOURCES:
        if categories and source.category not in categories:
            continue
        print(f"Fetching {source.label} ({source.key})...")
        try:
            cameras = fetch_source(source)
        except (OpenDataError, requests.RequestException, ET.ParseError, ValueError) as e:
            print(f"  ! skipped: {e}")
            continue
        print(f"  {len(cameras)} cameras")
        all_cameras.extend(cameras)
        time.sleep(0.5)
    return all_cameras
