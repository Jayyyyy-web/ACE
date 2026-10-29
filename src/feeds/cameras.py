"""Build data/cameras.json from Taiwan's public camera sources.

By default this uses data.gov.tw open data only: no account, no keys.
TDX is optional and only used if you ask for it.

Examples:
    python -m src.feeds.cameras                       # open data, all categories
    python -m src.feeds.cameras --category traffic    # road cameras only
    python -m src.feeds.cameras --category water      # flood/river/debris-flow cameras only
    python -m src.feeds.cameras --source tdx          # TDX only (needs .env keys)
    python -m src.feeds.cameras --source tdx --city NewTaipei Taoyuan
    python -m src.feeds.cameras --source all          # open data + TDX
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from src.feeds import opendata

OUTPUT_PATH = Path("data/cameras.json")


def _fetch_tdx(cities: list[str] | None) -> list[dict]:
    # Imported here so open-data users never need TDX keys or settings.
    from src.feeds import tdx_cameras
    from src.feeds.tdx_auth import TDXAuthError

    try:
        sources = cities or None
        return tdx_cameras.fetch_all(sources)
    except TDXAuthError as e:
        print(f"Skipping TDX: {e}")
        return []


def save(cameras: list[dict], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cameras, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fetch Taiwan public camera lists.")
    parser.add_argument("--source", choices=["opendata", "tdx", "all"], default="opendata",
                        help="where to get cameras from (default: opendata, no keys needed)")
    parser.add_argument("--category", choices=["traffic", "water"], action="append",
                        help="limit open-data sources to a category (can repeat)")
    parser.add_argument("--city", nargs="+", help="TDX only: city codes such as NewTaipei Taoyuan")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)

    cameras: list[dict] = []
    if args.source in ("opendata", "all"):
        cameras += opendata.fetch_all(set(args.category) if args.category else None)
    if args.source in ("tdx", "all"):
        cameras += _fetch_tdx(args.city)

    if not cameras:
        print("No cameras returned. Check your internet connection (and TDX keys if using TDX).")
        sys.exit(1)

    # If both sources list the same camera, keep the first one seen.
    cameras = list({c["id"]: c for c in cameras}.values())
    save(cameras, args.output)

    print(f"\nFound {len(cameras):,} cameras. Saved to {args.output}")
    for source, count in Counter(c["source"] for c in cameras).most_common():
        print(f"  {source:<22} {count:>5}")
    by_type = Counter(c["url_type"] for c in cameras)
    print("  link types: " + ", ".join(f"{k} {v}" for k, v in by_type.most_common()))

    print("\nExample camera:")
    print(json.dumps(cameras[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
