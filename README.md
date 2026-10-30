# ACE

A personal project that gathers public traffic camera feeds (official open data from Taiwan and Singapore, plus US cameras from OpenTrafficCamMap) and uses computer vision to analyse traffic: vehicle and pedestrian counts, congestion, and unusual events.

Scope: anonymous, aggregate analysis only. No identification or tracking of individual people or vehicles.

## Structure

- `src/feeds/` – camera list fetching, quality scanning, shared formats
- `src/map.py` – builds and serves the camera map
- `src/vision/` – object detection on camera frames
- `src/api/` – backend API
- `frontend/` – map template

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install requests python-dotenv certifi   # enough for fetching, scanning and the map
pip install -r requirements.txt              # everything (large: includes PyTorch)
```

## Usage

No account or API key needed.

```bash
python -m src.feeds.cameras                      # Taiwan + US + Singapore -> data/cameras.json
python -m src.feeds.cameras --source opendata    # Taiwan only
python -m src.feeds.cameras --source otcm        # US only
python -m src.feeds.cameras --source sgp         # Singapore only
python -m src.feeds.cameras --category traffic   # Taiwan road cameras only (US is all road cameras)
```

Besides the flat `data/cameras.json`, a copy per country is written to `data/cameras/<COUNTRY>.json` in OpenTrafficCamMap's nested layout (region → county → cameras).

### Sources

**Taiwan** — government open data from data.gov.tw (Open Government Data License v1):

| Source | Category | Dataset |
|---|---|---|
| Freeway Bureau (national freeways) | traffic | [37665](https://data.gov.tw/dataset/37665) |
| Keelung City | traffic | [59458](https://data.gov.tw/dataset/59458) |
| Chiayi County | traffic | [122133](https://data.gov.tw/dataset/122133) |
| Chiayi City | traffic | [173813](https://data.gov.tw/dataset/173813) |
| Tainan City | traffic | [166140](https://data.gov.tw/dataset/166140) |
| New Taipei City (view-only) | traffic | [158108](https://data.gov.tw/dataset/158108) |
| Taipei MRT construction-site cameras | traffic | [138749](https://data.gov.tw/dataset/138749), [138750](https://data.gov.tw/dataset/138750), [145692](https://data.gov.tw/dataset/145692) |
| Water Resources Agency flood cameras | water | [36687](https://data.gov.tw/dataset/36687) |
| Water Resources Agency river cameras | water | [41567](https://data.gov.tw/dataset/41567) |
| Debris-flow monitoring cameras | water | [9327](https://data.gov.tw/dataset/9327) |

Download links are looked up from the data.gov.tw metadata API on every run, so the fetcher keeps working when a city moves its files. Sources that fail are skipped, not fatal.

Not included: Taipei City's road cameras. That dataset only has locations, and using Taipei's live traffic images requires an application to the city.

**United States** — [OpenTrafficCamMap](https://github.com/AidanWelch/OpenTrafficCamMap) (MIT licence), a crowdsourced list of state DOT cameras: about 6,900 cameras across California, Ohio, Colorado, Indiana, Alabama, Alaska, Delaware, Kentucky, Arizona and Georgia. Its data was last updated in 2024, so some links are dead; the scanner finds which work. Cameras marked for review, at bad coordinates, or in agency-specific formats are skipped.

**United States — optional `saat` source (off by default).** DOT feeds (SCDOT, VDOT, DDOT, Maryland SHA, Montgomery County) whose compiled list comes from [seeallthethings](https://github.com/baywolf88/seeallthethings). ACE imports only those government feeds and refuses that list's private/unsecured-camera references (Insecam, Shodan). The list is from 2018 and its links are now dead (expired tokens, retired camera IPs), so it is not fetched by default; enable it with `python -m src.feeds.cameras --source opendata otcm sgp saat` if you want it anyway.

**Singapore** — the Land Transport Authority's traffic images on [data.gov.sg](https://api.data.gov.sg/v1/transport/traffic-images), no key needed. Since about July 2026 this free API only serves 8 cameras (Woodlands Causeway, Tuas Second Link, Sentosa Gateway); the full ~90-camera network is only on LTA DataMall, which needs a registered key. All 8 are 1920×1080 stills refreshed about every 20 seconds. Each snapshot gets a new URL, so records keep the camera's `api_camera_id` and the map and scanner fetch the latest image from the API (format `UNIQUE_SINGAPORE_LTA`).

### Camera map

```bash
python -m src.map
```

Builds `data/map.html`, serves it on `http://localhost:8765` and opens it in your browser. Press **Ctrl+C** in the terminal to stop. (It's served rather than opened as a file because some camera servers, like California's live video, refuse requests from pages without a web address. The server only listens on your own computer.) Use `--no-serve` to open the file directly, or `--no-open` to just build it.

**Live video only** is on by default: the map shows cameras with moving video (MJPEG streams, HLS video and city video players). Untick it in the sidebar to also see still images and web pages, or start that way with `python -m src.map --include-stills`.

Every camera is a pin, clustered by area and coloured by type, with search (road, place, state or ID), and filters by country, type and source. Each country has a **zoom** button.

Click a pin and the camera opens in a viewer that takes half the screen (the bottom half on a phone). Live video (MJPEG and HLS) plays directly; still images refresh automatically. Use **‹ Prev / Next ›** or the `[` and `]` keys to flip through the cameras currently shown, and **Esc** to close. The feed stops as soon as you close or switch cameras.

**Picture quality:** by default the map only shows cameras measured at 720p or better, so everything you open fills the viewer. This needs scan results. Cameras whose size is unknown (not scanned yet, or New Taipei's city viewers) are included unless you untick that option. Change the starting filter with `python -m src.map --min-height 1080` (or `480`, or `0` for everything).

### Check camera quality

```bash
python -m src.feeds.scan --region new-taipei           # New Taipei area (includes Taipei City)
python -m src.feeds.scan --category traffic            # all road cameras (slow with US included)
python -m src.feeds.scan --country TWN                 # Taiwan only
python -m src.feeds.scan --country USA --sample 300    # 300 random US cameras
python -m src.feeds.scan --country SGP                 # Singapore
```

Connects to each camera for a few seconds and records whether it's online, its resolution, frame rate and response time, then ranks them. HLS video is measured from its playlist. Results go to `data/camera_quality.json` and `data/camera_quality.csv` (opens in Excel), merged with earlier scans so you can scan one country or area at a time. No footage is saved. Taiwan regions: `new-taipei`, `keelung`, `taoyuan`, `taichung`, `tainan`, `kaohsiung`.

### Optional: TDX

TDX covers every Taiwan city, but needs a free account. Put your keys in `.env` (copy `.env.example`), then:

```bash
python -m src.feeds.tdx_auth                               # check your keys work
python -m src.feeds.cameras --source tdx                   # TDX only
python -m src.feeds.cameras --source tdx --city NewTaipei Taoyuan
python -m src.feeds.cameras --source all                   # everything
```

### Camera record format

Records follow [OpenTrafficCamMap's conventions](https://github.com/AidanWelch/OpenTrafficCamMap#camera-list): country (ISO alpha-3), administrative region, county, encoding and format. See `src/feeds/formats.py`.

```json
{
  "id": "keelung:T000002",
  "source": "keelung",
  "category": "traffic",
  "country": "TWN",
  "region": "基隆市",
  "county": "other",
  "road": "國道3號",
  "direction": "N",
  "description": "基金一路 基金交流道下匝道",
  "lat": 25.13972,
  "lon": 121.71492,
  "stream_url": "https://CCTV.KLCG.GOV.TW:443/9cc4ca1c",
  "url_type": "stream",
  "encoding": "JPEG",
  "format": "MJPEG",
  "update_rate": null,
  "refresh_rate": null
}
```

| `url_type` | `format` | Meaning |
|---|---|---|
| `stream` | `MJPEG` | live video as a stream of JPEGs |
| `image` | `IMAGE_STREAM` | a still image that refreshes |
| `hls` | `M3U8` | live H.264 video (HLS) |
| `page` | `WEB_PAGE` | a web page that embeds the camera |
| `viewer` | `WEB_VIEWER` | an agency's official viewer page |

`MJPEG`, `WEB_PAGE` and `WEB_VIEWER` aren't in OpenTrafficCamMap's format list yet; its README says the list should be added to.

`viewer` cameras (New Taipei) come from a dataset with locations but no stream links, so each links to the city's official live-traffic viewer page. They're shown in the map viewer; the scanner and any automated analysis skip them. Analysing New Taipei's video automatically would need the official TDX feed.

### Note on Python 3.13+

Many Taiwan government sites use certificates that newer Python rejects as "Missing Subject Key Identifier". `src/feeds/http.py` relaxes only that extra strictness check. Certificates and hostnames are still fully verified.

## Credits

- US camera list and record conventions: [OpenTrafficCamMap](https://github.com/AidanWelch/OpenTrafficCamMap), Copyright (c) 2020 AidanWelch, MIT licence. Full text in [`licenses/OpenTrafficCamMap-MIT.txt`](licenses/OpenTrafficCamMap-MIT.txt).
- Taiwan camera lists: data.gov.tw, Open Government Data License v1.
- Singapore traffic images: Land Transport Authority via data.gov.sg, Singapore Open Data Licence.
- Basemap: Esri, HERE, Garmin, © OpenStreetMap contributors.

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for all licences and terms.

## Roadmap

- [x] Phase 1a: camera lists from open data (and optionally TDX)
- [x] Phase 1b: camera quality scanner
- [x] Phase 1c: camera map
- [x] Phase 1d: OpenTrafficCamMap format + US cameras
- [x] Phase 1e: Singapore (free API: 8 cameras)
- [ ] Phase 2: run object detection on selected feeds and store counts
- [ ] Phase 3: detect anomalies (sudden drops or spikes)
- [ ] Phase 4: natural-language queries over the data
