"""Turn the BODS regional GTFS into Route Studio timetable CSVs for one operator.

Usage: python3 bods_extract.py <gtfs.zip> <naptan Stops.csv> <out dir> <region key> [agency name]
Run once per BODS region, then bods_merge.py joins the per-region indexes into index.json.

For each route group (82, 82A, 82C → "82") it writes <group>.csv in the Route Studio template format:
day tabs (MF / SA / SU), an outbound and an inbound table in each, timing points only, with NaPTAN code,
latitude and longitude for every stop. index.json lists the groups and the key codes used.

Days are read from the next school-term month (REF_*), and school-day journeys are told apart from ones that
also run in the holidays by looking at the next Christmas or summer holiday (HOL). Both are worked out from today.
"""
import csv, io, json, re, sys, zipfile, datetime as dt
from collections import defaultdict, Counter

GTFS, NAPTAN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
REGION = sys.argv[4]
AGENCY = sys.argv[5] if len(sys.argv) > 5 else "Central Connect"
REGION_NAME = REGION.replace("_", " ").title()
D = dt.date

def easter(y):
    a, b, c = y % 19, y // 100, y % 100; d, e = b // 4, b % 4; f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i, k = c // 4, c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
    return D(y, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)
def school_holiday(d):
    """roughly when most English schools are off (dates vary by council, so this errs wide)"""
    y = d.year; e = easter(y)
    return (d >= D(y, 7, 20) and d <= D(y, 9, 4)) or d >= D(y, 12, 18) or d <= D(y, 1, 5) \
        or D(y, 10, 20) <= d <= D(y, 11, 1) or D(y, 2, 9) <= d <= D(y, 2, 21) or D(y, 5, 24) <= d <= D(y, 6, 2) \
        or e - dt.timedelta(days=14) <= d <= e + dt.timedelta(days=9)
TODAY = dt.date.today()
# a normal term-time month: the first four whole weeks from next Monday that don't touch a school holiday
REF_FROM = TODAY + dt.timedelta(days=7 - TODAY.weekday())
while any(school_holiday(REF_FROM + dt.timedelta(days=i)) for i in range(28)): REF_FROM += dt.timedelta(days=7)
REF_TO = REF_FROM + dt.timedelta(days=27)
# the next Christmas or summer holiday weekdays (not bank holidays), to tell schooldays-only journeys apart
def hol_from(y):
    xmas = [D(y, 12, d) for d in (21, 22, 23, 29, 30, 31)]
    summer = [D(y, 8, d) for d in range(3, 24)]
    return [d for d in sorted(summer + xmas) if d.weekday() < 5]
HOL = [d for d in hol_from(TODAY.year) + hol_from(TODAY.year + 1) if d > TODAY]
HOL = [d for d in HOL if d.month == HOL[0].month and d.year == HOL[0].year]

z = zipfile.ZipFile(GTFS)
rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8-sig"))

agency = [a for a in rd("agency.txt") if a["agency_name"].strip().lower() == AGENCY.lower()]
if not agency: sys.exit(f"No agency called {AGENCY}")
aid = {a["agency_id"] for a in agency}
routes = {r["route_id"]: r["route_short_name"].strip() for r in rd("routes.txt") if r["agency_id"] in aid}
trips = {t["trip_id"]: t for t in rd("trips.txt") if t["route_id"] in routes}
svc_ids = {t["service_id"] for t in trips.values()}

# ---- service calendars → the set of dates each service runs on (only the dates we look at)
look = [REF_FROM + dt.timedelta(days=i) for i in range((REF_TO - REF_FROM).days + 1)] + HOL
cal = {c["service_id"]: c for c in rd("calendar.txt") if c["service_id"] in svc_ids}
days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
pd = lambda s: D(int(s[:4]), int(s[4:6]), int(s[6:]))
runs = defaultdict(set)
for sid, c in cal.items():
    a, b = pd(c["start_date"]), pd(c["end_date"])
    for d in look:
        if a <= d <= b and c[days[d.weekday()]] == "1": runs[sid].add(d)
lookset = set(look)
for x in rd("calendar_dates.txt"):
    if x["service_id"] not in svc_ids: continue
    d = pd(x["date"])
    if d not in lookset: continue
    (runs[x["service_id"]].add if x["exception_type"] == "1" else runs[x["service_id"]].discard)(d)

# ---- timing points of each trip
st = defaultdict(list)
for r in rd("stop_times.txt"):
    if r["trip_id"] in trips: st[r["trip_id"]].append(r)
stops_used = {r["stop_id"] for v in st.values() for r in v}
gstops = {s["stop_id"]: s for s in rd("stops.txt") if s["stop_id"] in stops_used}

# NaPTAN: locality (town) and common name
nap = {}
with open(NAPTAN, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if r["ATCOCode"] in stops_used: nap[r["ATCOCode"]] = r

def stop_label(sid):
    n = nap.get(sid); g = gstops.get(sid, {})
    town = (n and (n["LocalityName"] or n["ParentLocalityName"])) or ""
    name = (n and n["CommonName"]) or g.get("stop_name", sid)
    return town.strip(), name.strip()

def hm(t):
    h, m, _ = (int(x) for x in t.split(":")); return h * 60 + m

journeys = {}   # signature → journey (trips with the same route, direction and times are one journey)
for tid, rows in st.items():
    t = trips[tid]; dates = runs.get(t["service_id"], set())
    if not dates: continue
    rows.sort(key=lambda r: int(r["stop_sequence"]))
    tp = [r for r in rows if r.get("timepoint", "1") == "1"] or rows
    if rows[0] not in tp: tp.insert(0, rows[0])
    if rows[-1] not in tp: tp.append(rows[-1])
    calls = tuple((r["stop_id"], hm(r["departure_time"] or r["arrival_time"])) for r in tp)
    key = (routes[t["route_id"]], t["direction_id"], calls)
    j = journeys.setdefault(key, {"route": key[0], "dir": key[1], "calls": calls, "dates": set()})
    j["dates"] |= dates

DAYNAME = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays"]
DAYCODE = ["MO", "TUO", "WO", "THO", "FO"]
meanings = {"SCH": "Schooldays only", "SH": "School holidays only", "FO": "Fridays only"}
def classify(j):
    """→ list of (tab, codes)"""
    ref = [d for d in j["dates"] if REF_FROM <= d <= REF_TO]; hol = [d for d in j["dates"] if d in HOL]
    out = []
    wk = Counter(d.weekday() for d in ref)
    need = Counter(d.weekday() for d in look if REF_FROM <= d <= REF_TO)
    on = [k for k in range(5) if wk[k] >= need[k] / 2]
    if on:
        codes = []
        if len(on) < 5:
            if len(on) == 1: codes.append(DAYCODE[on[0]]); meanings[DAYCODE[on[0]]] = DAYNAME[on[0]] + " only"
            else:
                c = "".join(DAYNAME[k][:2] for k in on).upper(); codes.append(c)
                meanings[c] = ", ".join(DAYNAME[k] for k in on[:-1]) + " and " + DAYNAME[on[-1]] + " only"
        if not hol: codes.append("SCH")
        out.append(("MF", codes))
    elif len(hol) >= len(HOL) / 2: out.append(("MF", ["SH"]))   # a few odd added dates (bank holidays on a Sunday timetable) don't count
    if wk[5] >= need[5] / 2: out.append(("SA", []))
    if wk[6] >= need[6] / 2: out.append(("SU", []))
    return out

def merge_order(seqs):
    """one stop order that keeps every journey's order (stops can appear twice, e.g. a loop back to the bus station)"""
    master = []
    for s in sorted(seqs, key=len, reverse=True):
        last = -1
        for sid in s:
            try: i = master.index(sid, last + 1)
            except ValueError: master.insert(last + 1, sid); i = last + 1
            last = i
    return master

def group_of(r):
    m = re.match(r"^([A-Z]*\d+)", r); return m.group(1) if m else r

groups = defaultdict(list)
for j in journeys.values(): groups[group_of(j["route"])].append(j)

def fmt(m): m %= 1440; return f"{m // 60:02d}:{m % 60:02d}"
def q(v): v = str(v); return f'"{v.replace(chr(34), chr(34) * 2)}"' if re.search(r'[",\n]', v) else v
natkey = lambda s: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]

index = []
for g, js in sorted(groups.items(), key=lambda x: natkey(x[0])):
    tabs = defaultdict(list)
    for j in js:
        for tab, codes in classify(j): tabs[tab].append((j, codes))
    if not tabs: continue
    lines = []; used_codes = set(); n_j = 0; summary = ""
    for tab in ("MF", "SA", "SU"):
        if tab not in tabs: continue
        lines.append([tab])
        for d in ("0", "1"):
            col = [(j, c) for j, c in tabs[tab] if j["dir"] == d]
            if not col: continue
            master = merge_order([[s for s, _ in j["calls"]] for j, _ in col])
            # place each journey's calls on the master rows (same order, repeats allowed)
            placed = []
            for j, c in col:
                row = {}; last = -1
                for sid, t in j["calls"]:
                    i = master.index(sid, last + 1); row[i] = t; last = i
                placed.append((j, c, row))
            cover = Counter(i for _, _, r in placed for i in r); R = max(cover, key=lambda i: (cover[i], -i))
            offs = defaultdict(list)
            for _, _, r in placed:
                if R in r:
                    for i, t in r.items(): offs[i].append(r[R] - t)
            def key(p):
                r = p[2]
                if R in r: return r[R]
                i0 = min(r); o = sorted(offs[i0]); return r[i0] + (o[len(o) // 2] if o else 0)
            placed.sort(key=key)
            # title from the commonest stopping pattern: where it starts, two places on the way, where it ends
            pat = Counter(tuple(s for s, _ in j["calls"]) for j, _, _ in placed).most_common()
            main = max(pat, key=lambda x: (x[1], len(x[0])))[0]
            towns = []
            for i in main:
                tw = stop_label(i)[0] or stop_label(i)[1]
                if not towns or towns[-1] != tw: towns.append(tw)
            if len(towns) > 4: towns = [towns[0], towns[len(towns) // 3], towns[2 * len(towns) // 3], towns[-1]]
            title = " > ".join(dict.fromkeys(towns))
            if not summary: summary = title
            lines.append([title])
            lines.append(["Route", "NaPTAN", "Latitude", "Longitude"] + [j["route"] for j, _, _ in placed])
            lines.append(["Codes", "", "", ""] + [" ".join(c) for _, c, _ in placed])
            for c in (c for _, c, _ in placed): used_codes.update(c)
            for i, sid in enumerate(master):
                times = [fmt(r[i]) if i in r else "–" for _, _, r in placed]
                if all(t == "–" for t in times): continue
                tw, nm = stop_label(sid); g_ = gstops.get(sid, {})
                lines.append([f"{tw}, {nm}" if tw else nm, sid, round(float(g_.get("stop_lat", "nan")), 6), round(float(g_.get("stop_lon", "nan")), 6)] + times)
            lines.append([])
            n_j += len(placed)
        lines.append([])
    fn = f"{REGION}-{g}.csv"
    with open(f"{OUT}/{fn}", "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(",".join(q(v) for v in r) for r in lines) + "\r\n")
    rts = sorted({j["route"] for j in js}, key=natkey)
    index.append({"id": f"{REGION}-{g}", "region": REGION_NAME, "routes": rts, "name": summary, "file": fn, "journeys": n_j, "days": [t for t in ("MF", "SA", "SU") if t in tabs]})

feed = next(rd("feed_info.txt"))
json.dump({"operator": AGENCY, "source": f"Bus Open Data Service (BODS) GTFS, {REGION_NAME}", "feed_version": feed["feed_version"],
           "generated": dt.date.today().isoformat(), "term_month": [REF_FROM.isoformat(), REF_TO.isoformat()],
           "codes": meanings, "groups": index}, open(f"{OUT}/index-{REGION}.json", "w"), indent=1)
print(len(index), "route groups:", ", ".join(f"{x['id']}({'/'.join(x['routes'])}:{x['journeys']})" for x in index))
