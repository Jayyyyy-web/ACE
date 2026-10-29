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
pip install -r requirements.txt
cp .env.example .env            # then add your TDX keys
```

## Usage

```bash
python -m src.feeds.tdx_auth             # check your TDX keys work
python -m src.feeds.cameras              # fetch every camera in Taiwan -> data/cameras.json
python -m src.feeds.cameras NewTaipei    # or just one or more cities
```

## Roadmap

- [ ] Phase 1: authenticate with TDX and map every camera
- [ ] Phase 2: run object detection on selected feeds and store counts
- [ ] Phase 3: detect anomalies (sudden drops or spikes)
- [ ] Phase 4: natural-language queries over the data
