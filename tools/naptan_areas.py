"""Split the national NaPTAN Stops.csv into one small file per ATCO area, so Route Studio can find any stop in
England, Scotland and Wales by NaPTAN code or by town and stop name without loading the whole country.
Usage: python3 naptan_areas.py Stops.csv <out dir>   → <out>/<area>.json + <out>/index.json
Rows: [atco, CommonName, Indicator, Landmark, Street, LocalityName, ParentLocalityName, GrandParentLocalityName, Town, Suburb, lon, lat, StopType]"""
import csv, json, os, sys
import math
def osgb_to_wgs84(E, N):
    """British National Grid easting/northing → WGS84 (lon, lat): OS transverse Mercator inverse, then a Helmert shift (±5 m)"""
    a, b, F0 = 6377563.396, 6356256.909, 0.9996012717; lat0, lon0, N0, E0 = math.radians(49), math.radians(-2), -100000, 400000
    e2 = 1 - (b * b) / (a * a); n = (a - b) / (a + b); lat, M = lat0, 0
    while True:
        lat = (N - N0 - M) / (a * F0) + lat
        Ma = (1 + n + 1.25 * n**2 + 1.25 * n**3) * (lat - lat0); Mb = (3 * n + 3 * n**2 + 2.625 * n**3) * math.sin(lat - lat0) * math.cos(lat + lat0)
        Mc = (1.875 * n**2 + 1.875 * n**3) * math.sin(2 * (lat - lat0)) * math.cos(2 * (lat + lat0)); Md = 35 / 24 * n**3 * math.sin(3 * (lat - lat0)) * math.cos(3 * (lat + lat0))
        M = b * F0 * (Ma - Mb + Mc - Md)
        if abs(N - N0 - M) < 1e-5: break
    s_ = math.sin(lat); nu = a * F0 / math.sqrt(1 - e2 * s_**2); rho = a * F0 * (1 - e2) / (1 - e2 * s_**2)**1.5; eta2 = nu / rho - 1
    t = math.tan(lat); sec = 1 / math.cos(lat); dE = E - E0
    VII = t / (2 * rho * nu); VIII = t / (24 * rho * nu**3) * (5 + 3 * t**2 + eta2 - 9 * t**2 * eta2); IX = t / (720 * rho * nu**5) * (61 + 90 * t**2 + 45 * t**4)
    X = sec / nu; XI = sec / (6 * nu**3) * (nu / rho + 2 * t**2); XII = sec / (120 * nu**5) * (5 + 28 * t**2 + 24 * t**4); XIIA = sec / (5040 * nu**7) * (61 + 662 * t**2 + 1320 * t**4 + 720 * t**6)
    phi = lat - VII * dE**2 + VIII * dE**4 - IX * dE**6; lam = lon0 + X * dE - XI * dE**3 + XII * dE**5 - XIIA * dE**7
    nu = a / math.sqrt(1 - e2 * math.sin(phi)**2); x = nu * math.cos(phi) * math.cos(lam); y = nu * math.cos(phi) * math.sin(lam); z = (1 - e2) * nu * math.sin(phi)
    tx, ty, tz, sc = 446.448, -125.157, 542.060, -20.4894e-6; rx, ry, rz = (math.radians(v / 3600) for v in (0.1502, 0.2470, 0.8421))
    x2 = tx + (1 + sc) * x - rz * y + ry * z; y2 = ty + rz * x + (1 + sc) * y - rx * z; z2 = tz - ry * x + rx * y + (1 + sc) * z
    A, B = 6378137.0, 6356752.3142; ee = 1 - (B * B) / (A * A); p = math.hypot(x2, y2); la = math.atan2(z2, p * (1 - ee))
    for _ in range(10): la = math.atan2(z2 + ee * A / math.sqrt(1 - ee * math.sin(la)**2) * math.sin(la), p)
    return math.degrees(math.atan2(y2, x2)), math.degrees(la)
from collections import defaultdict
src, out = sys.argv[1:3]; os.makedirs(out, exist_ok=True)
F = ['ATCOCode', 'CommonName', 'Indicator', 'Landmark', 'Street', 'LocalityName', 'ParentLocalityName', 'GrandParentLocalityName', 'Town', 'Suburb']
areas = defaultdict(list)
for r in csv.DictReader(open(src, encoding='utf-8-sig')):
    if (r.get('Status') or 'active').lower() != 'active': continue
    try: lon, lat = float(r['Longitude']), float(r['Latitude'])
    except (ValueError, TypeError):
        # some areas (e.g. Cambridgeshire, Norfolk) only give British National Grid easting/northing
        try: lon, lat = osgb_to_wgs84(float(r['Easting']), float(r['Northing']))
        except (ValueError, TypeError, KeyError): continue
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
