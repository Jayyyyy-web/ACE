"""Singapore traffic cameras from data.gov.sg (no account or key needed).

Source: the Land Transport Authority's traffic images, published on
data.gov.sg's real-time API:
    https://api.data.gov.sg/v1/transport/traffic-images

Since around July 2026 this free API only returns 8 cameras: the Woodlands
Causeway, the Tuas Second Link and Sentosa Gateway. The full network (~90
cameras) is only on LTA DataMall, which needs a registered account key.

These cameras are 1920x1080 still images. Every snapshot gets a new URL, so a
saved image link goes stale within minutes. The record stores the camera's ID
(api_camera_id) and the map and scanner ask the API for the newest image each
time. Format "UNIQUE_SINGAPORE_LTA" marks that, following OpenTrafficCamMap's
naming for agency-specific formats.
"""

from __future__ import annotations

from src.feeds.formats import with_format
from src.feeds.http import session

API_URL = "https://api.data.gov.sg/v1/transport/traffic-images"
FORMAT = "UNIQUE_SINGAPORE_LTA"
UPDATE_RATE_MS = 20_000  # images refresh about every 20 seconds

# Names for the cameras the open API currently serves. The API only gives IDs
# and coordinates; unknown IDs still import, just with a generic name.
CAMERA_NAMES = {
    "2701": ("Woodlands Causeway", "Woodlands", None),
    "2702": ("Woodlands Checkpoint", "Woodlands", None),
    "2704": ("Woodlands Flyover", "Woodlands", None),
    "4703": ("Tuas Second Link", "Tuas", None),
    "4712": ("After Tuas West Road", "Tuas", None),
    "4713": ("Tuas Checkpoint", "Tuas", None),
    "4798": ("Sentosa Gateway, towards Telok Blangah", "Sentosa Gateway", None),
    "4799": ("Sentosa Gateway, towards Sentosa", "Sentosa Gateway", None),
}


def _latest(timeout: int = 30) -> list[dict]:
    resp = session.get(API_URL, timeout=timeout)
    resp.raise_for_status()
    items = resp.json().get("items") or []
    return items[0].get("cameras", []) if items else []


def latest_image_url(camera_id: str) -> str | None:
    """Newest image URL for one camera, or None if it isn't in the feed."""
    for cam in _latest(timeout=15):
        if str(cam.get("camera_id")) == str(camera_id):
            return cam.get("image")
    return None


def fetch_all() -> list[dict]:
    print("Fetching Singapore LTA traffic images (data.gov.sg)...")
    try:
        raw = _latest()
    except Exception as e:  # one failing source shouldn't stop the run
        print(f"  ! skipped: {e}")
        return []

    cameras = []
    for cam in raw:
        cid = str(cam.get("camera_id") or "")
        loc = cam.get("location") or {}
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if not cid or lat is None or lon is None:
            continue
        name, area, direction = CAMERA_NAMES.get(cid, (f"Traffic camera {cid}", None, None))
        cameras.append(with_format({
            "id": f"sg-lta:{cid}",
            "source": "sg-lta",
            "category": "traffic",
            "country": "SGP",
            "region": "Singapore",
            "county": area,
            "road": None,
            "direction": direction,
            "description": name,
            "lat": float(lat),
            "lon": float(lon),
            "stream_url": cam.get("image"),  # a snapshot; see api_camera_id
            "url_type": "image",
            "encoding": "JPEG",
            "format": FORMAT,
            "update_rate": UPDATE_RATE_MS,
            "api_camera_id": cid,
        }))
    print(f"  {len(cameras)} cameras (the free API currently serves only these)")
    return cameras
