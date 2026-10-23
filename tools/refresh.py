"""Weekly refresh for the Route Studio website (run by .github/workflows/refresh.yml, or by hand).
Downloads the NaPTAN stops and the operator's BODS timetables, and rebuilds naptan/ and bods/.
Settings are in config.json: operator (as named in BODS), regions (BODS regional GTFS files; "all" checks every region)."""
import json, os, shutil, subprocess, sys, urllib.request, zipfile, io, csv
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); T = os.path.join(ROOT, "tools"); W = os.path.join(ROOT, ".work")
cfg = json.load(open(os.path.join(ROOT, "config.json")))
ALL = ["east_anglia", "east_midlands", "london", "north_east", "north_west", "scotland", "south_east", "south_west", "wales", "west_midlands", "yorkshire"]
os.makedirs(W, exist_ok=True)
def get(url, path):
    print("download", url, flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "route-studio-refresh"})
    with urllib.request.urlopen(req, timeout=900) as r, open(path, "wb") as f: shutil.copyfileobj(r, f, 1 << 20)
    return path
run = lambda *a: subprocess.run([sys.executable, *a], check=True)

# NaPTAN: every stop, split by area
stops = get("https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv", os.path.join(W, "Stops.csv"))
shutil.rmtree(os.path.join(ROOT, "naptan"), ignore_errors=True)
run(os.path.join(T, "naptan_areas.py"), stops, os.path.join(ROOT, "naptan"))

# BODS timetables for the operator
regions = ALL if cfg.get("regions") == "all" else cfg["regions"]
out = os.path.join(W, "bods"); shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
found = []
for r in regions:
    z = get(f"https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/{r}/", os.path.join(W, f"{r}.zip"))
    names = [a["agency_name"].strip().lower() for a in csv.DictReader(io.TextIOWrapper(zipfile.ZipFile(z).open("agency.txt"), encoding="utf-8-sig"))]
    if cfg["operator"].lower() in names:
        run(os.path.join(T, "bods_extract.py"), z, stops, out, r, cfg["operator"])
        run(os.path.join(T, "bods_paths.py"), z, os.path.join(out, f"paths-{r}.json"), cfg["operator"])
        found.append(r)
    os.remove(z)
if not found: sys.exit(f"{cfg['operator']} wasn't found in any BODS region")
run(os.path.join(T, "bods_merge.py"), out, *found)
dst = os.path.join(ROOT, "bods"); shutil.rmtree(dst, ignore_errors=True); os.makedirs(dst)
for f in os.listdir(out):
    if not f.startswith(("index-", "paths-")): shutil.copy(os.path.join(out, f), dst)
if cfg.get("regions") == "all": print("regions with this operator:", found)
