"""Build data/cameras.json from public camera sources.

Default sources need no account or key:
  opendata  Taiwan government open data (data.gov.tw)
  otcm      OpenTrafficCamMap's crowdsourced US camera list (MIT licence)
  sgp       Singapore LTA traffic images (data.gov.sg)

Off by default (opt in with --source):
  saat      US DOT cameras from the seeallthethings list (SCDOT/VDOT/DDOT/SHA).
            A 2018 list whose links are now dead; kept for completeness.
  tdx       Taiwan TDX (needs keys in .env)

Every camera follows OpenTrafficCamMap's conventions (country, region,
county, encoding, format, update rate; see src/feeds/formats.py). Besides the
flat data/cameras.json, a per-country copy in OpenTrafficCamMap's nested
layout is written to data/cameras/<COUNTRY>.json.

Examples:
    python -m src.feeds.cameras                          # Taiwan + US + Singapore
    python -m src.feeds.cameras --source opendata        # Taiwan only
    python -m src.feeds.cameras --source otcm            # US only
    python -m src.feeds.cameras --source sgp             # Singapore only
    python -m src.feeds.cameras --category traffic       # Taiwan road cameras + US
    python -m src.feeds.cameras --source opendata tdx    # Taiwan open data + TDX
    python -m src.feeds.cameras --source tdx --city NewTaipei Taoyuan
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from src.feeds import opendata, otcm, saat, sgp
from src.feeds.formats import with_format

OUTPUT_PATH = Path("data/cameras.json")
COUNTRY_DIR = Path("data/cameras")


def _fetch_tdx(cities: list[str] | None) -> list[dict]:
    # Imported here so open-data users never need TDX keys or settings.
    from src.feeds import tdx_cameras
    from src.feeds.tdx_auth import TDXAuthError

    try:
        return tdx_cameras.fetch_all(cities or None)
    except TDXAuthError as e:
        print(f"Skipping TDX: {e}")
        return []


def save(cameras: list[dict], path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cameras, ensure_ascii=False, indent=2), encoding="utf-8")


def export_by_country(cameras: list[dict], folder: Path = COUNTRY_DIR) -> list[Path]:
    """Write one file per country in OpenTrafficCamMap's nested layout:
    {region: {county: [camera, ...]}} with its field names."""
    nested: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for c in cameras:
        entry = {
            "description": " ".join(x for x in (c.get("road"), c.get("description")) if x) or c["id"],
            "latitude": c["lat"],
            "longitude": c["lon"],
            "url": c["stream_url"],
            "encoding": c.get("encoding"),
            "format": c.get("format"),
        }
        if c.get("direction"):
            entry["direction"] = c["direction"]
        if c.get("update_rate"):
            entry["updateRate"] = c["update_rate"]
        # ACE extras, so records can be matched back to cameras.json.
        entry["id"] = c["id"]
        entry["source"] = c["source"]
        entry["category"] = c.get("category")
        nested[c.get("country") or "other"][c.get("region") or "other"][c.get("county") or "other"].append(entry)

    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for country, regions in nested.items():
        path = folder / f"{country}.json"
        path.write_text(json.dumps(regions, ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fetch public camera lists.")
    parser.add_argument("--source", nargs="+",
                        choices=["opendata", "otcm", "sgp", "saat", "tdx", "all"],
                        default=["opendata", "otcm", "sgp"],
                        help="sources to use (default: opendata otcm sgp; no keys needed)")
    parser.add_argument("--category", choices=["traffic", "water"], action="append",
                        help="limit Taiwan open-data sources to a category (can repeat)")
    parser.add_argument("--city", nargs="+", help="TDX only: city codes such as NewTaipei Taoyuan")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)

    sources = ({"opendata", "otcm", "sgp", "saat", "tdx"} if "all" in args.source
               else set(args.source))
    cameras: list[dict] = []
    if "opendata" in sources:
        cameras += opendata.fetch_all(set(args.category) if args.category else None)
    if "otcm" in sources:
        cameras += otcm.fetch_all()
    if "sgp" in sources:
        cameras += sgp.fetch_all()
    if "saat" in sources:
        cameras += saat.fetch_all()
    if "tdx" in sources:
        cameras += _fetch_tdx(args.city)

    if not cameras:
        print("No cameras returned. Check your internet connection (and TDX keys if using TDX).")
        sys.exit(1)

    # If two sources list the same camera, keep the first one seen.
    cameras = [with_format(c) for c in {c["id"]: c for c in cameras}.values()]
    save(cameras, args.output)
    country_files = export_by_country(cameras)

    print(f"\nFound {len(cameras):,} cameras. Saved to {args.output}")
    for country, count in Counter(c["country"] for c in cameras).most_common():
        print(f"  {country}: {count:,}")
    for source, count in Counter(c["source"] for c in cameras).most_common():
        print(f"    {source:<22} {count:>5}")
    by_format = Counter(c["format"] for c in cameras)
    print("  formats: " + ", ".join(f"{k} {v}" for k, v in by_format.most_common()))
    print("  per-country files: " + ", ".join(str(p) for p in country_files))

    print("\nExample camera:")
    print(json.dumps(cameras[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
