"""Import live video from open-webcam-atlas.

open-webcam-atlas (https://github.com/jaydenbarnescs-tech/open-webcam-atlas,
MIT, Copyright (c) 2026 Jayden Barnes) indexes openly published webcams. Most
of its live streams duplicate US DOT cameras ACE already has, so ACE takes
only what is new and live:

  - Krasnoyarsk, Russia: the city camera portal cam.krk.ru (CC BY-SA, per
    the atlas), live HLS.
  - YouTube live streams: Kyoto's official tourism cameras and public live
    streams tagged on OpenStreetMap. These play through YouTube's own embed
    player (allowed by YouTube's terms) and are view-only: ACE never
    downloads or analyses YouTube video.

The atlas list is downloaded once and cached in data/cache/ for a week.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

from src.feeds.cache import CACHE_DIR, cached_json
from src.feeds.formats import with_format
from src.feeds.http import session

URL = "https://raw.githubusercontent.com/jaydenbarnescs-tech/open-webcam-atlas/main/data/cameras.json"
_YT = re.compile(r"^https://www\.youtube(?:-nocookie)?\.com/embed/([\w-]{6,})")
ISO3 = {"JP": "JPN", "RU": "RUS", "US": "USA"}

OEMBED = "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={id}&format=json"
YT_STATUS = CACHE_DIR / "youtube-status.json"
YT_STATUS_MAX_AGE = 86400  # re-check each video at most once a day


def _video_id(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def youtube_alive(ids: list[str]) -> dict[str, bool]:
    """Ask YouTube's public oEmbed endpoint whether each video exists and may be
    embedded (HTTP 200). Dead, private or embed-disabled videos come back
    400/401/403/404. Verdicts are cached for a day."""
    try:
        cache = json.loads(YT_STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    now = time.time()
    todo = [i for i in ids if now - cache.get(i, {}).get("at", 0) > YT_STATUS_MAX_AGE]

    def check(vid: str):
        try:
            r = session.get(OEMBED.format(id=vid), timeout=15)
            return vid, r.status_code == 200, True
        except Exception:
            return vid, True, False  # network trouble: keep it, don't cache

    with ThreadPoolExecutor(max_workers=6) as pool:
        for vid, ok, sure in pool.map(check, todo):
            if sure:
                cache[vid] = {"ok": ok, "at": now}
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        YT_STATUS.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass
    return {i: cache.get(i, {}).get("ok", True) for i in ids}


def _rec(src: str, cam: dict, url: str, url_type: str, fmt: str, country: str, region: str) -> dict:
    return with_format({
        "id": f"{src}:{hashlib.sha1(url.encode()).hexdigest()[:10]}",
        "source": src,
        "category": "traffic" if cam.get("cat") == "traffic" else "webcam",
        "country": country,
        "region": region,
        "county": None,
        "road": None,
        "direction": None,
        "description": cam.get("name") or None,
        "lat": float(cam["lat"]),
        "lon": float(cam["lon"]),
        "stream_url": url,
        "url_type": url_type,
        "encoding": "H.264",
        "format": fmt,
    })


def convert(cams: list[dict]) -> list[dict]:
    out = []
    for cam in cams:
        try:
            lat, lon = float(cam.get("lat")), float(cam.get("lon"))
        except (TypeError, ValueError):
            continue
        if abs(lat) < 0.01 and abs(lon) < 0.01:
            continue
        cc = (cam.get("country") or "").upper()

        stream = (cam.get("stream") or "").strip()
        if cam.get("src") == "cam.krk.ru" and stream.startswith("https://"):
            out.append(_rec("owa-krasnoyarsk", cam, stream, "hls", "M3U8", "RUS", "Krasnoyarsk"))
            continue

        m = _YT.match((cam.get("embed") or "").strip())
        if m:
            vid = m.group(1)
            # A clean privacy-enhanced embed URL; the viewer adds autoplay/mute.
            url = f"https://www.youtube-nocookie.com/embed/{vid}"
            kyoto = cam.get("src") == "Kyoto Official Tourism"
            src = "owa-kyoto-tourism" if kyoto else "owa-youtube-osm"
            out.append(_rec(src, cam, url, "youtube", "YOUTUBE_EMBED",
                            ISO3.get(cc, cc or "other"), "Kyoto" if kyoto else "other"))
    return out


def fetch_all() -> list[dict]:
    print("Fetching open-webcam-atlas live video (Krasnoyarsk, YouTube live)...")
    try:
        cams = cached_json(URL, "open-webcam-atlas.json")
    except Exception as e:
        print(f"  ! skipped: {type(e).__name__}: {e}")
        return []
    out = convert(cams if isinstance(cams, list) else [])
    seen, unique = set(), []
    for c in out:
        if c["stream_url"] not in seen:
            seen.add(c["stream_url"])
            unique.append(c)
    yt_ids = [_video_id(c["stream_url"]) for c in unique if c["url_type"] == "youtube"]
    alive = youtube_alive(yt_ids)
    dropped = sum(1 for v in alive.values() if not v)
    unique = [c for c in unique
              if c["url_type"] != "youtube" or alive.get(_video_id(c["stream_url"]), True)]
    yt = sum(1 for c in unique if c["url_type"] == "youtube")
    print(f"  {len(unique) - yt} Krasnoyarsk streams, {yt} YouTube live embeds"
          + (f" (dropped {dropped} unavailable videos)" if dropped else ""))
    return unique
