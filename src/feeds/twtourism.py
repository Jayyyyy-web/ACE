"""Taiwan Tourism Administration live cameras (交通部觀光署 即時影像).

The Tourism Administration's official site lists the live cameras run by
Taiwan's national scenic area offices and city and county governments:
https://www.taiwan.net.tw/m1.aspx?sNo=0042331 — Taipei 101 from Xiangshan,
Dadaocheng Wharf, Jiufen, Yehliu, Gaomei Wetlands, Sun Moon Lake (all seven
of its cameras), Alishan, Penghu, Green Island, Kinmen, Matsu and more. Most
stream in HD.

Every one is a YouTube live stream, so ACE plays them only through YouTube's
own embed player (allowed by YouTube's terms) and never downloads, records or
analyses them: they are for watching, not for the AI. From the site ACE takes
only each camera's name, county, provider, location and video ID, and links
back to its official page. Videos YouTube reports as unavailable or not
embeddable are dropped.

The list page is cached for a day. Each camera's own page (which has its
location and the video it currently embeds) is cached for a week, so after
the first run a refresh is usually a single request.
"""

from __future__ import annotations

import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

from src.feeds.cache import CACHE_DIR, cached_text
from src.feeds.formats import tw_region, with_format
from src.feeds.http import session
from src.feeds.opendata import LAT_RANGE, LON_RANGE
from src.feeds.owa import youtube_alive

LIST_URL = "https://www.taiwan.net.tw/m1.aspx?sNo=0042331"
CAMERA_URL = "https://www.taiwan.net.tw/m1.aspx?sNo=0042331&uid={uid}"
PUBLISHER = "交通部觀光署 Tourism Administration"
DETAILS_PATH = CACHE_DIR / "twtourism-cameras.json"
DETAILS_MAX_AGE = 7 * 86400
EMBED = "https://www.youtube-nocookie.com/embed/"

# The list page: one <li><div class="media-item"> per camera.
_ITEM = re.compile(r'<li>\s*<div class="media-item">')
_UID = re.compile(r"m1\.aspx\?sNo=0042331&(?:amp;)?uid=(\d+)")
_TITLE = re.compile(r'class="media-title">\s*([^<]+?)\s*<')
_COUNTY = re.compile(r"<small>\s*([^<]+?)\s*</small>")
_PROVIDER = re.compile(r"即時影像提供來源[：:]\s*([^\s<]+)")
_THUMB_ID = re.compile(r"(?:img\.youtube\.com|i\.ytimg\.com)/vi/([\w-]{11})/")
# A camera's own page: the YouTube player it embeds, and a Google map at q=lat,lon.
_EMBED_VIDEO = re.compile(
    r"""<iframe[^>]+src=["']https://www\.youtube(?:-nocookie)?\.com/embed/(?!live_stream)([\w-]{11})(?![\w-])""")
_EMBED_CHANNEL = re.compile(
    r"""<iframe[^>]+src=["']https://www\.youtube(?:-nocookie)?\.com/embed/live_stream\?channel=(UC[\w-]{22})""")
_MAP_AT = re.compile(r"google\.com/maps/embed[^\"']*?[?&](?:amp;)?q=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)")


def parse_list(page: str) -> list[dict]:
    cameras, seen = [], set()
    for chunk in _ITEM.split(page)[1:]:
        uid = _UID.search(chunk)
        if not uid or uid.group(1) in seen:
            continue
        seen.add(uid.group(1))
        title, county = _TITLE.search(chunk), _COUNTY.search(chunk)
        provider, thumb = _PROVIDER.search(chunk), _THUMB_ID.search(chunk)
        cameras.append({
            "uid": uid.group(1),
            "title": html.unescape(title.group(1)) if title else None,
            "county": html.unescape(county.group(1)) if county else None,
            "provider": html.unescape(provider.group(1)) if provider else None,
            "thumb_video": thumb.group(1) if thumb else None,
        })
    return cameras


def parse_camera_page(page: str) -> dict:
    video, channel, at = _EMBED_VIDEO.search(page), _EMBED_CHANNEL.search(page), _MAP_AT.search(page)
    return {
        "video": video.group(1) if video else None,
        "channel": channel.group(1) if channel else None,
        "lat": float(at.group(1)) if at else None,
        "lon": float(at.group(2)) if at else None,
    }


def _check_list(page: str) -> None:
    if not parse_list(page):
        raise ValueError("no cameras found on the list page (has the site changed?)")


def _camera_pages(uids: list[str]) -> dict:
    """Location and current video for each camera, from its own page."""
    try:
        cache = json.loads(DETAILS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    now = time.time()
    todo = [u for u in uids if now - cache.get(u, {}).get("at", 0) > DETAILS_MAX_AGE]

    def read(uid: str):
        try:
            resp = session.get(CAMERA_URL.format(uid=uid), timeout=30)
            resp.raise_for_status()
            return uid, parse_camera_page(resp.content.decode("utf-8", errors="replace"))
        except Exception:
            return uid, None  # keep any earlier answer

    if todo:
        print(f"  reading {len(todo)} camera pages for locations...")
        with ThreadPoolExecutor(max_workers=4) as pool:
            for uid, info in pool.map(read, todo):
                if info:
                    cache[uid] = {**info, "at": now}
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            DETAILS_PATH.write_text(json.dumps(cache), encoding="utf-8")
        except OSError:
            pass
    return cache


def _in_taiwan(lat: float, lon: float) -> bool:
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]


def fetch_all() -> list[dict]:
    print("Fetching Tourism Administration live cameras (Taiwan, YouTube)...")
    try:
        page = cached_text(LIST_URL, "twtourism-list.html", max_age_days=1, check=_check_list)
    except Exception as e:
        print(f"  ! skipped: {type(e).__name__}: {e}")
        return []
    listed = parse_list(page)
    pages = _camera_pages([c["uid"] for c in listed])

    cameras = []
    for item in listed:
        info = pages.get(item["uid"]) or {}
        lat, lon = info.get("lat"), info.get("lon")
        if lat is None or lon is None or not _in_taiwan(lat, lon):
            continue
        # The camera page's player is what the site actually plays; the list
        # thumbnail can lag behind when a stream is restarted.
        if info.get("channel"):
            url = f"{EMBED}live_stream?channel={info['channel']}"
        elif info.get("video") or item["thumb_video"]:
            url = EMBED + (info.get("video") or item["thumb_video"])
        else:
            continue
        cameras.append(with_format({
            "id": f"tw-tourism:{item['uid']}",
            "source": "tw-tourism",
            "category": "webcam",
            "country": "TWN",
            "region": tw_region(item["county"]),
            "county": None,
            "road": None,
            "direction": None,
            "description": item["title"],
            "lat": lat,
            "lon": lon,
            "stream_url": url,
            "url_type": "youtube",
            "encoding": "H.264",
            "format": "YOUTUBE_EMBED",
            "publisher": item["provider"] or PUBLISHER,
            "page_url": CAMERA_URL.format(uid=item["uid"]),
        }))

    # Drop videos YouTube says are gone or can't be embedded. (Channel embeds
    # always show the channel's current stream, so there's no video to check.)
    videos = [c["stream_url"].removeprefix(EMBED) for c in cameras if "live_stream?" not in c["stream_url"]]
    alive = youtube_alive(videos)
    kept = [c for c in cameras if alive.get(c["stream_url"].removeprefix(EMBED), True)]
    dropped = len(cameras) - len(kept)
    print(f"  {len(kept)} official live streams"
          + (f" (dropped {dropped} unavailable videos)" if dropped else "")
          + (f"; {len(listed) - len(cameras)} listed without a location or video" if len(listed) > len(cameras) else ""))
    return kept
