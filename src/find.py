"""Find proper cameras: live video that's sharp, smooth, close to real time,
and plays in the map. Every camera is tested before it's kept.

    python -m src.find          # find and test (about 10-20 minutes the first time)
    python -m src.map           # then see them on the map

The bar (change it with the options shown):
  live         new pictures keep arriving: nothing frozen, still or pre-recorded
  sharp        1280x720 or better                        --min-height 1080 (or 480)
  smooth       at least 2 frames a second                --min-fps 0 to allow slideshows
  near live    no more than 15 seconds behind real time  --max-delay 25
  playable     the camera's server lets other sites (the map) play its video,
               in H.264, which every browser plays

Only cameras that pass go to data/proper_cameras.json, which the map shows.
data/find_report.csv (opens in Excel) lists every camera tested and why any
failed. No video is saved.

The candidates are official public cameras that ACE's survey found sharp and
live (see GROUPS below and the README). Results depend on your connection:
some servers only answer some countries, and a slow link lowers MJPEG frame
rates and makes HLS fall behind. Run it again any time; cameras found too
small are skipped for a week so later runs are quicker (--retest to recheck).

    python -m src.find --group taiwan               # one group
    python -m src.find --list                       # the groups and their sources
    python -m src.find --group us --max-delay 30    # US DOTs (off by default)
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from src.feeds import scan
from src.feeds.cache import CACHE_DIR

OUT_PATH = Path("data/proper_cameras.json")
REPORT_PATH = Path("data/find_report.csv")
HISTORY_PATH = CACHE_DIR / "find-history.json"
SMALL_SKIP_DAYS = 7  # a camera's picture size rarely changes
# A server that has refused or ignored this many cameras, and answered none,
# is skipped for the rest of the run: some servers only answer some
# countries, and waiting on each of their cameras takes ages.
HOST_GIVE_UP = 6
_REFUSALS = ("ConnectionError", "ConnectTimeout", "ReadTimeout", "SSLError", "ProxyError", "HTTP 403")


class _Servers:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.refused: Counter = Counter()
        self.answered: set[str] = set()

    def given_up(self, host: str) -> bool:
        with self.lock:
            return host not in self.answered and self.refused[host] >= HOST_GIVE_UP

    def note(self, host: str, r: dict) -> None:
        refused = r.get("status") == "tls-error" or (
            r.get("status") == "offline" and any(e in (r.get("error") or "") for e in _REFUSALS))
        with self.lock:
            if refused:
                self.refused[host] += 1
            else:
                self.answered.add(host)

    def skipped(self) -> list[str]:
        return sorted(h for h, n in self.refused.items() if n >= HOST_GIVE_UP and h not in self.answered)


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    sources: tuple[str, ...]  # camera "source" names; shell-style wildcards allowed
    default: bool
    note: str


GROUPS = [
    Group("taiwan", "Taiwan city cameras", ("taichung", "keelung", "tainan", "chiayi-city", "chiayi-county"), True,
          "MJPEG, real time. Taichung has the sharpest (about 60 at 720p+, 13 at 1080p)."),
    Group("indonesia", "Indonesian city and regency cameras",
          ("les-atcs-pekanbaru", "les-cctv-magelang", "les-atcs-cianjur", "les-atcs-palembang", "les-cctv-cirebon",
           "les-cctv-wonosobo", "les-cctv-salatiga", "les-cctv-kebumen", "les-cctv-padang", "les-atcs-denpasar",
           "les-atcs-bandung", "les-cctv-jogjakota", "les-atcs-tasikmalaya",
           "argus-bantul", "argus-jogjakarta", "argus-tasikmalaya", "argus-bandung-pelindung",
           "argus-tangerang", "argus-asahan", "argus-bpjt"), True,
          "Bantul: 1080p, 25 fps, about 8 s behind. Pekanbaru (720p, 5 s chunks) and Magelang (2 s chunks) "
          "are near live too (about 8-13 s). Yogyakarta City is HD but 20-35 s behind."),
    Group("norway", "Norwegian road cameras (Statens vegvesen)", ("les-vegvesen_video",), True,
          "Open licence (NLOD). Many 720p, but 12-second chunks: about 20 s behind, so --max-delay 25."),
    Group("thailand", "Thai highway cameras (Department of Highways)", ("les-trafficvision",), True,
          "Some 720p and 1080p. Their server refuses some countries."),
    Group("korea", "Korean city traffic centres",
          ("argus-sejong", "argus-ansan", "argus-topis-seoul", "argus-busan", "argus-ulsan", "argus-daegu",
           "argus-pohang", "argus-changwon", "argus-gwangju", "argus-chungju"), True,
          "Sejong: 1080p in 3-second chunks. Most others are 640x480 in 10-second chunks."),
    Group("krasnoyarsk", "Krasnoyarsk city cameras (Orion Telecom)", ("owa-krasnoyarsk",), True,
          "1080p, but 15-17 s chunks put it about 30 s behind: add --max-delay 40 to keep it. "
          "Their server refuses some countries."),
    Group("poland", "Gdańsk, Gdynia and Sopot (TASK)", ("argus-task-gdansk",), True,
          "City and seaside views, 1080p, about 12 s behind."),
    Group("istanbul", "Istanbul municipality", ("argus-istanbul-ibb",), True,
          "Their server refuses some countries."),
    Group("us", "US state transport departments",
          ("les-caltrans", "les-seattle_sdot", "les-mdsha", "les-mndot", "les-ladotd_511", "les-deldot",
           "les-goakamai_hdot", "les-iowa_dot", "les-vdot",
           "ora-*", "us-*", "argus-virginia", "argus-arlingtonva", "argus-njta", "argus-pgctrip", "argus-msdot",
           "argus-oktraffic", "argus-wv511", "argus-castlerock", "argus-arcgis_cams", "argus-ny511",
           "argus-cotrip", "argus-scdot", "argus-mdchart", "argus-caltrans", "argus-opentrafficcam"), False,
          "About 13,000 cameras. Hundreds are HD (Seattle, Caltrans, Maryland, Minnesota, Hawaii) but "
          "sent in 10-15 second chunks: about 18-25 s behind, so --max-delay 30. Slow to test."),
    Group("other", "Low-resolution official cameras",
          ("freeway", "thb", "argus-twipcam", "argus-taiwan-freeway", "argus-kaiho", "argus-dsat",
           "argus-bondowoso"), False,
          "Taiwan freeways and provincial highways (352x240), Japan Coast Guard, Macau (352x288)."),
]
GROUP_BY_KEY = {g.key: g for g in GROUPS}


@dataclass
class Bar:
    min_height: int = 720
    min_fps: float = 2.0
    max_delay: float = 15.0


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------

def _wanted(source: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(source, p) for p in patterns)


def gather(patterns: list[str]) -> list[dict]:
    """Fetch the camera lists the chosen groups need (cached on disk).

    Where two lists hold the same stream, the first one fetched wins, so the
    licence-reviewed Live-Environment-Streams list goes before Argus and Ora."""
    from src.feeds import argus, les, opendata, ora, otcm, owa
    from src.feeds.cache import cached_json

    cams: list[dict] = []
    if any(p.startswith("les-") for p in patterns):
        cams += [c for c in les.fetch_all() if _wanted(c["source"], patterns)]
    for source in opendata.SOURCES:
        if _wanted(source.key, patterns):
            print(f"Fetching {source.label}...")
            try:
                found = opendata.fetch_source(source)
            except Exception as e:  # one bad source must never stop the run
                print(f"  ! skipped: {type(e).__name__}: {e}")
                continue
            print(f"  {len(found)} cameras")
            cams += found
    if any(p.startswith("argus-") for p in patterns):
        cams += [c for c in argus.fetch_all() if _wanted(c["source"], patterns)]
    if _wanted("owa-krasnoyarsk", patterns):
        print("Fetching Krasnoyarsk cameras (open-webcam-atlas)...")
        try:
            atlas = cached_json(owa.URL, "open-webcam-atlas.json")
            found = [c for c in owa.convert(atlas if isinstance(atlas, list) else [])
                     if c["source"] == "owa-krasnoyarsk"]
            print(f"  {len(found)} cameras")
            cams += found
        except Exception as e:
            print(f"  ! skipped: {type(e).__name__}: {e}")
    if any(p.startswith("ora-") for p in patterns):
        cams += [c for c in ora.fetch_all() if _wanted(c["source"], patterns)]
    if any(p.startswith("us-") for p in patterns):
        cams += [c for c in otcm.fetch_all() if _wanted(c["source"], patterns)]

    unique, seen = {}, set()
    for c in cams:
        url = c.get("stream_url")
        if c.get("url_type") in ("youtube", "viewer", "page") or not url:
            continue
        key = _same_stream(url)
        if key in seen or c["id"] in unique:
            continue
        seen.add(key)
        unique[c["id"]] = c
    return list(unique.values())


def _same_stream(url: str) -> str:
    """A form of a stream address that two lists writing it differently
    (host case, default port, http/https) still agree on."""
    p = urlparse(url.strip())
    host = (p.hostname or "").lower()
    port = f":{p.port}" if p.port and p.port not in (80, 443) else ""
    return f"{host}{port}{p.path}?{p.query}".rstrip("?")


# --------------------------------------------------------------------------
# Testing against the bar
# --------------------------------------------------------------------------

def verdict(r: dict, bar: Bar) -> str | None:
    """Why a tested camera fails the bar, in plain words; None if it passes
    everything that can be judged so far."""
    status = r.get("status")
    if status in ("frozen", "recorded"):
        return "not live: " + (r.get("error") or status)
    if status != "online":
        return f"{status}: {r.get('error')}" if r.get("error") else status
    if r.get("kind") == "image":
        return "a still picture, not video"
    if r.get("kind") not in ("mjpeg", "hls"):
        return f"not a video stream ({r.get('kind')})"
    if not r.get("height"):
        return "picture size unknown"
    if r["height"] < bar.min_height:
        return f"too small: {r['width']}x{r['height']}"
    if r.get("kind") == "hls" and r.get("cors") is False:
        return "its server won't let other sites (the map) play it"
    if r.get("codec") == "hevc":
        return "H.265 video, which most browsers can't play"
    if r.get("codec") not in (None, "h264"):
        return f"{r['codec']} video, which browsers can't play"
    if bar.min_fps and r.get("fps") is not None and r["fps"] < bar.min_fps:
        return f"choppy: {r['fps']:g} frames a second"
    if bar.max_delay and (r.get("delay_s") or 0) > bar.max_delay:
        return f"too far behind: about {r['delay_s']:.0f} s"
    if r.get("live") is False:
        return "not live"
    return None


def _load_history() -> dict:
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_history(history: dict) -> None:
    try:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(json.dumps(history), encoding="utf-8")
    except OSError:
        pass


def test_all(cams: list[dict], bar: Bar, workers: int, retest: bool) -> list[dict]:
    history = _load_history()
    now = time.time()
    results: list[dict] = []
    todo = []
    for c in cams:
        h = history.get(c["id"])
        if (not retest and h and h.get("height") and h["height"] < bar.min_height
                and now - h.get("at", 0) < SMALL_SKIP_DAYS * 86400):
            r = scan._result(c, status="online", kind=h.get("kind"), width=h.get("width"), height=h["height"])
            r["skipped"] = True
            results.append(r)
        else:
            todo.append(c)
    if len(todo) < len(cams):
        print(f"Skipping {len(cams) - len(todo)} cameras found too small in the last {SMALL_SKIP_DAYS} days "
              f"(--retest to check them again).")

    print(f"Testing {len(todo)} cameras, {workers} at a time...")
    started = time.monotonic()
    servers = _Servers()

    def probe(c: dict) -> dict:
        host = (urlparse(c["stream_url"]).hostname or "").lower()
        if servers.given_up(host):
            return scan._result(c, status="offline",
                                error=f"server not answering you (gave up after {HOST_GIVE_UP} cameras)")
        try:
            found = scan.probe_url(c["stream_url"], min_height=bar.min_height)
        except Exception as e:  # one bad camera must never stop the run
            found = {"status": "offline", "error": type(e).__name__}
        r = scan._result(c, **found)
        r["score"] = scan.score(r)
        servers.note(host, r)
        return r

    fresh: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(probe, c) for c in todo]
        for n, fut in enumerate(as_completed(futures), start=1):
            fresh.append(fut.result())
            if n % 100 == 0 or n == len(todo):
                ok = sum(1 for r in fresh if verdict(r, bar) is None)
                print(f"  {n}/{len(todo)} tested, {ok} look proper so far ({time.monotonic() - started:.0f} s)")
    if servers.skipped():
        print("Servers that didn't answer you (their other cameras were skipped): " + ", ".join(servers.skipped()))

    # Second look, a chunk later, only at HLS cameras that pass everything
    # else: a live stream has added new video by then.
    pending = [r for r in fresh if r.get("_recheck") and verdict(r, bar) is None]
    for r in fresh:
        if r not in pending:
            r.pop("_recheck", None)
    if pending:
        print(f"Checking that {len(pending)} HLS cameras keep adding new video...")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(scan.recheck_hls, pending))

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    for r in fresh:
        r["tested_at"] = stamp
        if r.get("height"):
            history[r["id"]] = {"at": now, "kind": r.get("kind"), "width": r.get("width"), "height": r["height"]}
    _save_history(history)
    return results + fresh


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

QUALITY_FIELDS = ("status", "kind", "live", "delay_s", "segment_s", "codec", "width", "height", "fps",
                  "score", "probed_url", "tested_at")


def save(cams: list[dict], results: list[dict], bar: Bar) -> list[dict]:
    by_id = {c["id"]: c for c in cams}
    proper, rows = [], []
    for r in results:
        why = verdict(r, bar)
        if why is None and r.get("live") is not True:
            why = "not confirmed live"
        cam = by_id[r["id"]]
        if why is None:
            proper.append({**cam, "q": {k: r.get(k) for k in QUALITY_FIELDS}})
        rows.append({
            "verdict": "proper" if why is None else "failed",
            "why": why or "",
            "id": r["id"], "source": r["source"], "publisher": cam.get("publisher") or "",
            "place": " ".join(x for x in (cam.get("road"), cam.get("description")) if x),
            "kind": r.get("kind"), "width": r.get("width"), "height": r.get("height"), "fps": r.get("fps"),
            "delay_s": r.get("delay_s"), "chunk_s": r.get("segment_s"),
            "tested_at": r.get("tested_at") or "skipped (known too small)",
            "stream_url": r["stream_url"],
        })
    proper.sort(key=lambda c: (c["q"]["delay_s"] or 0, -(c["q"]["height"] or 0)))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "found_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "bar": vars(bar),
        "cameras": proper,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    rows.sort(key=lambda x: (x["verdict"] != "proper", x["source"], x["id"]))
    with REPORT_PATH.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig opens cleanly in Excel
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["verdict"])
        writer.writeheader()
        writer.writerows(rows)
    return rows


def summary(rows: list[dict]) -> None:
    by_source: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_source[row["source"]].append(row)
    print(f"\n{'source':28} {'tested':>6} {'proper':>6}  main reasons the rest failed")
    for source, xs in sorted(by_source.items(), key=lambda kv: -sum(x["verdict"] == "proper" for x in kv[1])):
        reasons = Counter(_reason_group(x["why"]) for x in xs if x["verdict"] != "proper")
        top = ", ".join(f"{k} {v}" for k, v in reasons.most_common(3))
        print(f"{source:28} {len(xs):>6} {sum(x['verdict'] == 'proper' for x in xs):>6}  {top}")
    proper = [x for x in rows if x["verdict"] == "proper"]
    print(f"\n{len(proper)} proper cameras saved to {OUT_PATH}; every camera's result is in {REPORT_PATH}.")
    if proper:
        mjpeg = sum(1 for x in proper if x["kind"] == "mjpeg")
        fhd = sum(1 for x in proper if (x["height"] or 0) >= 1080)
        print(f"  {mjpeg} real-time MJPEG, {len(proper) - mjpeg} HLS; {fhd} at 1080p or better.")
    # Sharp cameras that missed only on delay: worth knowing about.
    slower = sorted(x["delay_s"] for x in rows if x["why"].startswith("too far behind") and x["delay_s"])
    if slower:
        suggest = next((d for d in (20, 25, 30, 40, 60) if d >= slower[int(len(slower) * 0.8)]), 60)
        within = sum(1 for d in slower if d <= suggest)
        print(f"  {len(slower)} more cameras were sharp enough but further behind (about "
              f"{slower[0]:.0f}-{slower[-1]:.0f} s). --max-delay {suggest} would let {within} of them in.")
    if proper:
        print("Next: python -m src.map")


def _reason_group(why: str) -> str:
    for key in ("too small", "too far behind", "choppy", "not live", "won't let", "offline",
                "still picture", "H.265", "picture size unknown", "not confirmed"):
        if key in why:
            return {"won't let": "blocks other sites", "still picture": "still picture"}.get(key, key)
    return why.split(":")[0][:24] if why else "?"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Find and test proper live cameras.")
    p.add_argument("--group", nargs="+", choices=[g.key for g in GROUPS] + ["all"],
                   help="camera groups to search (default: " + " ".join(g.key for g in GROUPS if g.default) + ")")
    p.add_argument("--source", nargs="+", help="only these camera sources, e.g. taichung argus-bantul")
    p.add_argument("--min-height", type=int, default=720, help="smallest picture height in pixels (default 720)")
    p.add_argument("--min-fps", type=float, default=2.0, help="fewest frames a second (default 2; 0 = any)")
    p.add_argument("--max-delay", type=float, default=15.0,
                   help="most seconds behind real time (default 15; MJPEG is about 1)")
    p.add_argument("--workers", type=int, default=12, help="cameras tested at once (default 12; be polite)")
    p.add_argument("--retest", action="store_true", help="also retest cameras found too small recently")
    p.add_argument("--list", action="store_true", help="show the groups and exit")
    args = p.parse_args(argv)

    if args.list:
        for g in GROUPS:
            print(f"{g.key:12} {'(default) ' if g.default else '(opt-in)  '}{g.label}: {g.note}")
            print(f"{'':12} sources: {' '.join(g.sources)}")
        return

    groups = GROUPS if args.group and "all" in args.group else (
        [GROUP_BY_KEY[k] for k in args.group] if args.group else [g for g in GROUPS if g.default])
    patterns = list(args.source) if args.source else [s for g in groups for s in g.sources]
    bar = Bar(args.min_height, args.min_fps, args.max_delay)

    cams = gather(patterns)
    if args.source:
        cams = [c for c in cams if _wanted(c["source"], patterns)]
    if not cams:
        raise SystemExit("No candidate cameras found. Check your internet connection.")
    print(f"\n{len(cams):,} candidate cameras. The bar: {bar.min_height}p or better, "
          f"{bar.min_fps:g}+ frames a second, at most {bar.max_delay:g} s behind real time.")
    results = test_all(cams, bar, max(1, min(args.workers, 24)), args.retest)
    rows = save(cams, results, bar)
    summary(rows)


if __name__ == "__main__":
    main()
