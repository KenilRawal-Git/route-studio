"""Join the per-region outputs of bods_extract.py / bods_paths.py into index.json and paths.json.
Usage: python3 bods_merge.py <out dir> <region> [<region> ...]"""
import json, sys
OUT, regions = sys.argv[1], sys.argv[2:]
idx = {"operator": None, "source": "Bus Open Data Service (BODS) GTFS", "regions": [], "codes": {}, "groups": []}
paths = {"v": 1, "routes": {}}
for r in regions:
    i = json.load(open(f"{OUT}/index-{r}.json"))
    idx["operator"] = i["operator"]; idx["feed_version"] = i["feed_version"]; idx["generated"] = i["generated"]; idx["term_month"] = i["term_month"]
    idx["regions"].append(r.replace("_", " ").title()); idx["codes"].update(i["codes"])
    seen = {(tuple(g["routes"]), g["name"]) for g in idx["groups"]}
    idx["groups"] += [g for g in i["groups"] if (tuple(g["routes"]), g["name"]) not in seen]   # routes on a region border appear in both files
    for k, v in json.load(open(f"{OUT}/paths-{r}.json"))["routes"].items(): paths["routes"].setdefault(k, []).extend(v)
json.dump(idx, open(f"{OUT}/index.json", "w"), indent=1)
json.dump(paths, open(f"{OUT}/paths.json", "w"), separators=(",", ":"))
print(len(idx["groups"]), "route groups from", ", ".join(idx["regions"]))
