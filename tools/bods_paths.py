"""Every stop each route calls at (not just timing points), for drawing accurate route lines.
Central Connect's BODS data has no route shapes, so the map routes along the roads through all of these stops.
Usage: python3 bods_paths.py <gtfs.zip> <out/paths-region.json> [agency name]  (bods_merge.py joins the regions)
Output: {"v":1,"routes":{"82":[{"n":trips,"stops":[[atco,lon,lat],...]}, ...]}} — the stopping patterns, most used first."""
import csv, io, json, sys, zipfile
from collections import Counter, defaultdict
GTFS, OUT = sys.argv[1], sys.argv[2]; AGENCY = sys.argv[3] if len(sys.argv) > 3 else "Central Connect"
z = zipfile.ZipFile(GTFS); rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8-sig"))
aid = {a["agency_id"] for a in rd("agency.txt") if a["agency_name"].strip().lower() == AGENCY.lower()}
routes = {r["route_id"]: r["route_short_name"].strip() for r in rd("routes.txt") if r["agency_id"] in aid}
trips = {t["trip_id"]: routes[t["route_id"]] for t in rd("trips.txt") if t["route_id"] in routes}
seq = defaultdict(list)
for r in rd("stop_times.txt"):
    if r["trip_id"] in trips: seq[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"]))
pat = defaultdict(Counter)
for t, s in seq.items(): pat[trips[t]][tuple(x for _, x in sorted(s))] += 1
need = {x for c in pat.values() for p in c for x in p}
pos = {s["stop_id"]: (round(float(s["stop_lon"]), 6), round(float(s["stop_lat"]), 6)) for s in rd("stops.txt") if s["stop_id"] in need}
out = {}
for rt, c in pat.items():
    ps = []
    for p, n in c.most_common():
        # skip patterns that are just part of a longer one already kept
        if any(" ".join(p) in " ".join(q["k"]) for q in ps): continue
        ps.append({"n": n, "k": p})
        if len(ps) >= 8: break
    out[rt] = [{"n": q["n"], "stops": [[a, *pos[a]] for a in q["k"] if a in pos]} for q in ps]
json.dump({"v": 1, "routes": out}, open(OUT, "w"), separators=(",", ":"))
print(len(out), "routes,", sum(len(v) for v in out.values()), "patterns")
