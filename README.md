# Route Studio

Central Connect's builder for timetables, route maps, fare charts and bus guides. Everything runs in the browser: open `index.html` (or the GitHub Pages site) and nothing needs installing.

## Where the data comes from
- **Roads and places for maps:** live from OpenStreetMap's Overpass API, for whatever area the stops are in, in 0.25° squares kept in the browser for 60 days. `mapdata/` holds a pre-built Colchester–Sudbury area used if Overpass can't be reached.
- **Stop positions:** NaPTAN, split by area in `naptan/` (found by NaPTAN code, town and stop name).
- **Central Connect timetables:** BODS (Bus Open Data Service) regional GTFS, turned into the builder's own CSV format in `bods/`, with every stop each route calls at (`bods/paths.json`) so map lines follow the real route.

## Weekly refresh
`.github/workflows/refresh.yml` runs `tools/refresh.py` every Monday morning (and from the Actions tab › *Refresh timetables and stops* › *Run workflow*). It downloads NaPTAN and the BODS files listed in `config.json`, rebuilds `naptan/` and `bods/`, and commits them; GitHub Pages then serves the new data.

`config.json`: `operator` is the name in BODS; `regions` are the BODS regions to read (`"all"` checks every region, which takes longer).
