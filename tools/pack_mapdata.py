"""Pack an Overpass export into the compact map-data format the builder's Map mode reads.

Format (all coordinates are integers in 1e-5 degrees, delta-encoded: [x0, y0, dx1, dy1, ...]):
{ v:1, name, bbox:[s,w,n,e], roads:[[cls, ref, enc]], rivers:[[name, enc]], rails:[enc],
  areas:[[kind, [enc ring, ...]]], places:[[name, kind, lon, lat]], stations:[[name, lon, lat]] }
cls: 0 trunk/motorway, 1 primary, 2 secondary, 3 tertiary, 4 unclassified, 5 residential
kind: "built", "landscape", "water"
"""
import json, math, sys

SRC, OUT, NAME = sys.argv[1], sys.argv[2], sys.argv[3]
Q = 1e5
CLS = {'motorway': 0, 'trunk': 0, 'primary': 1, 'secondary': 2, 'tertiary': 3, 'unclassified': 4, 'residential': 5}
BUILT = {'residential', 'commercial', 'retail', 'industrial'}


def dp(pts, tol):
    if len(pts) < 3: return pts
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    L = math.hypot(x1 - x0, y1 - y0)
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        # closed rings start and end on the same point: measure from that point instead of a line
        d = abs((y1 - y0) * x - (x1 - x0) * y + x1 * y0 - y1 * x0) / L if L > 1e-12 else math.hypot(x - x0, y - y0)
        if d > dmax: dmax, idx = d, i
    if dmax <= tol: return [pts[0], pts[-1]]
    return dp(pts[:idx + 1], tol)[:-1] + dp(pts[idx:], tol)


def enc(pts):
    out, px, py = [], 0, 0
    for i, (lon, lat) in enumerate(pts):
        x, y = round(lon * Q), round(lat * Q)
        if i and x == px and y == py: continue
        out += [x - px, y - py] if out else [x, y]
        px, py = x, y
    return out


def stitch(segs):
    segs = [list(s) for s in segs if len(s) > 1]
    rings = []
    while segs:
        ring = segs.pop(0); changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]: ring += s[1:]
                elif s[-1] == ring[-1]: ring += s[::-1][1:]
                elif s[-1] == ring[0]: ring = s[:-1] + ring
                elif s[0] == ring[0]: ring = s[::-1][:-1] + ring
                else: continue
                segs.pop(i); changed = True; break
        if len(ring) > 3: rings.append(ring)
    return rings


def area(r):
    k = math.cos(math.radians(r[0][1]))
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(r, r[1:] + r[:1]))) / 2 * k * 111_195 ** 2


def kind_of(t):
    if t.get('boundary') in ('protected_area', 'national_park'):
        if t.get('boundary') == 'national_park' or t.get('designation') in ('area_of_outstanding_natural_beauty', 'national_park') \
                or t.get('protect_class') == '5':
            return 'landscape'
        return None
    if t.get('landuse') in BUILT: return 'built'
    if t.get('natural') == 'water': return 'water'
    return None


d = json.load(open(SRC))
els = d['elements']
use = {}
for e in els:
    if e['type'] == 'way' and e.get('tags', {}).get('highway', '').replace('_link', '') in CLS:
        for n in e['nodes']: use[n] = use.get(n, 0) + 1

out = dict(v=1, name=NAME, roads=[], rivers=[], rails=[], areas=[], places=[], stations=[])
lons, lats = [], []
for e in els:
    t = e.get('tags', {})
    if e['type'] == 'node':
        if t.get('railway') == 'station' and t.get('name'):
            out['stations'].append([t['name'], round(e['lon'], 5), round(e['lat'], 5)])
        elif t.get('place') in ('city', 'town', 'village', 'suburb', 'hamlet') and t.get('name'):
            out['places'].append([t['name'], t['place'], round(e['lon'], 5), round(e['lat'], 5)])
        continue
    if e['type'] == 'way':
        g = [(p['lon'], p['lat']) for p in e.get('geometry', []) if p]
        if not g: continue
        lons += [g[0][0]]; lats += [g[0][1]]
        hw = t.get('highway', '').replace('_link', '')
        if hw in CLS:
            ids = e['nodes']
            # keep junction nodes exactly so routing stays connected; simplify only between them
            keep = [i for i, n in enumerate(ids) if i == 0 or i == len(ids) - 1 or use.get(n, 0) > 1]
            pts = []
            for a, b in zip(keep, keep[1:]):
                seg = dp(g[a:b + 1], 1.5e-5)
                pts += seg if not pts else seg[1:]
            out['roads'].append([CLS[hw], (t.get('ref') or '').split(';')[0], enc(pts)])
            continue
        if t.get('waterway') == 'river':
            out['rivers'].append([t.get('name', ''), enc(dp(g, 3e-5))]); continue
        if t.get('railway') == 'rail' and t.get('service') not in ('siding', 'yard', 'spur', 'crossover'):
            out['rails'].append(enc(dp(g, 2e-5))); continue
        k = kind_of(t)
        if k and len(g) > 3 and g[0] == g[-1]:
            if k == 'built' and area(g) < 4000: continue
            if k == 'water' and area(g) < 20000: continue
            out['areas'].append([k, [enc(dp(g, 2.5e-5))]] + ([t.get('name', '')] if k == 'landscape' else []))
    elif e['type'] == 'relation':
        k = kind_of(t)
        if not k: continue
        mem = lambda role: [[(p['lon'], p['lat']) for p in m.get('geometry', []) if p]
                            for m in e.get('members', []) if m['type'] == 'way' and m.get('role') in role]
        rings = stitch(mem(('outer', ''))) + stitch(mem(('inner',)))
        rings = [r for r in rings if area(r) > (20000 if k == 'water' else 4000)]
        if rings: out['areas'].append([k, [enc(dp(r, 2.5e-5)) for r in rings]] + ([t.get('name', '')] if k == 'landscape' else []))

b = d.get('osm3s', {})
out['bbox'] = [round(min(lats), 4), round(min(lons), 4), round(max(lats), 4), round(max(lons), 4)]
s = json.dumps(out, separators=(',', ':'), ensure_ascii=False)
open(OUT, 'w').write(s)
print(f"{len(s)/1e6:.2f} MB  roads {len(out['roads'])}  areas {len(out['areas'])}  places {len(out['places'])}  "
      f"stations {len(out['stations'])}  rails {len(out['rails'])}  rivers {len(out['rivers'])}  bbox {out['bbox']}")
