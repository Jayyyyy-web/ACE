# ACE

A personal project that finds **proper live cameras** (official public cameras whose video is live, sharp, smooth and close to real time), shows them on a map, and next uses computer vision to analyse traffic: vehicle and pedestrian counts, congestion, and unusual events.

Scope: anonymous, aggregate analysis only. No identification or tracking of individual people or vehicles.

## Structure

- `src/find.py` – finds and tests the proper cameras
- `src/feeds/` – camera list fetching, quality testing, shared formats
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

## Start here: proper cameras

No account or API key needed.

```bash
python -m src.find     # find and test the proper cameras (about 10-20 minutes the first time)
python -m src.map      # see them on the map
```

**What "proper" means.** Every camera is tested from your own computer before it's kept:

| Test | Default | Change it |
|---|---|---|
| **Live**: new pictures keep arriving; nothing frozen, still or pre-recorded | always | |
| **Sharp**: picture size, read from the video itself | 1280×720 or better | `--min-height 1080` (Full HD only) or `480` |
| **Smooth**: frames per second | at least 2 | `--min-fps 0` allows slideshows |
| **Close to real time** | at most 15 s behind | `--max-delay 10`, `--max-delay 25` |
| **Plays in the map**: the server lets other sites play its video (CORS), in H.264 | always | |

Only cameras that pass go to `data/proper_cameras.json`, and the map then shows only those (`python -m src.map --all` shows the old, much bigger list). `data/find_report.csv` (opens in Excel) lists every camera tested and why any failed. Cameras found too small are skipped for a week so later runs are quicker (`--retest` checks them again). No video is saved.

**How live is live?** MJPEG video (blue pins) sends each picture the moment it's taken, so it's real time. HLS video (pink pins) arrives in chunks, and the map plays it about one and a half chunks plus a few seconds behind, so servers that send short chunks are the most live. The finder works out each camera's delay from its chunk length, how old its newest video is, and how fast a chunk downloads. Checked against cameras' on-screen clocks, that estimate was right to within a few seconds.

**Results depend on your connection.** Some servers only answer some countries, and a slow link lowers MJPEG frame rates and makes HLS fall behind. That's why the finder runs on your computer rather than shipping a fixed list. A server that refuses or ignores its first few cameras is skipped for the rest of the run, so nothing hangs on it; the finder prints which ones.

### Where the finder looks

`python -m src.find --list` shows the groups; pick some with `--group`, or single sources with `--source`.

| Group | Sources | On by default |
|---|---|---|
| `taiwan` | Taichung, Keelung, Tainan, Chiayi City and County (live MJPEG from data.gov.tw) | yes |
| `indonesia` | Bantul, Yogyakarta City, Tasikmalaya, Bandung, Tangerang, Asahan, Jasa Marga toll roads | yes |
| `korea` | Sejong (new), Ansan, Seoul, Busan, Ulsan, Daegu, Pohang, Changwon, Gwangju, Chungju | yes |
| `krasnoyarsk` | Krasnoyarsk city cameras (cam.krk.ru, run by Orion Telecom) | yes |
| `poland` | Gdańsk, Gdynia and Sopot city and seaside cameras (TASK, Gdańsk University of Technology) (new) | yes |
| `istanbul` | Istanbul Metropolitan Municipality | yes |
| `us` | US state transport departments (about 13,000 cameras) | no: nearly all are below 720p or 15–30 s behind, and testing them takes hours |
| `other` | Taiwan freeways and provincial highways, Japan Coast Guard, Macau: all official, all below 720p | no |

### What the survey found (November 2026)

Before the finder was written, samples from every source were tested from ACE's test environment, outside Asia. Your numbers will differ, mostly for the better in Taiwan.

| Source | What was measured |
|---|---|
| **Taichung** (Taiwan) | 310 of 315 live, real time. 61 at 720p or better (13 at 1080p). Frame rates from overseas were 1–9 a second on the HD cameras, so only 11–15 passed the 2-a-second test from there; nearer Taichung they should be higher. |
| **Keelung** (Taiwan) | 52 of 60 live, 5 at 720p, 2–5 frames a second. |
| **Bantul** (Indonesia) | The best find: 29 of 39 cameras live in HD (16 at 1080p), 25 frames a second, 2-second chunks. Their on-screen clocks showed the map playing them **7–9 seconds** behind real time. |
| **Sejong** (Korea) | 25–28 of 45 passed in each run, nearly all 1080p at 25 frames a second, in 3-second chunks: about 8 s behind (estimated). The city's own Sejong-N portal (smart.sejong.go.kr) streams them. |
| **Gdańsk, Gdynia, Sopot** (Poland) | 5 of 6 passed: 1080p (one 2560×1440), 25 frames a second, 6-second chunks: about 12 s behind (estimated). |
| **Yogyakarta City** (Indonesia) | Sharp (720p and 1080p, 25 frames a second) but 11-second chunks: 23–36 s behind by their clocks, so it misses the default bar. Try `--max-delay 40`. |
| Other Korean cities | Mostly 640×480 to 720×480 in 10–12-second chunks (about 20 s behind). Seoul, Busan, Ulsan, Ansan (labelled Full HD) and Chungju didn't answer the test environment; they may answer you. |
| **Krasnoyarsk** (Orion Telecom) | Sharp (1080p, 20–30 frames a second), but its server sends 15–17-second chunks, so even the map's faster player runs it about 25–35 s behind: it misses the default bar, and `--max-delay 40` keeps it. Most of its cameras refused the test environment (HTTP 403); they may answer you. |
| US state DOTs | Mostly 320×240 to 720×480. The HD ones use long chunks (Delaware 17 s, Mississippi 11 s): 20–30 s behind. |

**Left out, and why.** Some sharp, fairly live webcams were found but aren't used: ones run by internet providers or companies (in Mezhdurechensk, the Czech Ore Mountains, Kyrgyzstan, Astrakhan, Harlingen), because they carry no open licence and are meant for the companies' own sites; and some streamed from Wowza cloud addresses (for example Geoje in Korea, Istanbul's larger set), because the stream's address doesn't show who runs it. Some streams would never play in the map anyway, because their servers block other sites (Mezhdurechensk, Tangerang, the Japan Coast Guard). Yogyakarta Province's 543 links are dead. Taipei City needs a licence agreement, Kaohsiung and Taoyuan don't allow automated access, and TDX needs an account.

## The full camera list

Before the restart around proper cameras, ACE gathered every public camera it could find, about 29,000 of them, most of them still pictures, small or delayed. All of that still works and is described below; the map shows it with `python -m src.map --all`.

```bash
python -m src.feeds.cameras                      # every default source -> data/cameras.json
python -m src.feeds.cameras --source argus owa   # the worldwide live sources only
python -m src.feeds.cameras --source ora         # US live video (Ora) only
python -m src.feeds.cameras --source opendata twtourism   # Taiwan only
python -m src.feeds.cameras --source otcm        # US only
python -m src.feeds.cameras --source sgp         # Singapore only
python -m src.feeds.cameras --category traffic   # Taiwan road cameras only (US is all road cameras)
```

Besides the flat `data/cameras.json`, a copy per country is written to `data/cameras/<COUNTRY>.json` in OpenTrafficCamMap's nested layout (region → county → cameras).

### Sources

**Taiwan** — government open data from data.gov.tw (Open Government Data License v1), plus the Highway Bureau's own open-data site:

| Source | Category | Dataset |
|---|---|---|
| Freeway Bureau (national freeways) | traffic | [37665](https://data.gov.tw/dataset/37665) |
| **Taichung City — HD live video** | traffic | [83750](https://data.gov.tw/dataset/83750) |
| Highway Bureau (provincial highways) | traffic | [交通資料庫](https://thbapp.thb.gov.tw/opendata/) (`cctvs.xml`) |
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

**Taichung** has the sharpest road cameras in Taiwan that need no account: 315 live MJPEG streams from the city's own video servers. In a November 2026 scan all 315 were online and 61 were 720p or better (13 at 1920×1080, the best at about 9 fps); most of the rest are 640×360 to 720×576. The dataset links each camera to a small page on the city's traffic site rather than to the video, so ACE reads the stream address from every page (cached for a week) and stores the stream itself, which the scanner, the map and later the AI can use directly. The page stays linked as the camera's **Official page**.

**Highway Bureau** (交通部公路局): 2,356 provincial-highway cameras, published on the bureau's own [open-data site](https://thbapp.thb.gov.tw/opendata/). Its terms ask users to state that the data comes from the Highway Bureau (ACE sets it as every camera's publisher, shown in the map) and not to download it more often than every 60 seconds (ACE keeps its copy for a day). The streams are about 320×240, so once scanned the default 720p map filter hides them; pick a lower quality in the sidebar to see them. In browser tests, cameras whose stream address ends in a direction tag such as `(N)` (about 8% of them) wouldn't play inside the map; the rest did.

**Taiwan — Tourism Administration live cameras** (`twtourism`). The 114 official live cameras listed on the [Tourism Administration's site](https://www.taiwan.net.tw/m1.aspx?sNo=0042331), run by the national scenic area offices and city and county governments: Taipei 101 from Xiangshan, Dadaocheng Wharf, Tamsui, Jiufen, Yehliu, Gaomei Wetlands, all seven Sun Moon Lake cameras, Alishan, Penghu, Green Island, Kinmen, Matsu and more, mostly in HD. They are YouTube live streams, so they are **view-only**: they play in YouTube's embed player, and the scanner and any analysis skip them. ACE takes only each camera's name, county, provider, location and video ID, links back to its official page, and drops videos YouTube reports as unavailable. The list is cached for a day and each camera's page for a week.

Not included: Taipei City's road cameras (reusing them needs an application and a licence agreement with the city), and Kaohsiung's and Taoyuan's (their camera sites only serve Taiwan and don't allow automated access; the official machine-readable route is TDX, below). Datasets of police intersection cameras list locations only and aren't used.

**United States** — [OpenTrafficCamMap](https://github.com/AidanWelch/OpenTrafficCamMap) (MIT licence), a crowdsourced list of state DOT cameras: about 6,900 cameras across California, Ohio, Colorado, Indiana, Alabama, Alaska, Delaware, Kentucky, Arizona and Georgia. Its data was last updated in 2024, so some links are dead; the scanner finds which work. Cameras marked for review, at bad coordinates, or in agency-specific formats are skipped.

**United States — live video from [Ora](https://github.com/warner-wvez/Ora)** (PolyForm Noncommercial licence; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)). About 11,900 state DOT live HLS streams across 17 states (Colorado, Delaware, Hawaii, Iowa, Indiana, Louisiana, Maryland, Minnesota, Missouri, Mississippi, Nevada, New York, Oklahoma, South Carolina, Tennessee, Wisconsin, West Virginia). Only states whose agencies serve video openly are used; Florida, North Carolina, New Jersey, Pennsylvania and Texas lock their streams to their own sites and are skipped. Ora's offline/frozen cameras, snapshot-only views and bad coordinates are dropped. Where Ora and OpenTrafficCamMap list the same stream, Ora's newer record is kept.

**United States — optional `saat` source (off by default).** DOT feeds (SCDOT, VDOT, DDOT, Maryland SHA, Montgomery County) whose compiled list comes from [seeallthethings](https://github.com/baywolf88/seeallthethings). ACE imports only those government feeds and refuses that list's private/unsecured-camera references (Insecam, Shodan). The list is from 2018 and its links are now dead (expired tokens, retired camera IPs), so it is not fetched by default; enable it with `python -m src.feeds.cameras --source opendata otcm sgp saat` if you want it anyway.

**Worldwide official live video — [Argus](https://github.com/GoSlowPoke168/Argus)** (MIT). Argus lists about 229,000 cameras from many kinds of sources. ACE takes only live video (HLS/MJPEG) from an explicit allowlist of official publishers in `src/feeds/argus.py`, and only when the stream is served from that publisher's own domain: city ITS centres in South Korea (Seoul, Busan, Ulsan, Daegu, Pohang, Changwon, Gwangju, Ansan, Chungju), local governments and Jasa Marga toll roads in Indonesia, the Japan Coast Guard, Macau's DSAT, Istanbul's municipality, Taiwan's Freeway Bureau, and US agencies such as Virginia DOT, Arlington County and the New Jersey Turnpike Authority. Commercial webcam companies, TV stations, bare-IP and dynamic-DNS hosts are excluded, and two sources whose links had all gone dead (Yogyakarta Province, Thailand's ITIC) were dropped. About 13,800 streams after removing duplicates; the list is cached in `data/cache/` for a week.

**Krasnoyarsk and YouTube live — [open-webcam-atlas](https://github.com/jaydenbarnescs-tech/open-webcam-atlas)** (MIT). Adds Krasnoyarsk's 281 city cameras (cam.krk.ru, CC BY-SA) and YouTube live streams: Kyoto's 23 official tourism cameras plus public live streams tagged on OpenStreetMap. YouTube streams play only through YouTube's own embed player and are view-only (the scanner and any analysis skip them); each run checks YouTube's oEmbed endpoint and drops videos that are gone or not embeddable.

In browser tests, live video played from Bantul (1920×1080), Yogyakarta City (1280×720), Daegu, Pohang, Tasikmalaya, Bondowoso, Macau, Virginia and the NJ Turnpike. Some others (Seoul, Busan, Ulsan, the coast guard, Arlington, Krasnoyarsk) couldn't be reached from the test environment's network; run the scanner to see which work from yours.

**Singapore** — the Land Transport Authority's traffic images on [data.gov.sg](https://api.data.gov.sg/v1/transport/traffic-images), no key needed. Since about July 2026 this free API only serves 8 cameras (Woodlands Causeway, Tuas Second Link, Sentosa Gateway); the full ~90-camera network is only on LTA DataMall, which needs a registered key. All 8 are 1920×1080 stills refreshed about every 20 seconds. Each snapshot gets a new URL, so records keep the camera's `api_camera_id` and the map and scanner fetch the latest image from the API (format `UNIQUE_SINGAPORE_LTA`).

### Camera map

```bash
python -m src.map
```

Builds `data/map.html`, serves it on `http://localhost:8765` and opens it in your browser. Press **Ctrl+C** in the terminal to stop. (It's served rather than opened as a file because some camera servers, like California's live video, refuse requests from pages without a web address. The server only listens on your own computer.) Use `--no-serve` to open the file directly, or `--no-open` to just build it.

**Live video only** is on by default: the map shows cameras with moving video (MJPEG streams, HLS video and city video players). Untick it in the sidebar to also see still images and web pages, or start that way with `python -m src.map --include-stills`.

**Tested live only** is on once you've run the scanner (below): the map then shows only cameras the scanner found really live, meaning new video kept arriving and nothing was frozen, pre-recorded or a still picture. Untested places disappear until you scan them. YouTube streams and city viewers can't be tested, so they show only with this off (or start with `python -m src.map --untested`).

**How far behind real time:** MJPEG video (blue pins) is real time. HLS video (pink pins) is published in chunks, 2–17 seconds long on most of these cameras, so it always runs at least one chunk behind. hls.js normally starts three chunks back, which put many cameras 30–60 seconds behind; ACE's player sits one chunk plus 2 seconds behind instead. In tests that took California from about 30 s to 12 s behind, Virginia from 21 s to 8 s, New York from 15 s to 8 s and the New Jersey Turnpike from 7.5 s to 4 s, with no stutter. The scanner works out each camera's delay, and the map shows cameras up to 15 seconds behind by default. Pick **Real time** in the sidebar (or `--max-delay 5`) for MJPEG plus the fastest HLS only, or **Any delay** (`--max-delay 0`). The viewer shows a live readout such as "● live · 4 s behind".

Every camera is a pin, clustered by area and coloured by type, with search (road, place, state or ID), and filters by country, type and source. Each country has a **zoom** button.

Click a pin and the camera opens in a viewer that takes half the screen (the bottom half on a phone). Live video (MJPEG and HLS) plays directly; still images refresh automatically. Use **‹ Prev / Next ›** or the `[` and `]` keys to flip through the cameras currently shown, and **Esc** to close. The feed stops as soon as you close or switch cameras. **Open source ↗** opens the stream itself in a new tab at full size; **Official page ↗** (Taichung, Tourism Administration) opens the camera's page on the agency's own site.

**Picture quality:** by default the map only shows cameras measured at 720p or better, so everything you open fills the viewer. This needs scan results. Cameras whose size is unknown (not scanned yet, or New Taipei's city viewers) are included unless you untick that option. Change the starting filter with `python -m src.map --min-height 1080` (or `480`, or `0` for everything).

### Check camera quality

```bash
python -m src.feeds.scan --region new-taipei           # New Taipei area (includes Taipei City)
python -m src.feeds.scan --category traffic            # all road cameras (slow with US included)
python -m src.feeds.scan --country TWN                 # Taiwan only
python -m src.feeds.scan --source taichung             # Taichung's HD cameras (3–4 minutes)
python -m src.feeds.scan --source owa-krasnoyarsk      # Krasnoyarsk's Orion Telecom cameras
python -m src.feeds.scan --country USA --sample 300    # 300 random US cameras
python -m src.feeds.scan --country SGP                 # Singapore
```

Connects to each camera for a few seconds and tests whether it's really live: an MJPEG stream must send more than one different picture, and an HLS playlist must have added new video when read again a chunk later, and must not be a finished recording. Cameras that fail show as `frozen` or `recorded`. It also records resolution, frame rate and response time, plus each HLS camera's chunk length and about how far behind real time the map will play it, then ranks the live ones. For HLS video it downloads one chunk and reads the real picture size, codec and frame rate from the video itself (playlists often don't say, or say the wrong thing), and checks the server lets other sites play it (CORS). MJPEG cameras take about 5 seconds each, eight at a time: Taiwan's roughly 4,000 testable cameras take about 45 minutes, and the whole US list several hours, so try `--sample` first. Results go to `data/camera_quality.json` and `data/camera_quality.csv` (opens in Excel), merged with earlier scans so you can scan one country or area at a time. No footage is saved. Taiwan regions: `new-taipei`, `keelung`, `taoyuan`, `taichung`, `tainan`, `kaohsiung`.

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
| `youtube` | `YOUTUBE_EMBED` | a YouTube live stream, shown only through YouTube's embed player |

`MJPEG`, `WEB_PAGE` and `WEB_VIEWER` aren't in OpenTrafficCamMap's format list yet; its README says the list should be added to.

`viewer` cameras (New Taipei) come from a dataset with locations but no stream links, so each links to the city's official live-traffic viewer page. They're shown in the map viewer; the scanner and any automated analysis skip them. Analysing New Taipei's video automatically would need the official TDX feed.

### Note on Python 3.13+

Many Taiwan government sites use certificates that newer Python rejects as "Missing Subject Key Identifier". `src/feeds/http.py` relaxes only that extra strictness check. Certificates and hostnames are still fully verified.

## Credits

- US live-video stream list: [Ora](https://github.com/warner-wvez/Ora), Copyright (c) 2026 Warner Varnado, PolyForm Noncommercial 1.0.0. Full text in [`licenses/Ora-PolyForm-Noncommercial.txt`](licenses/Ora-PolyForm-Noncommercial.txt).
- US camera list and record conventions: [OpenTrafficCamMap](https://github.com/AidanWelch/OpenTrafficCamMap), Copyright (c) 2020 AidanWelch, MIT licence. Full text in [`licenses/OpenTrafficCamMap-MIT.txt`](licenses/OpenTrafficCamMap-MIT.txt).
- Worldwide official live streams: [Argus](https://github.com/GoSlowPoke168/Argus), Copyright (c) 2026 Jeremy Hou, MIT licence ([`licenses/Argus-MIT.txt`](licenses/Argus-MIT.txt)); the streams belong to their publishing agencies, including Bantul Regency and Yogyakarta City (Indonesia), Sejong City's Sejong-N portal and other Korean city traffic centres, and TASK at Gdańsk University of Technology (Poland).
- Krasnoyarsk cameras and YouTube live list: [open-webcam-atlas](https://github.com/jaydenbarnescs-tech/open-webcam-atlas), Copyright (c) 2026 Jayden Barnes, MIT licence ([`licenses/open-webcam-atlas-MIT.txt`](licenses/open-webcam-atlas-MIT.txt)); Krasnoyarsk cameras: cam.krk.ru, CC BY-SA.
- Taiwan camera lists: data.gov.tw, Open Government Data License v1 (including Taichung City Government's live traffic cameras). Provincial-highway cameras: 資料來源：交通部公路局 (source: Highway Bureau, MOTC). Tourism live cameras: listed by the Tourism Administration, MOTC (交通部觀光署), streamed by the scenic area offices and local governments on YouTube.
- Singapore traffic images: Land Transport Authority via data.gov.sg, Singapore Open Data Licence.
- Basemap: Esri, HERE, Garmin, © OpenStreetMap contributors.

See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for all licences and terms.

## Roadmap

- [x] Phase 1a: camera lists from open data (and optionally TDX)
- [x] Phase 1b: camera quality scanner
- [x] Phase 1c: camera map
- [x] Phase 1d: OpenTrafficCamMap format + US cameras
- [x] Phase 1e: Singapore (free API: 8 cameras)
- [x] Phase 1f: US live video (Ora) and worldwide official live video (Argus, open-webcam-atlas)
- [x] Phase 1g: Taiwan HD: Taichung live video, Highway Bureau, Tourism Administration live cameras
- [x] Phase 1h: live test (frozen and pre-recorded streams caught, HLS delay measured) and near-real-time HLS playback
- [x] Phase 1i: restart from proper cameras: a finder that tests every camera (live, 720p+, smooth, close to real time, playable) and a map of only those; new sources Sejong (Korea) and Gdańsk (Poland)
- [ ] Phase 2: run object detection on selected feeds and store counts
- [ ] Phase 3: detect anomalies (sudden drops or spikes)
- [ ] Phase 4: natural-language queries over the data
