"""The sea for each map square, from OpenStreetMap's coastline (natural=coastline ways: land on the left, sea on the right).

sea_cells(want, coast, filled, cell) -> {(i, j): [["sea", [enc ring, ...]], ...]}
  want   the squares being built, as (i, j) = (lat // cell, lon // cell)
  coast  {(i, j): [[(lon, lat), ...], ...]} coastline ways touching each square
  filled squares that have any map features (an empty square is open sea when it borders sea, else empty country)

Each square is cut along the coastline; a piece is sea when the points just to the right of the coastline fall in it.
The result is in pack_mapdata.py's area format, kind "sea", so it's drawn under everything else.
"""
import math
from shapely.geometry import LineString, Point, box
from shapely.ops import polygonize, unary_union

Q = 1e5


def _enc(pts):
    out, px, py = [], 0, 0
    for i, (lon, lat) in enumerate(pts):
        x, y = round(lon * Q), round(lat * Q)
        if i and x == px and y == py: continue
        out += [x - px, y - py] if out else [x, y]
        px, py = x, y
    return out


def _area(poly):
    k = math.cos(math.radians(poly.centroid.y))
    return poly.area * k * 111_195 ** 2


def _pieces(B, ways):
    """the square cut along the coastline: [(polygon, is_sea)]"""
    lines = []
    for g in ways:
        L = LineString(g).intersection(B)
        if L.is_empty: continue
        lines += [L] if L.geom_type == "LineString" else [x for x in getattr(L, "geoms", []) if x.geom_type == "LineString"]
    if not lines: return None
    faces = list(polygonize(unary_union([B.exterior] + lines)))
    if not faces: return None
    votes = [0] * len(faces)
    eps = 2e-6
    for g in ways:
        for (x0, y0), (x1, y1) in list(zip(g, g[1:]))[:: max(1, len(g) // 400)]:
            dx, dy = x1 - x0, y1 - y0; L = math.hypot(dx, dy)
            if L < 1e-9: continue
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            if not B.contains(Point(mx, my)): continue
            nx, ny = dy / L * eps, -dx / L * eps      # to the right of the way's direction
            for p, v in ((Point(mx + nx, my + ny), 1), (Point(mx - nx, my - ny), -1)):
                for f, face in enumerate(faces):
                    if face.contains(p): votes[f] += v; break
    return [(f, v > 0) for f, v in zip(faces, votes) if v != 0]


def sea_cells(want, coast, filled, cell):
    out, edge_sea = {}, {}
    B_of = lambda i, j: box(j * cell, i * cell, (j + 1) * cell, (i + 1) * cell)
    for c in want:
        if not coast.get(c): continue
        B = B_of(*c); ps = _pieces(B, coast[c])
        if not ps: continue
        sea = [f for f, s in ps if s]
        if not sea: continue
        out[c] = sea
        # which sides of the square touch sea, so empty squares beyond it can be filled
        u = unary_union(sea)
        x0, y0, x1, y1 = B.bounds
        sides = {"s": LineString([(x0, y0), (x1, y0)]), "n": LineString([(x0, y1), (x1, y1)]),
                 "w": LineString([(x0, y0), (x0, y1)]), "e": LineString([(x1, y0), (x1, y1)])}
        edge_sea[c] = {k for k, L in sides.items() if u.buffer(1e-7).intersection(L).length > cell * 0.05}
    # open sea: empty squares reached from a sea side, spreading through other empty squares
    step = {"n": (1, 0), "s": (-1, 0), "e": (0, 1), "w": (0, -1)}
    todo = [(c[0] + step[k][0], c[1] + step[k][1]) for c, ks in edge_sea.items() for k in ks]
    open_sea = set()
    while todo:
        c = todo.pop()
        if c in open_sea or c not in want or c in filled or coast.get(c): continue
        open_sea.add(c); todo += [(c[0] + a, c[1] + b) for a, b in step.values()]
    for c in open_sea: out[c] = [B_of(*c)]
    res = {}
    for c, polys in out.items():
        areas = []
        for p in polys:
            p = p.simplify(2.5e-5)
            if p.is_empty or _area(p) < 20000: continue
            for q in ([p] if p.geom_type == "Polygon" else list(p.geoms)):
                areas.append(["sea", [_enc(list(q.exterior.coords))] + [_enc(list(r.coords)) for r in q.interiors]])
        if areas: res[c] = areas
    return res
