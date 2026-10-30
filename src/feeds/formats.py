"""Shared camera-record helpers, following OpenTrafficCamMap's conventions.

OpenTrafficCamMap (https://github.com/AidanWelch/OpenTrafficCamMap, MIT)
groups cameras by country (ISO alpha-3), then administrative region, then
county, and describes each stream by its encoding and format. ACE records
carry the same information, so cameras from any country look the same.

Every camera record has:
    id, source, category,
    country      ISO 3166-1 alpha-3, e.g. "TWN", "USA"
    region       state / city / county name ("other" if unknown)
    county       district / county inside the region ("other" if unknown)
    road, direction, description, lat, lon,
    stream_url,
    url_type     how ACE opens it: stream | image | hls | page | viewer
    encoding     JPEG | H.264 | None
    format       MJPEG | IMAGE_STREAM | M3U8 | WEB_PAGE | WEB_VIEWER
    update_rate  ms between image refreshes, if known
    api_camera_id  (Singapore only) camera ID used to look up the latest image
    refresh_rate (older field, kept for compatibility)
"""

from __future__ import annotations

# url_type -> (encoding, format). OpenTrafficCamMap's format list says it is
# "not exhaustive and should be added to"; MJPEG, WEB_PAGE and WEB_VIEWER are
# our additions for feed types it doesn't list yet.
URL_TYPE_FORMATS = {
    "stream": ("JPEG", "MJPEG"),
    "image": ("JPEG", "IMAGE_STREAM"),
    "hls": ("H.264", "M3U8"),
    "page": (None, "WEB_PAGE"),
    "viewer": (None, "WEB_VIEWER"),
}

FORMAT_TO_URL_TYPE = {
    "IMAGE_STREAM": "image",
    "M3U8": "hls",
    "MJPEG": "stream",
    "WEB_PAGE": "page",
    "WEB_VIEWER": "viewer",
    # Image whose URL changes every snapshot; ask data.gov.sg for the latest.
    "UNIQUE_SINGAPORE_LTA": "image",
}

# Taiwan's OpenStreetMap admin-level-4 names (cities and counties).
_TW_CITY_FIXES = {"台北市": "臺北市", "台中市": "臺中市", "台南市": "臺南市", "台東縣": "臺東縣"}


def tw_region(name: str | None) -> str:
    """Normalise a Taiwan city/county name to its OpenStreetMap spelling."""
    if not name:
        return "other"
    name = str(name).strip()
    return _TW_CITY_FIXES.get(name, name) or "other"


def with_format(record: dict) -> dict:
    """Fill encoding/format from url_type, and make sure every field exists."""
    encoding, fmt = URL_TYPE_FORMATS.get(record.get("url_type") or "", (None, None))
    record.setdefault("encoding", encoding)
    record.setdefault("format", fmt)
    record.setdefault("update_rate", None)
    record.setdefault("refresh_rate", None)
    record["region"] = record.get("region") or "other"
    record["county"] = record.get("county") or "other"
    return record
