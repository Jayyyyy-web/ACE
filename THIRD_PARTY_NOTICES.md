# Third-party notices

ACE uses data and conventions from the projects and agencies below. Their
licences and terms apply to their material, not to ACE's own code.

## OpenTrafficCamMap — MIT License

- Project: https://github.com/AidanWelch/OpenTrafficCamMap
- Copyright (c) 2020 AidanWelch
- Used for: the US camera list (downloaded by `src/feeds/otcm.py` at run time)
  and the camera record conventions in `src/feeds/formats.py` (country,
  region, county, encoding, format, update rate).
- Full licence text: [`licenses/OpenTrafficCamMap-MIT.txt`](licenses/OpenTrafficCamMap-MIT.txt)

```
MIT License

Copyright (c) 2020 AidanWelch

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Ora — PolyForm Noncommercial License 1.0.0

- Project: https://github.com/warner-wvez/Ora
- Required Notice: Copyright (c) 2026 Warner Varnado (https://warner-wvez.github.io/Ora/)
- Used for: the list of US state DOT live-video streams (downloaded by
  `src/feeds/ora.py` at run time, not copied into this repo). ACE uses only
  the states Ora marks as playing openly, and skips states whose streams are
  locked to the agency's own site.
- Licence terms: personal and other non-commercial use only. ACE is a personal,
  non-commercial project. Anyone reusing ACE commercially must remove the Ora
  source or get permission from its author.
- Full licence text: [`licenses/Ora-PolyForm-Noncommercial.txt`](licenses/Ora-PolyForm-Noncommercial.txt)

## Live-Environment-Streams — CC BY 4.0

- Project: https://github.com/william-ricchiuti/Live-Environment-Streams
- By William Ricchiuti; data licensed under Creative Commons Attribution 4.0
  International. Attribution: "Camera list: Live-Environment-Streams by
  William Ricchiuti (CC BY 4.0)". ACE converts it to its own record format
  and keeps only live video (HLS, MJPEG) with a real location.
- Used for: road-authority live video in Norway, Thailand, Indonesia and the
  US (downloaded by `src/feeds/les.py` at run time and cached locally, not
  copied into this repo). Its maintainers review each source's terms
  (SOURCES-REVIEW.md in that repo) and list only cleared sources.
- Each camera keeps the credit its operator asks for (shown as its publisher
  in the map), for example "Statens vegvesen (NLOD)" for Norway's cameras
  (Norwegian Licence for Open Government Data, https://data.norge.no/nlod/en),
  Caltrans (public domain), Iowa DOT (CC BY 4.0) and the State of Maryland.
- Full licence text: [`licenses/Live-Environment-Streams-CC-BY-4.0.txt`](licenses/Live-Environment-Streams-CC-BY-4.0.txt)

## Argus — MIT License

- Project: https://github.com/GoSlowPoke168/Argus
- Copyright (c) 2026 Jeremy Hou
- Used for: a worldwide list of public camera streams (downloaded by
  `src/feeds/argus.py` at run time and cached locally, not copied into this
  repo). ACE keeps only live video from an explicit allowlist of official
  government and transport-agency publishers, each verified by the stream's
  own domain. Commercial webcams, TV stations, bare-IP and dynamic-DNS hosts
  are excluded.
- Full licence text: [`licenses/Argus-MIT.txt`](licenses/Argus-MIT.txt)

## open-webcam-atlas — MIT License

- Project: https://github.com/jaydenbarnescs-tech/open-webcam-atlas
- Copyright (c) 2026 Jayden Barnes
- Used for: Krasnoyarsk city cameras and YouTube live-stream embeds
  (downloaded by `src/feeds/owa.py` at run time and cached locally).
- Full licence text: [`licenses/open-webcam-atlas-MIT.txt`](licenses/open-webcam-atlas-MIT.txt)

## Krasnoyarsk city cameras — CC BY-SA

- Source: cam.krk.ru (Krasnoyarsk, Russia; run by Orion Telecom), listed by
  open-webcam-atlas as CC BY-SA. Attribution: "Cameras: cam.krk.ru". ACE
  only links to the streams and stores no footage. The site's robots.txt
  asks automated tools not to use its `/api/`, so ACE never calls it: the
  stream list comes from open-webcam-atlas, and the streams are played
  only where the stream server itself allows it.

## YouTube live streams

- Taiwan's Tourism Administration cameras, Kyoto's official tourism cameras
  and public live streams tagged on OpenStreetMap play only through YouTube's
  own embed player, as YouTube's Terms of Service allow. ACE never downloads,
  records or analyses YouTube video, and drops videos YouTube reports as
  unavailable or not embeddable (checked with YouTube's public oEmbed
  endpoint).

## Taiwan Tourism Administration live cameras

- Source: the official list at https://www.taiwan.net.tw/m1.aspx?sNo=0042331
  (交通部觀光署, Tourism Administration, MOTC). The streams belong to the
  national scenic area administrations and city and county governments that
  run them, credited on each camera as its publisher.
- ACE reads the list at run time (the site's robots.txt allows it) and keeps
  only each camera's name, county, provider, location and YouTube video ID.
  It copies none of the site's text or photos, stores nothing in this repo,
  and links each camera back to its official page.

## Government open data

- **Taiwan** camera lists: data.gov.tw, Open Government Data License, version 1
  (https://data.gov.tw/license). This includes Taichung City's live traffic
  cameras (臺中市交通即時道路影像, dataset 83750, Taichung City Government).
  ACE reads each Taichung camera's stream address
  from the camera page the dataset links to, and links back to that page.
- **Taiwan provincial highways:** 資料來源：交通部公路局 (Source: Highway
  Bureau, MOTC), from its open-data site https://thbapp.thb.gov.tw/opendata/
  (CCTV list `cctvs.xml`, MOTC real-time traffic data standard v2.0). The
  bureau's terms for this data: it is free to download and use; anyone
  passing it on, as is or value-added, must state that the original source
  is the Highway Bureau; data may not be downloaded more often than every
  60 seconds; and it may not be used in any way that breaks Taiwan's laws.
  ACE credits the bureau on every camera and caches the list for a day.
- **Singapore** traffic images: Land Transport Authority via data.gov.sg,
  Singapore Open Data Licence (https://data.gov.sg/open-data-licence).
- **United States (optional `saat` source):** department-of-transportation
  camera feeds — SCDOT, VDOT, DDOT, Maryland SHA and Montgomery County —
  whose compiled list comes from https://github.com/baywolf88/seeallthethings
  (no stated licence; last updated 2018). ACE imports only those DOT feeds and
  excludes that list's references to private/unsecured cameras (Insecam,
  Shodan). The underlying feeds belong to the transport agencies.
- Live streams imported through Argus belong to their publishers: Seoul
  TOPIS, Busan, Ulsan, Daegu, Pohang, Changwon, Gwangju, Ansan and Chungju
  ITS, and Sejong City's Sejong-N smart-city portal (South Korea);
  Yogyakarta City, Bantul, Tangerang, Bandung, Tasikmalaya, Bondowoso and
  Asahan local governments and Jasa Marga (Indonesia); the Japan Coast
  Guard (MLIT); Macau DSAT; Istanbul Metropolitan Municipality; TASK, the
  academic computer centre of Gdańsk University of Technology (Poland);
  Taiwan's Freeway Bureau; and US agencies including Virginia DOT,
  Arlington County, the New Jersey Turnpike Authority and Prince George's
  County.
- Camera images and video stay the property of the agencies that publish
  them. ACE links to them and does not store or redistribute footage.

## Libraries and map tiles

- Leaflet (BSD-2-Clause) and Leaflet.markercluster (MIT), loaded from cdnjs.
- hls.js (Apache-2.0), loaded from cdnjs.
- Basemap tiles: Esri, HERE, Garmin, © OpenStreetMap contributors.
