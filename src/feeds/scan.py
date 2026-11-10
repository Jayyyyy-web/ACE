"""Camera quality and live-video test.

Reads data/cameras.json, connects to each camera briefly, and records:
  - whether it's online
  - whether it's really live: new video keeps arriving (an MJPEG stream
    sends more than one different picture; an HLS playlist adds new video
    when read again a chunk later and isn't a finished recording)
  - for HLS, the chunk length and roughly how far behind real time it plays
    in the map (see hls_delay; MJPEG is real time)
  - resolution (width x height) and, for HLS, the codec: read from one
    downloaded chunk, since playlists often don't say
  - frame rate, for video streams
  - for HLS, whether the server lets other sites play it (CORS); the map
    can't play it otherwise
  - how long the first frame took to arrive

src.find uses these tests to keep only proper cameras.

Results go to data/camera_quality.json and data/camera_quality.csv, and the
best cameras are printed as a ranking. New results are merged with earlier
scans, so you can scan one country or area at a time.

Examples:
    python -m src.feeds.scan --region new-taipei     # New Taipei area only
    python -m src.feeds.scan --category traffic      # all road cameras
    python -m src.feeds.scan --source tainan --limit 50
    python -m src.feeds.scan --sample 200            # random 200 from everything
    python -m src.feeds.scan --country USA --sample 300   # 300 random US cameras
    python -m src.feeds.scan                         # every camera (slow)

Each probe takes a few seconds, but several run in parallel. The scanner only
reads a few seconds of each feed and saves no footage.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import struct
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests

from src.feeds.http import session
from src.feeds.videoinfo import chunk_info

CAMERAS_PATH = Path("data/cameras.json")
OUT_JSON = Path("data/camera_quality.json")
OUT_CSV = Path("data/camera_quality.csv")

# Rough bounding boxes (lat_min, lat_max, lon_min, lon_max).
# Taipei City sits inside New Taipei, so "new-taipei" covers both.
REGIONS = {
    "new-taipei": (24.67, 25.30, 121.28, 122.01),
    "keelung": (25.05, 25.20, 121.62, 121.82),
    "taoyuan": (24.60, 25.13, 120.97, 121.47),
    "taichung": (23.99, 24.45, 120.46, 121.45),
    "tainan": (22.88, 23.42, 120.03, 120.65),
    "kaohsiung": (22.47, 23.47, 120.17, 121.05),
}

CONNECT_TIMEOUT = 6      # seconds to connect
READ_TIMEOUT = 8         # seconds to wait for data
FPS_WINDOW = 4.0         # seconds spent counting frames on a video stream
MAX_STREAM_BYTES = 8_000_000
# The map plays HLS one chunk plus this many seconds behind the newest video
# (hls.js's default is three chunks: 30-60 s behind on 10-second chunks).
PLAYER_MARGIN_S = 2
# Servers date their chunks when the video reaches them, a few seconds after
# it was filmed (measured on Bantul's cameras against their on-screen clocks).
CAMERA_TO_SERVER_S = 3
HLS_RECHECK_MAX_S = 25   # longest wait before reading a playlist a second time
MAX_CHUNK_BYTES = 10_000_000  # one HLS chunk is downloaded to read its real picture size
# The map runs at http://localhost:8765. A browser only plays another site's
# HLS video if that site's answer allows it (CORS), so ask the way the map does.
MAP_ORIGIN = "http://localhost:8765"

SOI = b"\xff\xd8"  # JPEG start
EOI = b"\xff\xd9"  # JPEG end


# --------------------------------------------------------------------------
# Image size detection (no image library needed)
# --------------------------------------------------------------------------

def image_size(data: bytes) -> tuple[int, int] | None:
    """Return (width, height) of a JPEG, PNG or GIF from its header bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        w, h = struct.unpack("<HH", data[6:10])
        return w, h
    start = data.find(SOI)
    if start == -1:
        return None
    i = start + 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
            i += 1 if marker == 0xFF else 2
            continue
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        # Start-of-frame markers hold the dimensions (C4, C8, CC are not SOFs).
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + seg_len
    return None


# --------------------------------------------------------------------------
# Probing
# --------------------------------------------------------------------------

def _result(cam: dict, **fields) -> dict:
    base = {
        "id": cam["id"],
        "source": cam["source"],
        "category": cam.get("category"),
        "country": cam.get("country") or "TWN",
        "road": cam.get("road"),
        "description": cam.get("description"),
        "lat": cam.get("lat"),
        "lon": cam.get("lon"),
        "stream_url": cam["stream_url"],
        "probed_url": cam["stream_url"],
        "status": "offline",
        "kind": None,
        "live": None,       # True: new video kept arriving. False: frozen, a recording, or a still
        "delay_s": None,    # about how far behind real time the map plays it (MJPEG: 1)
        "segment_s": None,  # HLS: chunk length
        "codec": None,      # HLS: h264 or hevc, read from a real chunk
        "cors": None,       # HLS: False if the server won't let other sites (the map) play it
        "chunk_download_s": None,  # HLS: how long one chunk took to download
        "width": None,
        "height": None,
        "fps": None,
        "first_frame_s": None,
        "error": None,
        "score": 0.0,
    }
    base.update(fields)
    return base


def _chunks_as_they_arrive(resp: requests.Response):
    """Yield stream data the moment it arrives.

    Reading fixed-size blocks would wait until each block fills up, which
    bunches several frames together and makes the fps measurement wrong.
    """
    raw = resp.raw
    if hasattr(raw, "read1"):
        while True:
            chunk = raw.read1(65536)
            if not chunk:
                return
            yield chunk
    else:
        yield from resp.iter_content(chunk_size=1024)


def _probe_mjpeg(resp: requests.Response, started: float, min_height: int | None = None) -> dict:
    """Read a multipart MJPEG stream for a few seconds and count frames.
    With min_height, a stream whose first picture is smaller is left after
    that picture: there's no need to measure its frame rate."""
    buf = b""
    frames = 0
    pictures = set()  # a frozen camera repeats the same picture
    first_frame_at = None
    size = None
    total = 0
    deadline = None

    for chunk in _chunks_as_they_arrive(resp):
        if not chunk:
            continue
        buf += chunk
        total += len(chunk)
        while True:
            s = buf.find(SOI)
            if s == -1:
                buf = buf[-1:]
                break
            e = buf.find(EOI, s + 2)
            if e == -1:
                buf = buf[s:]
                break
            frame = buf[s:e + 2]
            buf = buf[e + 2:]
            frames += 1
            if len(pictures) < 2:
                pictures.add(hash(frame))
            now = time.monotonic()
            if first_frame_at is None:
                first_frame_at = now
                size = image_size(frame)
                deadline = now + FPS_WINDOW
                if size and min_height and size[1] < min_height:
                    return {"status": "online", "kind": "mjpeg", "width": size[0], "height": size[1],
                            "delay_s": 1.0, "first_frame_s": round(now - started, 2),
                            "error": "smaller than wanted, so not tested further"}
        if deadline and time.monotonic() >= deadline:
            break
        if total > MAX_STREAM_BYTES or time.monotonic() - started > READ_TIMEOUT + FPS_WINDOW:
            break

    if not frames:
        return {"status": "no-frames"}
    elapsed = max(time.monotonic() - first_frame_at, 0.001)
    fps = (frames - 1) / elapsed if frames > 1 else 0.0
    result = {
        "status": "online",
        "kind": "mjpeg",
        "live": True,
        "delay_s": 1.0,  # each picture is sent as soon as it's taken
        "width": size[0] if size else None,
        "height": size[1] if size else None,
        "fps": round(fps, 2),
        "first_frame_s": round(first_frame_at - started, 2),
    }
    if len(pictures) < 2:
        result.update(status="frozen", live=False,
                      error="sent only one picture" if frames == 1 else "kept sending the same picture")
    return result


_RESOLUTION_RE = re.compile(r"RESOLUTION=(\d+)x(\d+)", re.IGNORECASE)
_FRAMERATE_RE = re.compile(r"FRAME-RATE=([\d.]+)", re.IGNORECASE)
_BANDWIDTH_RE = re.compile(r"BANDWIDTH=(\d+)", re.IGNORECASE)
_TARGET_RE = re.compile(r"#EXT-X-TARGETDURATION:\s*([\d.]+)")
_SEQUENCE_RE = re.compile(r"#EXT-X-MEDIA-SEQUENCE:\s*(\d+)")
_EXTINF_RE = re.compile(r"#EXTINF:\s*([\d.]+)")
_PDT_RE = re.compile(r"#EXT-X-PROGRAM-DATE-TIME:\s*(\S+)")


def _best_variant(master: str, base_url: str) -> str | None:
    """The highest-bandwidth stream listed in a master playlist."""
    lines = [l.strip() for l in master.splitlines()]
    best, best_bw = None, -1
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue
        uri = next((l for l in lines[i + 1:] if l and not l.startswith("#")), None)
        bw = int((_BANDWIDTH_RE.search(line) or [0, 0])[1])
        if uri and bw > best_bw:
            best, best_bw = urljoin(base_url, uri), bw
    return best


_MAP_RE = re.compile(r'#EXT-X-MAP:.*?URI="([^"]+)"')


def _newest_end(text: str) -> float | None:
    """When the newest video ends (epoch seconds), if the server dates its
    chunks (EXT-X-PROGRAM-DATE-TIME). A chunk's tags come before its address,
    in any order; a dated chunk and every chunk after it add up from that
    date: many servers (Flussonic, for one) date only the first chunk."""
    start, after = None, 0.0
    duration, dated = 0.0, None
    for line in (l.strip() for l in text.splitlines()):
        if line.startswith("#EXTINF:"):
            m = _EXTINF_RE.match(line)
            duration = float(m.group(1)) if m else 0.0
        elif line.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            try:
                when = datetime.fromisoformat(line.split(":", 1)[1].strip().replace("Z", "+00:00"))
            except ValueError:
                continue
            dated = when.timestamp() if when.tzinfo is not None else None
        elif line and not line.startswith("#"):  # a chunk's address closes its tags
            if dated is not None:
                start, after = dated, 0.0
            if start is not None:
                after += duration
            duration, dated = 0.0, None
    return start + after if start is not None else None


def _media_state(text: str) -> dict:
    """What a media playlist says about its newest video."""
    target, sequence = _TARGET_RE.search(text), _SEQUENCE_RE.search(text)
    durations = _EXTINF_RE.findall(text)
    segments = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
    init = _MAP_RE.search(text)
    return {
        "segment_s": float(target.group(1)) if target else None,
        "sequence": int(sequence.group(1)) if sequence else None,
        "last": segments[-1] if segments else None,
        "last_duration": float(durations[-1]) if durations else 0.0,
        "newest_end": _newest_end(text),
        "init": init.group(1) if init else None,  # fMP4 streams: the chunk's header lives here
        "ended": "#EXT-X-ENDLIST" in text,
    }


def _cors_ok(headers) -> bool:
    allowed = (headers.get("Access-Control-Allow-Origin") or "").strip()
    return allowed == "*" or allowed == MAP_ORIGIN


def _age_of_newest(state: dict) -> float | None:
    """Seconds since the newest video ended, when the server dates its
    chunks. Many servers don't."""
    return time.time() - state["newest_end"] if state["newest_end"] is not None else None


def _get(url: str, limit: int = 500_000, timed: bool = False):
    """GET as the map's page would (with its Origin), returning the final URL,
    up to `limit` bytes of the body, and the response headers. With timed,
    also the seconds the body took to arrive (connection setup excluded: a
    player reuses its connection from chunk to chunk)."""
    resp = session.get(url, stream=True, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                       headers={"Origin": MAP_ORIGIN})
    with resp:
        resp.raise_for_status()
        t = time.monotonic()
        body = resp.raw.read(limit, decode_content=True)
        took = time.monotonic() - t
    return (resp.url, body, resp.headers, took) if timed else (resp.url, body, resp.headers)


def _get_text(url: str) -> tuple[str, str]:
    final, body, _ = _get(url)
    return final, body.decode("utf-8", "ignore")


# The start of a chunk is enough to read its picture size: HLS chunks open
# with the stream's parameters. If they aren't there, the whole chunk is read.
CHUNK_HEAD_BYTES = 150_000


def _measure_chunk(base_url: str, state: dict, min_height: int | None = None) -> dict:
    """Read the newest chunk's real picture size and codec (playlists often
    don't say, or say the wrong thing) from its first few kilobytes.

    min_height: if the picture is at least this tall (or its size can't be
    read from the start), download the whole chunk too, for the frame rate
    and download speed. None reads the start only, which keeps a big scan
    from downloading gigabytes."""
    if not state["last"]:
        return {}
    url = urljoin(base_url, state["last"])
    try:
        init = b""
        if state["init"]:
            _, init, _ = _get(urljoin(base_url, state["init"]), limit=2_000_000)
        _, head, headers = _get(url, limit=CHUNK_HEAD_BYTES)
        info = chunk_info(head, init)
        if info["height"] and (min_height is None or info["height"] < min_height):
            return {"codec": info["codec"], "width": info["width"], "height": info["height"],
                    "chunk_cors": _cors_ok(headers)}
        _, chunk, headers, took = _get(url, limit=MAX_CHUNK_BYTES, timed=True)
    except requests.RequestException as e:
        return {"chunk_error": type(e).__name__}
    info = chunk_info(chunk, init)
    out = {"codec": info["codec"], "chunk_download_s": round(took, 2), "chunk_cors": _cors_ok(headers)}
    if info["width"]:
        out.update(width=info["width"], height=info["height"])
    if info["frames"] and state["last_duration"] and len(chunk) < MAX_CHUNK_BYTES:
        out["fps"] = round(info["frames"] / state["last_duration"], 1)
    return out


def hls_delay(segment_s: float, newest_age_s: float | None = None, download_s: float | None = None) -> float:
    """About how far behind real time the map plays an HLS stream.

    The map's player sits one chunk plus PLAYER_MARGIN_S behind the newest
    video, and the newest video is itself about half a chunk old on average
    (or as old as the server says when it dates its chunks, plus the few
    seconds the camera takes to get its video to the server, which is when
    the date is stamped). A chunk that takes longer to download than to play
    makes the player fall further behind. (One chunk fetched on a fresh
    connection downloads slower than a player's steady stream does, so
    anything quicker than that is left alone.) Checked against cameras'
    on-screen clocks: right to within a few seconds on servers that keep up.
    """
    if newest_age_s is not None and 0 <= newest_age_s < 120:
        edge = newest_age_s + CAMERA_TO_SERVER_S
    else:
        edge = segment_s / 2 + 1
    slow = max(0.0, (download_s or 0.0) - segment_s) * 2
    return round(segment_s + PLAYER_MARGIN_S + edge + slow, 1)


def _probe_hls(text: str, url: str, started: float, headers=None, min_height: int | None = None) -> dict:
    """Read an HLS playlist and note how live it is.

    A master playlist lists each quality; ACE follows it to the best one's
    media playlist, which gives the chunk length and shows whether the stream
    has ended (a finished recording, not live video). One chunk is downloaded
    to read the real picture size, codec and frame rate, and every answer is
    checked for the CORS permission a browser needs to play it in the map.
    main() reads the media playlist again a chunk later (recheck_hls) to make
    sure new video is still arriving.
    """
    if not text.lstrip().startswith("#EXTM3U"):
        return {"status": "unsupported", "error": "not a valid HLS playlist"}
    sizes = [(int(w), int(h)) for w, h in _RESOLUTION_RE.findall(text)]
    rates = [float(r) for r in _FRAMERATE_RE.findall(text)]
    result = {"status": "online", "kind": "hls", "cors": _cors_ok(headers or {}),
              "first_frame_s": round(time.monotonic() - started, 2)}
    if sizes:
        w, h = max(sizes, key=lambda s: s[0] * s[1])
        result.update(width=w, height=h)
    if rates:
        result["fps"] = round(max(rates), 2)

    media_url, media = url, text
    if "#EXT-X-STREAM-INF" in text:
        variant = _best_variant(text, url)
        if not variant:
            return {**result, "status": "unsupported", "error": "master playlist lists no streams"}
        try:
            media_url, body, media_headers = _get(variant)
        except requests.RequestException as e:
            return {**result, "status": "offline", "error": f"media playlist: {type(e).__name__}"}
        media = body.decode("utf-8", "ignore")
        result["cors"] = result["cors"] and _cors_ok(media_headers)

    state = _media_state(media)
    if state["ended"]:
        return {**result, "status": "recorded", "live": False,
                "error": "a finished recording, not live video"}

    chunk = _measure_chunk(media_url, state, min_height)
    if "chunk_cors" in chunk:
        result["cors"] = result["cors"] and chunk.pop("chunk_cors")
    if chunk.get("chunk_error"):
        result["error"] = f"couldn't download a chunk ({chunk.pop('chunk_error')})"
    result.update(chunk)
    if not result.get("height"):
        result["error"] = result.get("error") or "picture size unknown"

    segment = state["segment_s"] or 6.0
    result.update(segment_s=state["segment_s"],
                  delay_s=hls_delay(segment, _age_of_newest(state), result.get("chunk_download_s")))
    result["_recheck"] = {"url": media_url, "sequence": state["sequence"], "last": state["last"],
                          "at": time.monotonic(), "wait": min(segment + 2, HLS_RECHECK_MAX_S)}
    return result


def recheck_hls(r: dict) -> dict:
    """Read an HLS stream's media playlist again: a live stream has added new
    video since the first read. Updates r in place."""
    info = r.pop("_recheck", None)
    if not info:
        return r
    wait = info["at"] + info["wait"] - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    text = None
    for attempt in (1, 2):  # a far-away server can drop one request
        try:
            _, text = _get_text(info["url"])
            break
        except Exception as e:  # one bad stream must never stop the scan
            if attempt == 2:
                r["error"] = f"second check failed ({type(e).__name__}); not confirmed live"
                return r
            time.sleep(2)
    state = _media_state(text)
    moved = (state["last"] != info["last"]
             or (state["sequence"] or 0) > (info["sequence"] or 0))
    if state["ended"]:
        r.update(status="recorded", live=False, error="the stream ended: a finished recording")
    elif moved:
        r["live"] = True
    else:
        r.update(status="frozen", live=False, error=f"no new video in {info['wait']:.0f} s")
    r["score"] = score(r)
    return r


_EMBED_RE = re.compile(
    r"""(?:src|data-src|href)\s*=\s*["']([^"']+?(?:mjpg|mjpeg|\.jpg|\.jpeg|\.png|cgi|\.m3u8|snapshot|video|stream)[^"']*)["']""",
    re.IGNORECASE,
)


def probe_url(url: str, depth: int = 0, min_height: int | None = None) -> dict:
    """Connect to one URL and work out what it serves.

    min_height (src.find sets it): stop measuring as soon as a video's picture
    turns out smaller than this; HLS video at least this sharp has a whole
    chunk downloaded for its frame rate and download speed. Without it, HLS
    picture size and codec are read from the first part of a chunk only."""
    started = time.monotonic()
    try:
        resp = session.get(url, stream=True, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                           headers={"Origin": MAP_ORIGIN})
    except requests.exceptions.SSLError as e:
        return {"status": "tls-error", "error": str(e)[:160]}
    except requests.RequestException as e:
        return {"status": "offline", "error": type(e).__name__}

    with resp:
        if resp.status_code >= 400:
            return {"status": "offline", "error": f"HTTP {resp.status_code}"}

        ctype = resp.headers.get("Content-Type", "").lower()

        if "multipart" in ctype or "mjpeg" in ctype or "mjpg" in ctype:
            return _probe_mjpeg(resp, started, min_height)

        if ctype.startswith("image/"):
            data = resp.raw.read(2_000_000, decode_content=True)
            size = image_size(data)
            return {
                "status": "online" if size else "bad-image",
                "kind": "image",
                "live": False,  # a still picture, not video
                "width": size[0] if size else None,
                "height": size[1] if size else None,
                "first_frame_s": round(time.monotonic() - started, 2),
            }

        if "mpegurl" in ctype or url.lower().split("?")[0].endswith(".m3u8"):
            text = resp.raw.read(200_000, decode_content=True).decode("utf-8", "ignore")
            return _probe_hls(text, resp.url, started, resp.headers, min_height)

        if "html" in ctype and depth == 0:
            # A web page that wraps the camera: look for the real feed inside it.
            html = resp.raw.read(300_000, decode_content=True).decode("utf-8", "ignore")
            for match in _EMBED_RE.finditer(html):
                inner = urljoin(url, match.group(1))
                if inner == url:
                    continue
                result = probe_url(inner, depth=1, min_height=min_height)
                if result.get("status") == "online":
                    result["probed_url"] = inner
                    return result
            return {"status": "page-only", "kind": "page",
                    "error": "no playable feed found inside the page"}

        # Unknown type: sniff the first bytes.
        head = resp.raw.read(65536, decode_content=True)
        size = image_size(head)
        if size:
            return {"status": "online", "kind": "image", "live": False,
                    "width": size[0], "height": size[1],
                    "first_frame_s": round(time.monotonic() - started, 2)}
        return {"status": "unsupported", "error": f"content type '{ctype or 'unknown'}'"}


def score(r: dict) -> float:
    """Higher is better. Resolution matters most; frame rate and speed help."""
    if r["status"] != "online" or not r.get("height"):
        return 0.0
    pixels = (r["width"] or 0) * r["height"]
    s = pixels / 10_000                       # 1920x1080 -> ~207, 352x240 -> ~8
    if r.get("fps"):
        s *= 1 + min(r["fps"], 15) / 15       # up to 2x for smooth video
    if r.get("first_frame_s") and r["first_frame_s"] > 5:
        s *= 0.8                              # slow to respond
    return round(s, 1)


def _current_url(cam: dict) -> str:
    """Most cameras have a fixed URL. Singapore's change every snapshot, so
    ask the API for the newest one."""
    if cam.get("format") == "UNIQUE_SINGAPORE_LTA" and cam.get("api_camera_id"):
        from src.feeds import sgp
        try:
            return sgp.latest_image_url(cam["api_camera_id"]) or cam["stream_url"]
        except Exception:
            return cam["stream_url"]
    return cam["stream_url"]


def probe(cam: dict) -> dict:
    found = probe_url(_current_url(cam))
    r = _result(cam, **found)
    r["score"] = score(r)
    return r


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _in_region(cam: dict, region: str) -> bool:
    lat_min, lat_max, lon_min, lon_max = REGIONS[region]
    return lat_min <= (cam.get("lat") or 0) <= lat_max and lon_min <= (cam.get("lon") or 0) <= lon_max


def select(cameras: list[dict], args) -> list[dict]:
    # "viewer" cameras are official web pages for people to open in a
    # browser; we don't pull video from them automatically.
    # The same goes for YouTube live streams, which ACE only ever shows through
    # YouTube's own embed player.
    view_only = ("viewer", "youtube")
    out = cameras
    if args.country:
        out = [c for c in out if (c.get("country") or "TWN") in args.country]
    if args.region:
        out = [c for c in out if _in_region(c, args.region)]
    if args.source:
        out = [c for c in out if c["source"] in args.source]
    if args.category:
        out = [c for c in out if c.get("category") == args.category]
    viewers = sum(1 for c in out if c.get("url_type") in view_only)
    if viewers:
        print(f"Skipping {viewers} view-only cameras (open those in a browser).")
        out = [c for c in out if c.get("url_type") not in view_only]
    if args.sample and len(out) > args.sample:
        out = random.sample(out, args.sample)
    if args.limit:
        out = out[: args.limit]
    return out


def save(results: list[dict]) -> list[dict]:
    """Merge new results into earlier ones, so scanning one country or region
    doesn't erase what you scanned before. Returns the full merged list."""
    merged: dict[str, dict] = {}
    if OUT_JSON.exists():
        try:
            for r in json.loads(OUT_JSON.read_text(encoding="utf-8")):
                merged[r["id"]] = r
        except (ValueError, KeyError):
            pass
    for r in results:
        merged[r["id"]] = r
    keys = list(results[0].keys())
    results = sorted(merged.values(), key=lambda r: r.get("score") or 0, reverse=True)
    for r in results:  # older rows may miss newer fields
        for k in keys:
            r.setdefault(k, None)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig opens cleanly in Excel
        fields = list(dict.fromkeys(k for r in results for k in r))
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    return results


def report(results: list[dict], top: int) -> None:
    online = [r for r in results if r["status"] == "online"]
    print(f"\nScanned {len(results)} cameras: {len(online)} online "
          f"({len(online) / max(len(results), 1):.0%})")

    statuses: dict[str, int] = {}
    for r in results:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    print("  " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items(), key=lambda x: -x[1])))

    sizes: dict[str, int] = {}
    for r in online:
        if r["height"]:
            key = f"{r['width']}x{r['height']}"
            sizes[key] = sizes.get(key, 0) + 1
    if sizes:
        print("  resolutions: " + ", ".join(f"{k} ({v})" for k, v in sorted(sizes.items(), key=lambda x: -x[1])[:8]))

    live = [r for r in results if r.get("live")]
    mjpeg = sum(1 for r in live if r["kind"] == "mjpeg")
    delays = sorted(r["delay_s"] for r in live if r["kind"] == "hls" and r.get("delay_s"))
    if live:
        line = f"  live video: {len(live)}"
        parts = []
        if mjpeg:
            parts.append(f"{mjpeg} MJPEG in real time")
        if delays:
            parts.append(f"{len(delays)} HLS about {delays[len(delays) // 2]:.0f} s behind (median; "
                         f"{sum(d <= 10 for d in delays)} within 10 s)")
        print(line + (" (" + ", ".join(parts) + ")" if parts else ""))

    # Rank live video first; fall back to anything online (e.g. still images).
    ranked = sorted(live or online, key=lambda r: r["score"], reverse=True)[:top]
    if not ranked:
        return
    print(f"\nTop {len(ranked)} cameras:")
    print(f"  {'score':>6}  {'resolution':>10}  {'fps':>5}  {'delay':>9}  {'id':<34} place")
    for r in ranked:
        res = f"{r['width']}x{r['height']}" if r["height"] else "?"
        fps = f"{r['fps']:.1f}" if r["fps"] is not None else ("still" if r["kind"] == "image" else "?")
        delay = "real time" if r["kind"] == "mjpeg" else (f"~{r['delay_s']:.0f} s" if r.get("delay_s") else "-")
        place = " ".join(x for x in (r.get("road"), r.get("description")) if x) or ""
        print(f"  {r['score']:>6}  {res:>10}  {fps:>5}  {delay:>9}  {r['id'][:34]:<34} {place[:40]}")
    print(f"\nOpen any of these in a browser via its stream_url in {OUT_CSV}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Check the quality of public cameras.")
    p.add_argument("--country", nargs="+", help="only these countries, e.g. TWN USA")
    p.add_argument("--region", choices=sorted(REGIONS), help="only cameras in this Taiwan area")
    p.add_argument("--source", nargs="+", help="only these sources, e.g. freeway tainan")
    p.add_argument("--category", choices=["traffic", "water"])
    p.add_argument("--sample", type=int, help="random sample of N cameras")
    p.add_argument("--limit", type=int, help="first N cameras only")
    p.add_argument("--workers", type=int, default=8, help="parallel probes (default 8; be polite)")
    p.add_argument("--top", type=int, default=20, help="how many to show in the ranking")
    args = p.parse_args(argv)

    if not CAMERAS_PATH.exists():
        raise SystemExit("data/cameras.json not found. Run: python -m src.feeds.cameras")
    cameras = json.loads(CAMERAS_PATH.read_text(encoding="utf-8"))
    chosen = select(cameras, args)
    if not chosen:
        raise SystemExit("No cameras match those filters.")

    print(f"Probing {len(chosen)} cameras with {args.workers} workers...")
    results: list[dict] = []
    started = time.monotonic()
    workers = max(1, min(args.workers, 16))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(probe, c) for c in chosen]
        for n, fut in enumerate(as_completed(futures), start=1):
            results.append(fut.result())
            if n % 25 == 0 or n == len(chosen):
                online = sum(r["status"] == "online" for r in results)
                print(f"  {n}/{len(chosen)} done, {online} online, {time.monotonic() - started:.0f}s")

    # Second look at HLS streams, a chunk after the first: live ones have
    # added new video. Done as a separate pass so nobody waits idle above.
    pending = [r for r in results if r.get("_recheck")]
    if pending:
        print(f"Checking that {len(pending)} HLS streams keep adding new video...")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for n, r in enumerate(pool.map(recheck_hls, pending), start=1):
                if n % 100 == 0 or n == len(pending):
                    live = sum(1 for x in pending[:n] if x.get("live"))
                    print(f"  {n}/{len(pending)} rechecked, {live} live")

    results.sort(key=lambda r: r["score"], reverse=True)
    total = save(results)
    print(f"Saved. {len(total):,} cameras in {OUT_JSON} (this scan plus earlier ones).")
    report(results, args.top)


if __name__ == "__main__":
    main()
