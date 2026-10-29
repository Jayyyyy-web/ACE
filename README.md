# ACE

A personal project that pulls Taiwan's public traffic camera feeds (open data via MOTC TDX and city open-data portals) and uses computer vision to analyze traffic: vehicle and pedestrian counts, congestion, and unusual events.

Scope: anonymous, aggregate analysis only. No identification or tracking of individual people or vehicles.

## Structure

- `src/feeds/` – TDX authentication and camera list fetching
- `src/vision/` – object detection on camera frames
- `src/api/` – backend API
- `frontend/` – camera map and dashboard

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install requests python-dotenv certifi   # enough for the camera fetcher
pip install -r requirements.txt              # everything (large: includes PyTorch)
```

## Usage

No account or API key needed. By default, camera lists come from Taiwan's government open-data portal (data.gov.tw), under the Open Government Data License v1.

```bash
python -m src.feeds.cameras                      # all open-data cameras -> data/cameras.json
python -m src.feeds.cameras --category traffic   # road cameras only
python -m src.feeds.cameras --category water     # flood / river / debris-flow cameras only
```

### Open-data sources

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

### Camera map

```bash
python -m src.map
```

Builds `data/map.html` and opens it in your browser: every camera as a pin, clustered by area and coloured by type, with search (road, district or ID) and filters by type and source.

Click a pin and the camera opens in a viewer that takes half the screen (the bottom half on a phone). Use **‹ Prev / Next ›** or the `[` and `]` keys to flip through the cameras currently shown, and **Esc** to close. The feed stops as soon as you close or switch cameras.

**Picture quality:** by default the map only shows cameras measured at 720p or better, so everything you open fills the viewer. This needs scan results (`python -m src.feeds.scan --category traffic`, then rebuild the map). Cameras whose size is unknown, like New Taipei's city viewers, are included unless you untick that option. Change the starting filter with `python -m src.map --min-height 1080` (or `480`, or `0` for everything).

### Check camera quality

```bash
python -m src.feeds.scan --region new-taipei    # New Taipei area (includes Taipei City)
python -m src.feeds.scan --category traffic     # all road cameras
python -m src.feeds.scan --sample 200           # random 200 from everything
```

Connects to each camera for a few seconds and records whether it's online, its resolution, frame rate and response time, then ranks them. Results go to `data/camera_quality.json` and `data/camera_quality.csv` (opens in Excel). No footage is saved. Regions: `new-taipei`, `keelung`, `taoyuan`, `taichung`, `tainan`, `kaohsiung`.

### Optional: TDX

TDX covers every city, but needs a free account. Put your keys in `.env` (copy `.env.example`), then:

```bash
python -m src.feeds.tdx_auth                          # check your keys work
python -m src.feeds.cameras --source tdx              # TDX only
python -m src.feeds.cameras --source tdx --city NewTaipei Taoyuan
python -m src.feeds.cameras --source all              # open data + TDX
```

### Camera record format

```json
{
  "id": "keelung:T000002",
  "source": "keelung",
  "category": "traffic",
  "road": "國道3號",
  "direction": "N",
  "description": "基金一路 基金交流道下匝道",
  "lat": 25.13972,
  "lon": 121.71492,
  "stream_url": "https://CCTV.KLCG.GOV.TW:443/9cc4ca1c",
  "url_type": "stream",
  "refresh_rate": null
}
```

`url_type` is `stream` (video/MJPEG), `image` (a still that refreshes), `page` (a web page that embeds the camera) or `viewer`.

`viewer` cameras (New Taipei) come from a dataset with locations but no stream links, so each links to the city's official live-traffic viewer page. They're for opening in a browser; the scanner and any automated analysis skip them. Analysing New Taipei's video automatically would need the official TDX feed.

### Note on Python 3.13+

Many Taiwan government sites use certificates that newer Python rejects as "Missing Subject Key Identifier". `src/feeds/http.py` relaxes only that extra strictness check. Certificates and hostnames are still fully verified.

## Roadmap

- [x] Phase 1a: camera lists from open data (and optionally TDX)
- [x] Phase 1b: camera quality scanner
- [x] Phase 1c: camera map
- [ ] Phase 2: run object detection on selected feeds and store counts
- [ ] Phase 3: detect anomalies (sudden drops or spikes)
- [ ] Phase 4: natural-language queries over the data
