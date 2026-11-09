"""Import official live-video cameras from the Argus camera map.

Argus (https://github.com/GoSlowPoke168/Argus, MIT, Copyright (c) 2026 Jeremy
Hou) publishes a ~229,000-camera list gathered from government and commercial
sources. ACE takes ONLY live video (HLS or MJPEG) from an explicit allowlist of
official publishers below, and for each one the stream must be served from
that publisher's own domain.

Deliberately left out:
  - commercial webcam companies, TV stations and resorts (their streams are
    meant to be watched on their own sites/players)
  - streams on bare IP addresses or dynamic-DNS hosts, whose owner can't be
    verified as the publishing agency
  - sources that point at private-camera sites
  - still images and short video clips (ACE is live video only)

Checked but excluded because every sampled link was dead (streams moved after
Argus collected them): Yogyakarta Province (jogjaprov.go.id) and the ITIC
Foundation, Thailand (iticfoundation.org).

The list is downloaded once and cached in data/cache/ for a week.
"""

from __future__ import annotations

import hashlib
import ipaddress
from urllib.parse import urlparse

from src.feeds.cache import cached_json
from src.feeds.formats import with_format

URL = "https://raw.githubusercontent.com/GoSlowPoke168/Argus/master/public/cameras.geojson"

# source -> (publisher, allowed stream host suffixes)
ALLOWLIST: dict[str, tuple[str, tuple[str, ...]]] = {
    # South Korea: city traffic information (ITS) centres
    "opencctv_topis-seoul": ("Seoul TOPIS", ("eseoul.go.kr",)),
    "opencctv_busan": ("Busan ITS", ("busan.go.kr",)),
    "opencctv_ulsan": ("Ulsan ITS", ("its.ulsan.kr",)),
    "opencctv_daegu": ("Daegu ITS", ("daegu.go.kr",)),
    "opencctv_pohang": ("Pohang City", ("pohang.go.kr",)),
    "opencctv_changwon": ("Changwon UTIS", ("changwon.go.kr",)),
    "opencctv_gwangju": ("Gwangju TIC", ("gjtic.go.kr",)),
    "opencctv_ansan": ("Ansan ITS", ("ansan.go.kr",)),
    "opencctv_chungju": ("Chungju ITS", ("chungju.go.kr",)),
    # Indonesia: provincial / city / regency governments, national toll roads
    "opencctv_jogjakarta": ("Yogyakarta City", ("jogjakota.go.id",)),
    "opencctv_bantul": ("Bantul Regency", ("bantulkab.go.id",)),
    "opencctv_tangerang": ("Tangerang Regency", ("tangerangkab.go.id",)),
    "opencctv_bandung-pelindung": ("Bandung City", ("bandung.go.id",)),
    "opencctv_tasikmalaya": ("Tasikmalaya City", ("tasikmalayakota.go.id",)),
    "opencctv_bondowoso": ("Bondowoso Regency", ("bondowosokab.go.id",)),
    "opencctv_asahan": ("Asahan Regency", ("asahankab.go.id",)),
    "opencctv_bpjt": ("Jasa Marga toll roads", ("jasamarga.com",)),
    # Japan, Macau, Türkiye
    "opencctv_kaiho": ("Japan Coast Guard (MLIT)", ("kaiho.mlit.go.jp",)),
    "opencctv_dsat": ("Macau DSAT", ("dsatmacau.com",)),
    "opencctv_istanbul-ibb": ("Istanbul Metropolitan Municipality", ("ibb.gov.tr",)),
    # Taiwan national freeways (duplicates of data.gov.tw are dropped later)
    "opencctv_twipcam": ("Taiwan Freeway Bureau", ("freeway.gov.tw",)),
    "opencctv_taiwan-freeway": ("Taiwan Freeway Bureau", ("freeway.gov.tw",)),
    # United States: state and local transport agencies
    "opencctv_virginia": ("Virginia DOT", ("vdotcameras.com",)),
    "opencctv_arlingtonva": ("Arlington County, VA", ("arlingtonva.us",)),
    "opencctv_njta": ("New Jersey Turnpike Authority", ("njta.com",)),
    "opencctv_pgctrip": ("Prince George's County, MD", ("skyvdn.com",)),
    "opencctv_msdot": ("Mississippi DOT", ("mdottraffic.com",)),
    "opencctv_oktraffic": ("Oklahoma DOT", ("oktraffic.org",)),
    "opencctv_wv511": ("West Virginia 511", ("roadsummary.com",)),
    "opencctv_castlerock": ("State DOT 511", ("dot.state.mn.us", "trafficwise.org")),
    "opencctv_arcgis_cams": ("Iowa DOT", ("iowadot.gov",)),
    "opencctv_ny511": ("New York State DOT", ("skyvdn.com",)),
    "opencctv_cotrip": ("Colorado DOT", ("cotrip.org",)),
    "opencctv_scdot": ("South Carolina DOT", ("skyvdn.com",)),
    "opencctv_mdchart": ("Maryland SHA", ("sha.maryland.gov",)),
    "opencctv_caltrans": ("Caltrans", ("dot.ca.gov",)),
    "opencctv_opentrafficcam": ("State DOTs", ("dot.ca.gov", "deldot.gov")),
}

LIVE_TYPES = {"m3u8": "hls", "mjpeg": "stream"}

ISO3 = {"US": "USA", "TW": "TWN", "KR": "KOR", "ID": "IDN", "JP": "JPN", "MO": "MAC",
        "TR": "TUR", "TH": "THA", "SG": "SGP", "GB": "GBR", "RU": "RUS"}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def allowed(source: str, url: str) -> bool:
    """True only for an allowlisted source whose stream is on its own domain."""
    entry = ALLOWLIST.get(source)
    if not entry or not url.startswith("https://") and not url.startswith("http://"):
        return False
    host = _host(url)
    if not host or _is_ip(host):
        return False
    return any(host == s or host.endswith("." + s) for s in entry[1])


def convert(data: dict) -> list[dict]:
    cameras = []
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        kind = LIVE_TYPES.get(p.get("feedType"))
        url = (p.get("streamUrl") or p.get("feedUrl") or "").strip()
        if not kind or not allowed(p.get("source", ""), url):
            continue
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2 or (abs(coords[0]) < 0.01 and abs(coords[1]) < 0.01):
            continue
        publisher = ALLOWLIST[p["source"]][0]
        src = "argus-" + p["source"].removeprefix("opencctv_")
        cc = (p.get("country") or "").upper()
        cameras.append(with_format({
            "id": f"{src}:{hashlib.sha1(url.encode()).hexdigest()[:10]}",
            "source": src,
            "category": "traffic",
            "country": ISO3.get(cc, cc or "other"),
            "region": p.get("city") or publisher,
            "county": None,
            "road": p.get("route") or p.get("highway") or None,
            "direction": p.get("direction") or None,
            "description": p.get("name") or publisher,
            "lat": float(coords[1]),
            "lon": float(coords[0]),
            "stream_url": url,
            "url_type": kind,
            "encoding": "H.264" if kind == "hls" else "JPEG",
            "format": "M3U8" if kind == "hls" else "MJPEG",
            "publisher": publisher,
        }))
    return cameras


def fetch_all() -> list[dict]:
    print("Fetching Argus official live-video cameras (worldwide)...")
    try:
        data = cached_json(URL, "argus-cameras.geojson")
    except Exception as e:
        print(f"  ! skipped: {type(e).__name__}: {e}")
        return []
    cameras = convert(data)
    seen, unique = set(), []
    for c in cameras:
        if c["stream_url"] not in seen:
            seen.add(c["stream_url"])
            unique.append(c)
    countries = sorted({c["country"] for c in unique})
    print(f"  {len(unique)} live streams from official publishers ({', '.join(countries)})")
    return unique
