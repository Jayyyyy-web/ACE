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

## Government open data

- **Taiwan** camera lists: data.gov.tw, Open Government Data License, version 1
  (https://data.gov.tw/license).
- **Singapore** traffic images: Land Transport Authority via data.gov.sg,
  Singapore Open Data Licence (https://data.gov.sg/open-data-licence).
- Camera images and video stay the property of the agencies that publish
  them. ACE links to them and does not store or redistribute footage.

## Libraries and map tiles

- Leaflet (BSD-2-Clause) and Leaflet.markercluster (MIT), loaded from cdnjs.
- hls.js (Apache-2.0), loaded from cdnjs.
- Basemap tiles: Esri, HERE, Garmin, © OpenStreetMap contributors.
