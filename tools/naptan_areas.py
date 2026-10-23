"""Split the national NaPTAN Stops.csv into one small file per ATCO area, so Route Studio can find any stop in
England, Scotland and Wales by NaPTAN code or by town and stop name without loading the whole country.
Usage: python3 naptan_areas.py Stops.csv <out dir>   → <out>/<area>.json + <out>/index.json
Rows: [atco, CommonName, Indicator, Landmark, Street, LocalityName, ParentLocalityName, GrandParentLocalityName, Town, Suburb, lon, lat, StopType]"""
import csv, json, os, sys
from collections import defaultdict
src, out = sys.argv[1:3]; os.makedirs(out, exist_ok=True)
F = ['ATCOCode', 'CommonName', 'Indicator', 'Landmark', 'Street', 'LocalityName', 'ParentLocalityName', 'GrandParentLocalityName', 'Town', 'Suburb']
areas = defaultdict(list)
for r in csv.DictReader(open(src, encoding='utf-8-sig')):
    if (r.get('Status') or 'active').lower() != 'active': continue
    try: lon, lat = float(r['Longitude']), float(r['Latitude'])
    except ValueError: continue
    areas[r['ATCOCode'][:3]].append([r[f] or '' for f in F] + [round(lon, 6), round(lat, 6), r.get('StopType') or ''])
index = []
for code, rows in sorted(areas.items()):
    fn = f"{code}.json"
    json.dump({'v': 1, 'fields': F + ['lon', 'lat', 'type'], 'rows': rows}, open(f"{out}/{fn}", 'w'), separators=(',', ':'), ensure_ascii=False)
    lats = [x[11] for x in rows]; lons = [x[10] for x in rows]
    locs = sorted({x[5] for x in rows if x[5]} | {x[6] for x in rows if x[6]} | {x[8] for x in rows if x[8]})
    index.append({'code': code, 'file': fn, 'stops': len(rows), 'bbox': [min(lats), min(lons), max(lats), max(lons)], 'places': locs})
json.dump({'v': 1, 'areas': index}, open(f"{out}/index.json", 'w'), separators=(',', ':'), ensure_ascii=False)
print(len(index), 'areas,', sum(a['stops'] for a in index), 'stops')
