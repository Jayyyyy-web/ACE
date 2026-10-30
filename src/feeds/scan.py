"""Camera quality scanner.

Reads data/cameras.json, connects to each camera briefly, and records:
  - whether it's online
  - resolution (width x height)
  - frame rate, for video streams
  - how long the first frame took to arrive

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
from pathlib import Path
from urllib.parse import urljoin

import requests

from src.feeds.http import session

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


def _probe_mjpeg(resp: requests.Response, started: float) -> dict:
    """Read a multipart MJPEG stream for a few seconds and count frames."""
    buf = b""
    frames = 0
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
            now = time.monotonic()
            if first_frame_at is None:
                first_frame_at = now
                size = image_size(frame)
                deadline = now + FPS_WINDOW
        if deadline and time.monotonic() >= deadline:
            break
        if total > MAX_STREAM_BYTES or time.monotonic() - started > READ_TIMEOUT + FPS_WINDOW:
            break

    if not frames:
        return {"status": "no-frames"}
    elapsed = max(time.monotonic() - first_frame_at, 0.001)
    fps = (frames - 1) / elapsed if frames > 1 else 0.0
    return {
        "status": "online",
        "kind": "mjpeg",
        "width": size[0] if size else None,
        "height": size[1] if size else None,
        "fps": round(fps, 2),
        "first_frame_s": round(first_frame_at - started, 2),
    }


_RESOLUTION_RE = re.compile(r"RESOLUTION=(\d+)x(\d+)", re.IGNORECASE)
_FRAMERATE_RE = re.compile(r"FRAME-RATE=([\d.]+)", re.IGNORECASE)


def _probe_hls(text: str, started: float) -> dict:
    """Read an HLS playlist. Master playlists list each quality's resolution."""
    if not text.lstrip().startswith("#EXTM3U"):
        return {"status": "unsupported", "error": "not a valid HLS playlist"}
    sizes = [(int(w), int(h)) for w, h in _RESOLUTION_RE.findall(text)]
    rates = [float(r) for r in _FRAMERATE_RE.findall(text)]
    result = {"status": "online", "kind": "hls",
              "first_frame_s": round(time.monotonic() - started, 2)}
    if sizes:
        w, h = max(sizes, key=lambda s: s[0] * s[1])
        result.update(width=w, height=h)
    else:
        result["error"] = "HLS playlist lists no resolution; size unknown"
    if rates:
        result["fps"] = round(max(rates), 2)
    return result


_EMBED_RE = re.compile(
    r"""(?:src|data-src|href)\s*=\s*["']([^"']+?(?:mjpg|mjpeg|\.jpg|\.jpeg|\.png|cgi|\.m3u8|snapshot|video|stream)[^"']*)["']""",
    re.IGNORECASE,
)


def probe_url(url: str, depth: int = 0) -> dict:
    """Connect to one URL and work out what it serves."""
    started = time.monotonic()
    try:
        resp = session.get(url, stream=True, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    except requests.exceptions.SSLError as e:
        return {"status": "tls-error", "error": str(e)[:160]}
    except requests.RequestException as e:
        return {"status": "offline", "error": type(e).__name__}

    with resp:
        if resp.status_code >= 400:
            return {"status": "offline", "error": f"HTTP {resp.status_code}"}

        ctype = resp.headers.get("Content-Type", "").lower()

        if "multipart" in ctype or "mjpeg" in ctype or "mjpg" in ctype:
            return _probe_mjpeg(resp, started)

        if ctype.startswith("image/"):
            data = resp.raw.read(2_000_000, decode_content=True)
            size = image_size(data)
            return {
                "status": "online" if size else "bad-image",
                "kind": "image",
                "width": size[0] if size else None,
                "height": size[1] if size else None,
                "first_frame_s": round(time.monotonic() - started, 2),
            }

        if "mpegurl" in ctype or url.lower().split("?")[0].endswith(".m3u8"):
            text = resp.raw.read(200_000, decode_content=True).decode("utf-8", "ignore")
            return _probe_hls(text, started)

        if "html" in ctype and depth == 0:
            # A web page that wraps the camera: look for the real feed inside it.
            html = resp.raw.read(300_000, decode_content=True).decode("utf-8", "ignore")
            for match in _EMBED_RE.finditer(html):
                inner = urljoin(url, match.group(1))
                if inner == url:
                    continue
                result = probe_url(inner, depth=1)
                if result.get("status") == "online":
                    result["probed_url"] = inner
                    return result
            return {"status": "page-only", "kind": "page",
                    "error": "no playable feed found inside the page"}

        # Unknown type: sniff the first bytes.
        head = resp.raw.read(65536, decode_content=True)
        size = image_size(head)
        if size:
            return {"status": "online", "kind": "image", "width": size[0], "height": size[1],
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
    viewers = [c for c in cameras if c.get("url_type") == "viewer"]
    out = [c for c in cameras if c.get("url_type") != "viewer"]
    if viewers:
        print(f"Skipping {len(viewers)} view-only cameras (open those in a browser).")
    if args.country:
        out = [c for c in out if (c.get("country") or "TWN") in args.country]
    if args.region:
        out = [c for c in out if _in_region(c, args.region)]
    if args.source:
        out = [c for c in out if c["source"] in args.source]
    if args.category:
        out = [c for c in out if c.get("category") == args.category]
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

    ranked = sorted(online, key=lambda r: r["score"], reverse=True)[:top]
    if not ranked:
        return
    print(f"\nTop {len(ranked)} cameras:")
    print(f"  {'score':>6}  {'resolution':>10}  {'fps':>5}  {'id':<34} place")
    for r in ranked:
        res = f"{r['width']}x{r['height']}" if r["height"] else "?"
        fps = f"{r['fps']:.1f}" if r["fps"] is not None else "still"
        place = " ".join(x for x in (r.get("road"), r.get("description")) if x) or ""
        print(f"  {r['score']:>6}  {res:>10}  {fps:>5}  {r['id'][:34]:<34} {place[:40]}")
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
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 16))) as pool:
        futures = [pool.submit(probe, c) for c in chosen]
        for n, fut in enumerate(as_completed(futures), start=1):
            results.append(fut.result())
            if n % 25 == 0 or n == len(chosen):
                online = sum(r["status"] == "online" for r in results)
                print(f"  {n}/{len(chosen)} done, {online} online, {time.monotonic() - started:.0f}s")

    results.sort(key=lambda r: r["score"], reverse=True)
    total = save(results)
    print(f"Saved. {len(total):,} cameras in {OUT_JSON} (this scan plus earlier ones).")
    report(results, args.top)


if __name__ == "__main__":
    main()
