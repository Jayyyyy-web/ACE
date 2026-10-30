"""Import live-video US DOT cameras from Ora.

Ora (https://github.com/warner-wvez/Ora, PolyForm Noncommercial 1.0.0,
Copyright (c) 2026 Warner Varnado) maps US state DOT traffic cameras and
records which ones publish a live HLS stream. Its states/index.json marks,
per state, whether that video really plays from an ordinary web page.

ACE imports ONLY live video, and only from states where the agency serves the
stream openly:
  - the state is flagged "video": true in Ora's index, and
  - it needs no relay ("relay") and no signed access token ("sign"). Those
    states lock their streams to their own sites; ACE doesn't work around that.
Cameras Ora itself marks offline or frozen are skipped. Snapshot-only cameras
are skipped too (ACE is live-video only; OpenTrafficCamMap covers stills).

Ora's data is fetched at run time, not copied into this repo. Its licence
allows personal, non-commercial use; see THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import hashlib
import re

from src.feeds.formats import with_format
from src.feeds.http import session

BASE = "https://raw.githubusercontent.com/warner-wvez/Ora/main/"
_BLOCKING_FLAGS = ("relay", "sign", "imgproxy")
_COMPASS = {"north": "N", "south": "S", "east": "E", "west": "W",
            "northbound": "N", "southbound": "S", "eastbound": "E", "westbound": "W"}


def _get_json(path: str):
    resp = session.get(BASE + path, timeout=60)
    resp.raise_for_status()
    return resp.json()


def open_video_states(index: dict) -> dict:
    """States whose live video plays openly, per Ora's own index."""
    return {code: cfg for code, cfg in index.items()
            if cfg.get("video") and not any(cfg.get(f) for f in _BLOCKING_FLAGS)}


def _looks_like_still(url: str) -> bool:
    low = url.lower().split("?")[0]
    return low.endswith((".jpg", ".jpeg", ".png", ".gif")) or "snapshot" in url.lower()


def _direction(label: str) -> str | None:
    word = (label or "").strip().lower().split(" ")[0] if label else ""
    return _COMPASS.get(word) or (label.strip().upper() if label and len(label.strip()) <= 2 else None)


def convert_state(code: str, cfg: dict, data: dict) -> list[dict]:
    cameras = []
    src = f"ora-{code.lower()}"
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        for d in props.get("directions", []) or []:
            url = (d.get("video") or "").strip()
            if not url.startswith("http"):
                continue  # no live stream for this view
            if d.get("status") in ("offline", "frozen"):
                continue
            if _looks_like_still(url):
                continue  # a snapshot, not live video
            if abs(lat) < 0.01 and abs(lon) < 0.01:
                continue  # placeholder (0, 0) location
            if 60 < lon < 180:
                lon = -lon  # a US longitude with its minus sign missing
            label = (d.get("label") or "").strip()
            name = props.get("name") or ""
            if name.strip().upper() in ("", "N/A", "NA", "NONE"):
                name, label = label or props.get("roadway") or code, ""
            cameras.append(with_format({
                "id": f"{src}:{hashlib.sha1(url.encode()).hexdigest()[:10]}",
                "source": src,
                "category": "traffic",
                "country": "USA",
                "region": cfg.get("name") or code,
                "county": props.get("county") or None,
                "road": props.get("roadway") or None,
                "direction": _direction(label),
                "description": f"{name} ({label})" if label and label.lower() not in name.lower() else name,
                "lat": float(lat),
                "lon": float(lon),
                "stream_url": url,
                # Ora plays every video link with hls.js; some (e.g. Missouri's
                # CameraStream API) are endpoints that hand back an HLS stream.
                "url_type": "hls",
                "encoding": "H.264",
                "format": "M3U8",
            }))
    return cameras


def fetch_all() -> list[dict]:
    print("Fetching Ora live-video DOT cameras (US)...")
    try:
        index = _get_json("states/index.json")
    except Exception as e:
        print(f"  ! skipped: {type(e).__name__}: {e}")
        return []

    states = open_video_states(index)
    locked = sorted(c for c, v in index.items() if v.get("video") and c not in states)
    cameras: list[dict] = []
    for code, cfg in sorted(states.items()):
        try:
            cams = convert_state(code, cfg, _get_json(cfg["file"]))
        except Exception as e:  # one state failing shouldn't stop the run
            print(f"  ! {code} skipped: {type(e).__name__}: {e}")
            continue
        cameras += cams

    seen, unique = set(), []
    for c in cameras:
        if c["stream_url"] not in seen:
            seen.add(c["stream_url"])
            unique.append(c)
    print(f"  {len(unique)} live streams from {len(states)} states"
          + (f" (skipped locked states: {', '.join(locked)})" if locked else ""))
    return unique
