"""Fallen: refresh what is coming down, where it can fall, and who lives under it.

  python pipeline/update.py              # online: CelesTrak + Aerospace Corporation (run by the scheduled GitHub Action)
  python pipeline/update.py --offline    # test with local files in raw/

Writes docs/data/live.json (objects coming down, with path, countries and people) and docs/data/sky.tle
(everything the live map draws).
"""
import argparse, csv, io, json, math, os, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
import numpy as np
from sgp4.api import Satrec, jday

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "docs", "data")
UA = {"User-Agent": "fallen-reentry-map/1.0 (+https://github.com/Tilakkumar13/fallen)"}
CT = "https://celestrak.org/NORAD/elements/gp.php"
R_E = 6378.137
G = np.load(os.path.join(HERE, "grids.npz")); POP, CID = G["pop"].astype(np.float64), G["country"].astype(np.int32)
COUNTRIES = json.load(open(os.path.join(HERE, "countries.json")))
NY, NX = POP.shape; RES = 180 / NY
LAT_C = 90 - (np.arange(NY) + .5) * RES


def get(url, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            err = e; time.sleep(3 * (k + 1))
    raise err


def parse_tle(text):
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    out = {}
    for i in range(len(lines) - 2):
        if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            out[int(lines[i + 1][2:7])] = (lines[i].strip(), lines[i + 1], lines[i + 2])
    return out


def aerospace_predictions(html):
    """Upcoming predictions from aerospace.org/reentries: NORAD id -> (time UTC, half-window hours).
    Entries read like "STARLINK-2019 (ID 47641) ... Aug 10, 2026 07:04 UTC ± 14 hours"."""
    out = {}
    for m in re.finditer(r"\(ID\s*(\d+)\)(.{0,1500}?)([A-Z][a-z]{2} \d{1,2}, \d{4} \d{2}:\d{2}(?::\d{2})?)\s*(?:UTC)?\s*(?:±|&plusmn;|&#177;|\+/-)\s*(\d+(?:\.\d+)?)\s*(hour|hours|minute|minutes|min|day|days)", html, re.S):
        if "Reentered" in m.group(2): continue
        ts = m.group(3)
        t = datetime.strptime(ts, "%b %d, %Y %H:%M:%S" if ts.count(":") == 2 else "%b %d, %Y %H:%M").replace(tzinfo=timezone.utc)
        w = float(m.group(4)) * {"m": 1 / 60, "h": 1, "d": 24}[m.group(5)[0]]
        out.setdefault(int(m.group(1)), (t, w))
    return out


def aerospace_all(pages=4):
    """The list is paginated (?page=0, 1, ...); keep predictions that haven't passed yet."""
    out, now = {}, datetime.now(timezone.utc)
    for k in range(pages):
        try: html = get("https://aerospace.org/reentries" + (f"?page={k}" if k else ""))
        except Exception as e: print(f"Aerospace page {k}:", e); break
        got = aerospace_predictions(html)
        if not got: break
        for nid, (t, w) in got.items():
            if t + timedelta(hours=w) > now: out.setdefault(nid, (t, w))
    return out


def gmst(jd_ut1):
    t = (jd_ut1 - 2451545.0) / 36525.0
    g = 67310.54841 + (876600 * 3600 + 8640184.812866) * t + 0.093104 * t * t - 6.2e-6 * t ** 3
    return math.radians((g % 86400) / 240.0)


def subpoint(sat, when):
    jd, fr = jday(when.year, when.month, when.day, when.hour, when.minute, when.second + when.microsecond / 1e6)
    e, r, _ = sat.sgp4(jd, fr)
    if e != 0: return None
    th = gmst(jd + fr)
    x = r[0] * math.cos(th) + r[1] * math.sin(th); y = -r[0] * math.sin(th) + r[1] * math.cos(th); z = r[2]
    rr = math.sqrt(x * x + y * y + z * z)
    return math.degrees(math.asin(z / rr)), (math.degrees(math.atan2(y, x)) + 540) % 360 - 180, rr - R_E


def decay_estimate(sat, now, horizon_days=90):
    """Step SGP4 forward until the orbit drops below 120 km or the model reports decay."""
    t, step, last = now, timedelta(hours=6), now
    while t < now + timedelta(days=horizon_days):
        p = subpoint(sat, t)
        if p is None or p[2] < 120:
            # refine inside the last step
            lo, hi = last, t
            for _ in range(12):
                mid = lo + (hi - lo) / 2; q = subpoint(sat, mid)
                (lo, hi) = (mid, hi) if (q is not None and q[2] >= 120) else (lo, mid)
            return lo
        last = t
        if p[2] < 200: step = timedelta(minutes=30)
        t += step
    return None


def band_rows(inc):
    i = math.radians(min(inc, 180 - inc)); s = max(math.sin(i), 1e-6)
    edge = lambda p: 0.5 + np.arcsin(np.clip(np.sin(np.radians(p)) / s, -1, 1)) / np.pi
    return edge(LAT_C + RES / 2) - edge(LAT_C - RES / 2)


def cell(lat, lon):
    return min(NY - 1, max(0, int((90 - lat) / RES))), min(NX - 1, max(0, int((lon + 180) / RES)))


def exposure_path(sat, t0, half_h, swath_km=50):
    """Ground track from t0-half to t0+half; cells within swath_km; people and countries under it."""
    start, end = t0 - timedelta(hours=half_h), t0 + timedelta(hours=half_h)
    step = timedelta(seconds=10)
    mask = np.zeros((NY, NX), bool); pts, t, land = [], start, 0; n = 0
    dlat = swath_km / 111.0
    while t <= end:
        p = subpoint(sat, t)
        if p is not None:
            lat, lon, _ = p; n += 1
            i, j = cell(lat, lon)
            di = int(math.ceil(dlat / RES)); dj = int(math.ceil(dlat / max(math.cos(math.radians(lat)), .05) / RES))
            mask[max(0, i - di):i + di + 1, max(0, j - dj):j + dj + 1] = True
            if j - dj < 0: mask[max(0, i - di):i + di + 1, NX + j - dj:] = True
            if j + dj >= NX: mask[max(0, i - di):i + di + 1, :j + dj - NX + 1] = True
            land += CID[i, j] > 0
            if len(pts) == 0 or (t - pts[-1][2]).total_seconds() >= 60: pts.append((round(lat, 2), round(lon, 2), t))
        t += step
    people = float(POP[mask].sum())
    by = np.bincount(CID[mask].ravel(), weights=POP[mask].ravel(), minlength=len(COUNTRIES) + 1)
    top = [{"name": COUNTRIES[k - 1]["name"], "n3": COUNTRIES[k - 1]["n3"], "inc": COUNTRIES[k - 1]["inc"], "people": int(by[k])}
           for k in np.argsort(-by) if k > 0 and by[k] >= 1]
    return {"mode": "path", "swath_km": swath_km, "people": int(people), "land_share": round(land / max(n, 1), 2),
            "countries": top[:40], "n_countries": len(top),
            "track": [[a, b] for a, b, _ in pts]}


def exposure_band(inc):
    """When the window spans many orbits, every longitude in the band is possible: weight by time at each latitude."""
    w = band_rows(inc)[:, None] / NX
    risk = POP * w
    by = np.bincount(CID.ravel(), weights=risk.ravel(), minlength=len(COUNTRIES) + 1)
    tot = by[1:].sum(); land = (w * (CID > 0)).sum()
    top = [{"name": COUNTRIES[k - 1]["name"], "n3": COUNTRIES[k - 1]["n3"], "inc": COUNTRIES[k - 1]["inc"], "share": round(float(by[k] / tot), 4)}
           for k in np.argsort(-by) if k > 0 and by[k] / tot >= 0.002]
    lim = min(inc, 180 - inc)
    return {"mode": "band", "lat_limit": round(lim, 1), "people": int(POP[np.abs(LAT_C) <= lim].sum()),
            "land_share": round(float(land), 2), "countries": top[:40], "n_countries": len(top)}


ISO = lambda t: t.isoformat().replace("+00:00", "Z")


def record(track, nid, name, typ, now, aero, ours):
    o = track.setdefault(str(nid), {"name": name, "type": typ, "aero": [], "ours": [], "final": None})
    for key, val in (("aero", aero), ("ours", ours)):
        if not val or val[0] is None: continue
        row = [ISO(now), ISO(val[0]), round(val[1], 1)]
        if not o[key] or o[key][-1][1] != row[1]: o[key].append(row)
        o[key] = o[key][-60:]


def aerospace_final(nid):
    html = get(f"https://aerospace.org/reentries/{nid}")
    if "Reentered" not in html: return None
    m = re.search(r"(\d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}) UTC\s*(?:±|&plusmn;)\s*(\d+(?:\.\d+)?)\s*(minute|hour|day)", html)
    if not m: return None
    t = datetime.strptime(m.group(1), "%d %b %Y %H:%M").replace(tzinfo=timezone.utc)
    return {"t": ISO(t), "half_h": float(m.group(2)) * {"m": 1 / 60, "h": 1, "d": 24}[m.group(3)[0]], "src": "Aerospace Corporation final prediction"}


def close_out(track, cat, offline):
    """Objects that have come down: store the best public re-entry time."""
    for nid, o in track.items():
        if o.get("final"): continue
        last = (o["aero"] or o["ours"] or [[None, None]])[-1][1]
        if not last or datetime.fromisoformat(last.replace("Z", "+00:00")) > datetime.now(timezone.utc) - timedelta(hours=2): continue
        c = cat.get(int(nid), {})
        fin = None
        if not offline:
            try: fin = aerospace_final(nid)
            except Exception: fin = None
        if not fin and c.get("DECAY_DATE"):
            fin = {"t": c["DECAY_DATE"] + "T12:00:00Z", "half_h": 12.0, "src": "CelesTrak decay date (day only)"}
        if fin: o["final"] = fin
    # keep the file small: drop objects with no data older than 120 days
    return track


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--offline", action="store_true"); ap.add_argument("--max", type=int, default=60)
    a = ap.parse_args()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    raw = os.path.join(os.path.dirname(ROOT), "raw")
    if a.offline:
        sky = {}; [sky.update(parse_tle(open(os.path.join(raw, f)).read())) for f in ("stations.tle", "starlink.tle")]
        decaying, preds = {}, {}
        satcat_text = open(os.path.join(raw, "satcat.csv")).read()
    else:
        sky = parse_tle(get(f"{CT}?GROUP=active&FORMAT=tle"))
        try: decaying = parse_tle(get(f"{CT}?SPECIAL=DECAYING&FORMAT=tle"))
        except Exception as e: print("no DECAYING group:", e); decaying = {}
        try: preds = aerospace_all()
        except Exception as e: print("no Aerospace predictions:", e); preds = {}
        print(f"Aerospace predictions: {len(preds)}")
        for nid in [k for k in preds if k not in sky and k not in decaying][:80]:
            try: decaying.update(parse_tle(get(f"{CT}?CATNR={nid}&FORMAT=tle")))
            except Exception: pass
        satcat_text = get("https://celestrak.org/pub/satcat.csv")
    cat = {int(r["NORAD_CAT_ID"]): r for r in csv.DictReader(io.StringIO(satcat_text))}
    allobj = dict(sky); allobj.update(decaying)
    # candidates: low perigee, from Aerospace's list, or in the decaying group
    cands = []
    for nid, (name, l1, l2) in allobj.items():
        sat = Satrec.twoline2rv(l1, l2)
        n = sat.no_kozai * 1440 / (2 * math.pi)                        # rev/day
        a_km = (398600.4418 / (n * 2 * math.pi / 86400) ** 2) ** (1 / 3)
        per = a_km * (1 - sat.ecco) - R_E
        if nid in preds or nid in decaying or per < 230:
            cands.append((per, nid, name, l1, l2, sat))
    cands.sort()
    tpath = os.path.join(OUT, "track.json")
    track = json.load(open(tpath)).get("objects", {}) if os.path.exists(tpath) else {}
    live = []
    for per, nid, name, l1, l2, sat in cands[: a.max * 3]:
        c = cat.get(nid, {})
        if c.get("DECAY_DATE"): continue
        ours = decay_estimate(sat, now)
        ours_half = max(1.0, 0.2 * (ours - now).total_seconds() / 3600) if ours else None
        if nid in preds:
            t0, half = preds[nid]; src = {"label": "The Aerospace Corporation", "url": f"https://aerospace.org/reentries/{nid}"}
        else:
            t0, half = ours, ours_half
            if t0 is None or t0 < now: continue
            src = {"label": "Our estimate: SGP4 with the TLE drag term, ±20% of time left", "url": None}
        record(track, nid, name, c.get("OBJECT_TYPE"), now, (t0, half) if nid in preds else None, (ours, ours_half) if ours else None)
        if t0 + timedelta(hours=half) < now: continue
        inc = sat.inclo * 180 / math.pi
        exp = exposure_path(sat, t0, half) if half <= 12 else exposure_band(inc)
        live.append({
            "norad": nid, "name": name, "cospar": c.get("OBJECT_ID"), "type": c.get("OBJECT_TYPE"), "owner": c.get("OWNER"), "site": c.get("LAUNCH_SITE"),
            "launch": c.get("LAUNCH_DATE"), "rcs": c.get("RCS"), "inc": round(inc, 2), "perigee": round(per), "tle": [l1, l2],
            "t0": t0.isoformat().replace("+00:00", "Z"), "half_h": round(half, 1), "source": src, "exposure": exp,
            "links": {"celestrak": f"https://celestrak.org/satcat/table-satcat.php?CATNR={nid}",
                      "aerospace": f"https://aerospace.org/reentries/{nid}", "n2yo": f"https://www.n2yo.com/satellite/?s={nid}"}})
        print(f"{name:28s} {nid:6d} per {per:4.0f} km  {t0:%Y-%m-%d %H:%M} ±{half:5.1f} h  {exp['mode']:4s} people {exp['people']:,}")
        if len(live) >= a.max: break
    live.sort(key=lambda o: o["t0"])
    close_out(track, cat, a.offline)
    started = (json.load(open(tpath)).get("started") if os.path.exists(tpath) else None) or ISO(now)
    json.dump({"started": started, "updated": ISO(now), "objects": track}, open(tpath, "w"), separators=(",", ":"))
    os.makedirs(OUT, exist_ok=True)
    json.dump({"updated": now.isoformat().replace("+00:00", "Z"), "predictions_from_aerospace": len(preds), "objects": live},
              open(os.path.join(OUT, "live.json"), "w"), separators=(",", ":"))
    with open(os.path.join(OUT, "sky.tle"), "w") as f:
        for nid, (name, l1, l2) in allobj.items():
            f.write(f"{name}\n{l1}\n{l2}\n")
    print(f"{len(live)} coming down, {len(allobj)} objects on the map")


if __name__ == "__main__":
    main()
