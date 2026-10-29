"""Build an interactive map of every camera.

Reads data/cameras.json (and data/camera_quality.json if you've run the
scanner), and writes a single self-contained page to data/map.html.

    python -m src.map            # build and open in your browser
    python -m src.map --no-open  # build only

Clicking a pin opens the camera in a viewer that takes half the screen.
By default only cameras measured at 720p or better are shown (needs a scan),
plus cameras whose size is unknown. Use the sidebar to change that, or
--min-height 0 to start with everything. Nothing is recorded.
"""

from __future__ import annotations

import argparse
import json
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = Path("data/cameras.json")
QUALITY_PATH = Path("data/camera_quality.json")
TEMPLATE_PATH = ROOT / "frontend" / "map_template.html"
OUTPUT_PATH = Path("data/map.html")

QUALITY_FIELDS = ("status", "kind", "width", "height", "fps", "score", "probed_url")
CAMERA_FIELDS = ("id", "source", "category", "road", "direction", "description",
                 "lat", "lon", "stream_url", "url_type")


def _embed(value) -> str:
    """JSON that's safe to drop inside a <script> tag."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def build(output: Path = OUTPUT_PATH, min_height: int = 720) -> tuple[Path, int, int]:
    if not CAMERAS_PATH.exists():
        raise SystemExit("data/cameras.json not found. Run: python -m src.feeds.cameras")
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
        if cam["id"] in quality:
            rec["q"] = quality[cam["id"]]
        records.append(rec)

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.replace("__CAMERAS__", _embed(records))
    html = html.replace("__GENERATED__", _embed(datetime.now().strftime("%Y-%m-%d %H:%M")))
    html = html.replace("__MIN_HEIGHT__", str(int(min_height)))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output, len(records), sum(1 for r in records if "q" in r)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Build the camera map.")
    p.add_argument("--no-open", action="store_true", help="don't open the map in a browser")
    p.add_argument("--output", type=Path, default=OUTPUT_PATH)
    p.add_argument("--min-height", type=int, default=720, choices=[0, 480, 720, 1080],
                   help="starting picture-quality filter in pixels (default 720; 0 shows all)")
    args = p.parse_args(argv)

    path, n, scanned = build(args.output, args.min_height)
    print(f"Map built with {n:,} cameras ({scanned:,} with scan results): {path}")
    if not args.no_open:
        webbrowser.open(path.resolve().as_uri())


if __name__ == "__main__":
    main()
