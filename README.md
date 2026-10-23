# Route Studio

Central Connect's builder for timetables, route maps, fare charts and bus guides. Everything runs in the browser: open `index.html` (or the GitHub Pages site) and nothing needs installing.

## Where the data comes from
- **Roads and places for maps:** OpenStreetMap, in 0.25° squares. `mapdata/` has every square around a stop on a Central Connect route, rebuilt weekly from Geofabrik's England extract. Anywhere else (a stops file for a new area), the browser downloads the missing squares live from the Overpass API and keeps them for 60 days.
- **Stop positions:** NaPTAN, split by area in `naptan/` (found by NaPTAN code, town and stop name).
- **Central Connect timetables:** BODS (Bus Open Data Service) regional GTFS, turned into the builder's own CSV format in `bods/`, with every stop each route calls at (`bods/paths.json`) so map lines follow the real route.

## Weekly refresh
`.github/workflows/refresh.yml` runs `tools/refresh.py` every Monday morning (and from the Actions tab › *Refresh timetables and stops* › *Run workflow*). It downloads NaPTAN, the BODS files listed in `config.json` and OpenStreetMap, rebuilds `naptan/`, `bods/` and `mapdata/`, and commits them; GitHub Pages then serves the new data.

`config.json`: `operator` is the name in BODS; `regions` are the BODS regions to read (`"all"` checks every region, which takes longer); `osm_extract` is the Geofabrik file for map data; `map_margin` is how many squares around each stop to build.
