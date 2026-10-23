"""Pre-built map data for every area the operator's buses run in, from an OpenStreetMap extract (.osm.pbf).

Usage: python3 build_tiles.py <extract.osm.pbf> <bods/paths.json> <out mapdata dir> [margin cells]

The map is cut into 0.25° squares (the same grid the website uses for live OpenStreetMap downloads).
Every square within <margin> squares (default 2, enough for the space a map shows around its stops) of a stop on any route gets mapdata/cell_<i>_<j>.json in the
builder's compact format (made by pack_mapdata.py), and mapdata/index.json lists them with their cell number,
so the page loads only the squares a map needs. Squares nobody needs aren't built.
"""
import json, os, subprocess, sys, tempfile
from collections import defaultdict
import osmium

PBF, PATHS, OUT = sys.argv[1:4]
MARGIN = int(sys.argv[4]) if len(sys.argv) > 4 else 2
CELL = 0.25
HERE = os.path.dirname(os.path.abspath(__file__))
HW = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential'}
BUILT = {'residential', 'commercial', 'retail', 'industrial'}
cell_of = lambda lon, lat: (int(lat // CELL), int(lon // CELL))

# the squares to build: around every stop the operator's routes call at
want = set()
for pats in json.load(open(PATHS))["routes"].values():
    for p in pats:
        for _, lon, lat in p["stops"]:
            i, j = cell_of(lon, lat)
            for di in range(-MARGIN, MARGIN + 1):
                for dj in range(-MARGIN, MARGIN + 1): want.add((i + di, j + dj))
print(len(want), "squares to build", flush=True)

def area_tags(t):
    return t.get('natural') == 'water' or t.get('landuse') in BUILT or t.get('boundary') in ('protected_area', 'national_park')
def way_wanted(t):
    hw = t.get('highway', '').replace('_link', '')
    return hw in HW or t.get('waterway') == 'river' or t.get('railway') == 'rail' or area_tags(t)

class Rels(osmium.SimpleHandler):
    """pass 1: multipolygon areas (lakes, national landscapes, big built-up areas) and the ways they're made of"""
    def __init__(s): super().__init__(); s.rels = []; s.member_ways = set()
    def relation(s, r):
        t = dict(r.tags)
        if t.get('type') in ('multipolygon', 'boundary') and area_tags(t):
            m = [(x.ref, x.role) for x in r.members if x.type == 'w']
            s.rels.append((r.id, t, m)); s.member_ways.update(ref for ref, _ in m)

class Elements(osmium.SimpleHandler):
    """pass 2: places, stations and ways with their geometry, filed under every wanted square they touch"""
    def __init__(s, member_ways):
        super().__init__(); s.cells = defaultdict(list); s.member_ways = member_ways; s.member_geo = {}
    def node(s, n):
        t = n.tags
        if not (t.get('place') in ('city', 'town', 'village', 'suburb', 'hamlet') or t.get('railway') == 'station'): return
        if not n.location.valid(): return
        c = cell_of(n.location.lon, n.location.lat)
        if c in want: s.cells[c].append({'type': 'node', 'id': n.id, 'lat': n.location.lat, 'lon': n.location.lon, 'tags': dict(t)})
    def way(s, w):
        mem = w.id in s.member_ways; t = dict(w.tags) if (mem or way_wanted(w.tags)) else None
        if t is None: return
        try: g = [(x.lon, x.lat) for x in w.nodes if x.location.valid()]; ids = [x.ref for x in w.nodes]
        except osmium.InvalidLocationError: return
        if len(g) < 2: return
        if mem: s.member_geo[w.id] = g
        if not way_wanted(t): return
        cs = {cell_of(lon, lat) for lon, lat in g} & want
        if not cs: return
        el = {'type': 'way', 'id': w.id, 'nodes': ids, 'tags': t, 'geometry': [{'lat': la, 'lon': lo} for lo, la in g]}
        for c in cs: s.cells[c].append(el)

src = PBF
if subprocess.run(["which", "osmium"], capture_output=True).returncode == 0:
    # osmium-tool (on the GitHub runner) cuts the country file down to the map features first, which is much faster
    src = os.path.join(tempfile.gettempdir(), "mapfeatures.osm.pbf")
    subprocess.run(["osmium", "tags-filter", PBF, "-o", src, "--overwrite",
                    "w/highway=motorway,motorway_link,trunk,trunk_link,primary,primary_link,secondary,secondary_link,tertiary,tertiary_link,unclassified,residential",
                    "w/waterway=river", "nwr/natural=water", "w/railway=rail", "n/railway=station", "n/place=city,town,village,suburb,hamlet",
                    "nwr/landuse=residential,commercial,retail,industrial", "nwr/boundary=protected_area,national_park"], check=True)
    print("filtered", round(os.path.getsize(src) / 1e6), "MB", flush=True)

R = Rels(); R.apply_file(src)
E = Elements(R.member_ways); E.apply_file(src, locations=True, idx="flex_mem")
for rid, t, members in R.rels:
    mem = [{'type': 'way', 'ref': ref, 'role': role, 'geometry': [{'lat': la, 'lon': lo} for lo, la in E.member_geo.get(ref, [])]} for ref, role in members]
    cs = {cell_of(p['lon'], p['lat']) for m in mem for p in m['geometry']} & want
    el = {'type': 'relation', 'id': rid, 'tags': t, 'members': mem}
    for c in cs: E.cells[c].append(el)

os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.startswith("cell_"): os.remove(os.path.join(OUT, f))
tiles = []
with tempfile.TemporaryDirectory() as tmp:
    for (i, j) in sorted(want):
        els = E.cells.get((i, j), []); fn = f"cell_{i}_{j}.json"
        if not els:   # open sea or empty country: still listed, so the page knows there's nothing to download
            json.dump({"v": 1, "name": "OpenStreetMap", "bbox": [i * CELL, j * CELL, (i + 1) * CELL, (j + 1) * CELL], "roads": [], "rivers": [], "rails": [],
                       "areas": [], "places": [], "stations": []}, open(os.path.join(OUT, fn), "w"), separators=(",", ":"))
        else:
            src_json = os.path.join(tmp, "cell.json")
            json.dump({'elements': els}, open(src_json, "w"))
            subprocess.run([sys.executable, os.path.join(HERE, "pack_mapdata.py"), src_json, os.path.join(OUT, fn), "OpenStreetMap"], check=True, capture_output=True)
        tiles.append({"file": fn, "name": "OpenStreetMap", "cell": [i, j], "bbox": [i * CELL, j * CELL, (i + 1) * CELL, (j + 1) * CELL]})
json.dump({"v": 2, "cell": CELL, "tiles": tiles}, open(os.path.join(OUT, "index.json"), "w"), separators=(",", ":"))
print(len(tiles), "squares built,", round(sum(os.path.getsize(os.path.join(OUT, t["file"])) for t in tiles) / 1e6, 1), "MB")
