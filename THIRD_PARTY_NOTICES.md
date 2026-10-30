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

## Government open data

- **Taiwan** camera lists: data.gov.tw, Open Government Data License, version 1
  (https://data.gov.tw/license).
- **Singapore** traffic images: Land Transport Authority via data.gov.sg,
  Singapore Open Data Licence (https://data.gov.sg/open-data-licence).
- **United States (optional `saat` source):** department-of-transportation
  camera feeds — SCDOT, VDOT, DDOT, Maryland SHA and Montgomery County —
  whose compiled list comes from https://github.com/baywolf88/seeallthethings
  (no stated licence; last updated 2018). ACE imports only those DOT feeds and
  excludes that list's references to private/unsecured cameras (Insecam,
  Shodan). The underlying feeds belong to the transport agencies.
- Camera images and video stay the property of the agencies that publish
  them. ACE links to them and does not store or redistribute footage.

## Libraries and map tiles

- Leaflet (BSD-2-Clause) and Leaflet.markercluster (MIT), loaded from cdnjs.
- hls.js (Apache-2.0), loaded from cdnjs.
- Basemap tiles: Esri, HERE, Garmin, © OpenStreetMap contributors.
