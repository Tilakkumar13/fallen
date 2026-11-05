"""Add COSPAR ID, SATCAT owner and launch site to every find in docs/data/history.json.
Run from the repo root: python research/add_liability.py <esa_recovered.csv> <extra_events.csv> <satcat.csv>"""
import csv, json, sys
esa_csv, extra_csv, sat_csv = sys.argv[1:4]
H = "docs/data/history.json"
h = json.load(open(H))
sat = {r["OBJECT_ID"]: r for r in csv.DictReader(open(sat_csv))}
by = {}
for r in csv.DictReader(open(esa_csv)):
    by[(r["Name"].strip(), r["Re-entry Date"].strip())] = r["COSPAR ID"].strip()
    by.setdefault((r["Name"].strip(), None), r["COSPAR ID"].strip())
for r in csv.DictReader(open(extra_csv)):
    by[(r["name"].strip(), r["date"].strip())] = r["cospar"].strip()
# finds reported after the snapshot, identified by name in the news reports
GUESS = {"Zhuque-2E": ("PRC", "JSC"), "SpaceX": ("US", None)}
n = 0
for p in h["points"]:
    # ESA lists one date as "978-09-11" (Cosmos 1029 decayed in 1978)
    if p.get("date") and len(p["date"].split("-")[0]) == 3: p["date"] = "1" + p["date"]
    c = by.get((p["name"], p["date"])) or by.get((p["name"], None))
    s = sat.get(c) if c else None
    p.pop("owner", None); p.pop("site", None); p.pop("cospar", None)
    if s:
        p.update(cospar=c, owner=s["OWNER"], site=s["LAUNCH_SITE"]); n += 1
    else:
        for k, (o, site) in GUESS.items():
            if k in p["name"]:
                p["owner"] = o
                if site: p["site"] = site
                n += 1
json.dump(h, open(H, "w"), separators=(",", ":"))
print(f"{n} of {len(h['points'])} finds have a launching state")
