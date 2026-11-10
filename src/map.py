"""Build an interactive camera map.

Once you've run the finder (python -m src.find), the map shows its proper
cameras: data/proper_cameras.json, every one tested live, sharp and close to
real time. With --all (or before the finder has run) it shows the older, much
bigger list instead: data/cameras.json, plus data/camera_quality.json if
you've run the scanner. Either way it writes one self-contained page to
data/map.html.

    python -m src.map             # build, serve on http://localhost:8765, open browser
    python -m src.map --all       # the full list instead of the proper cameras
    python -m src.map --no-serve  # build and open the file directly
    python -m src.map --no-open   # build only

Why serve it? Opened straight from a file, the page has no web address, and
some camera servers (e.g. California's live video) refuse requests from
pages without one. A tiny local server on your own computer fixes that.
Press Ctrl+C to stop it.

By default only live-video cameras are shown (MJPEG, HLS and city video
players); tick them back on in the sidebar or use --include-stills. Once
you've run the scanner, only cameras it found live are shown (new video kept
arriving: nothing frozen or pre-recorded), up to 15 s behind real time; see
--untested and --max-delay. HLS video plays one chunk plus 2 s behind the
newest video instead of hls.js's default three chunks.

Clicking a pin opens the camera in a viewer that takes half the screen.
By default only cameras measured at 720p or better are shown (needs a scan),
plus cameras whose size is unknown. Use the sidebar to change that, or
--min-height 0 to start with everything. Nothing is recorded.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = Path("data/cameras.json")
QUALITY_PATH = Path("data/camera_quality.json")
PROPER_PATH = Path("data/proper_cameras.json")
TEMPLATE_PATH = ROOT / "frontend" / "map_template.html"
OUTPUT_PATH = Path("data/map.html")

QUALITY_FIELDS = ("status", "kind", "live", "delay_s", "segment_s", "width", "height", "fps",
                  "score", "probed_url")
DELAY_CHOICES = (5, 10, 15, 30)
CAMERA_FIELDS = ("id", "source", "category", "country", "region", "road", "direction",
                 "description", "lat", "lon", "stream_url", "url_type", "format", "update_rate",
                 "api_camera_id", "publisher", "page_url")


def _embed(value) -> str:
    """JSON that's safe to drop inside a <script> tag."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _proper_records() -> tuple[list[dict], dict]:
    data = json.loads(PROPER_PATH.read_text(encoding="utf-8"))
    records = []
    for cam in data.get("cameras", []):
        if cam.get("lat") is None or cam.get("lon") is None:
            continue
        rec = {k: cam.get(k) for k in CAMERA_FIELDS}
        rec["q"] = {k: (cam.get("q") or {}).get(k) for k in QUALITY_FIELDS}
        records.append(rec)
    return records, data


def _all_records() -> list[dict]:
    if not CAMERAS_PATH.exists():
        raise SystemExit("No camera list yet. Run: python -m src.find   (or python -m src.feeds.cameras for --all)")
    cameras = json.loads(CAMERAS_PATH.read_text(encoding="utf-8"))
    quality = {}
    if QUALITY_PATH.exists():
        for r in json.loads(QUALITY_PATH.read_text(encoding="utf-8")):
            quality[r["id"]] = {k: r.get(k) for k in QUALITY_FIELDS}
    records = []
    for cam in cameras:
        if cam.get("lat") is None or cam.get("lon") is None:
            continue
        rec = {k: cam.get(k) for k in CAMERA_FIELDS}
        rec["country"] = rec.get("country") or "TWN"  # lists made before countries existed
        if cam["id"] in quality:
            rec["q"] = quality[cam["id"]]
        records.append(rec)
    return records


def build(output: Path = OUTPUT_PATH, min_height: int | None = None, live_only: bool = True,
          tested_only: bool = True, max_delay: int | None = None,
          show_all: bool = False) -> tuple[Path, int, int, bool]:
    """min_height and max_delay set where the sidebar filters start; left as
    None, the proper-cameras map starts at the finder's bar (nothing hidden)
    and the full map at 720p and 15 s."""
    proper = not show_all and PROPER_PATH.exists()
    if proper:
        records, data = _proper_records()
        bar = data.get("bar") or {}
        # Everything here already passed the finder's bar; start the sidebar
        # filters there so nothing is hidden, and let the user tighten them.
        if min_height is None:
            min_height = max(h for h in (0, 480, 720, 1080) if h <= bar.get("min_height", 720))
        if max_delay is None:
            limit = bar.get("max_delay") or 0
            max_delay = next((d for d in DELAY_CHOICES if d >= limit), 0) if limit else 0
        subtitle = "proper cameras"
        footnote = (f"Official public cameras, each tested live, {bar.get('min_height', 720)}p or sharper and "
                    f"close to real time on {data.get('found_at', '?')}.")
    else:
        records = _all_records()
        min_height = 720 if min_height is None else min_height
        max_delay = 15 if max_delay is None else max_delay
        subtitle = "camera map"
        footnote = "Public open-data feeds."

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.replace("__CAMERAS__", _embed(records))
    html = html.replace("__GENERATED__", _embed(datetime.now().strftime("%Y-%m-%d %H:%M")))
    html = html.replace("__MIN_HEIGHT__", str(int(min_height)))
    html = html.replace("__LIVE_ONLY__", "true" if live_only else "false")
    html = html.replace("__TESTED_ONLY__", "true" if tested_only else "false")
    html = html.replace("__MAX_DELAY__", str(int(max_delay)))
    html = html.replace("__SUBTITLE__", subtitle)
    html = html.replace("__FOOTNOTE__", footnote)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output, len(records), sum(1 for r in records if "q" in r), proper


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep the terminal readable
        pass


def serve(path: Path, port: int, open_browser: bool) -> None:
    """Serve only the folder the map is in, on this computer only."""
    folder = path.resolve().parent
    handler = functools.partial(_QuietHandler, directory=str(folder))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), handler) as httpd:
        url = f"http://localhost:{port}/{path.name}"
        print(f"Serving the map at {url}  (Ctrl+C to stop)")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Build the camera map.")
    p.add_argument("--no-open", action="store_true", help="build only: don't serve or open the map")
    p.add_argument("--no-serve", action="store_true", help="open the file directly instead of serving it")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--output", type=Path, default=OUTPUT_PATH)
    p.add_argument("--min-height", type=int, choices=[0, 480, 720, 1080],
                   help="starting picture-quality filter in pixels (default: the finder's bar, or 720 with --all; 0 shows all)")
    p.add_argument("--include-stills", action="store_true",
                   help="start with still images and web pages shown too (default: live video only)")
    p.add_argument("--untested", action="store_true",
                   help="start with untested cameras shown too (default once you've scanned: "
                        "only cameras the scan found live)")
    p.add_argument("--max-delay", type=int, choices=[5, 10, 15, 30, 0],
                   help="starting limit on how far behind real time a camera may run, in seconds "
                        "(default: the finder's bar, or 15 with --all; 5 = real time; 0 = any)")
    p.add_argument("--all", action="store_true",
                   help="show the full camera list (data/cameras.json) instead of the finder's proper cameras")
    args = p.parse_args(argv)

    path, n, scanned, proper = build(args.output, args.min_height, live_only=not args.include_stills,
                                     tested_only=not args.untested, max_delay=args.max_delay,
                                     show_all=args.all)
    if proper:
        print(f"Map built with the {n:,} proper cameras from {PROPER_PATH}: {path}")
        print("  (python -m src.map --all shows the full, untested list instead)")
    else:
        print(f"Map built with {n:,} cameras ({scanned:,} with scan results): {path}")
        if not args.all:
            print("  Tip: python -m src.find finds and tests the proper cameras; the map then shows only those.")
    if args.no_open:
        return
    if args.no_serve:
        webbrowser.open(path.resolve().as_uri())
        return
    serve(path, args.port, open_browser=True)


if __name__ == "__main__":
    main()
