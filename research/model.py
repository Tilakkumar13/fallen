"""Fallen: is the record of space debris found on the ground a record of risk, or of who looks?

Inputs
  esa_recovered.csv   ESA re-entry portal, "Recovered debris" table (parse_esa.py)
  raw/satcat.csv      CelesTrak SATCAT (orbit inclination, owner) via a GitHub mirror
  countries.geojson   Natural Earth 1:50m admin-0 (borders, population, GDP, economy class)
  pop_grid.npz        optional GHS-POP 2020 on the 0.25 degree grid; otherwise each country's
                      population is spread evenly over its land (crude, flagged in the output)

Model
  An uncontrolled re-entry spends time at each latitude according to its inclination i:
  P(lat < phi) = 1/2 + arcsin(sin phi / sin i) / pi. Longitude is taken as uniform.
  For every recovered event we ask where, given its orbit, debris would land
    LAND  on any land (finds follow where debris can fall), or
    POP   near people (finds follow population: someone has to see it).
  Summed over events this gives each country's expected number of finds under each model.
"""
import json, sys
import numpy as np, pandas as pd, geopandas as gpd
from rasterio import features
from rasterio.transform import from_origin

R = 0.25; NX, NY = int(360 / R), int(180 / R)
lat_c = 90 - (np.arange(NY) + .5) * R
DEDICATED = {"1977-091A": "Cosmos 954", "1973-027A": "Skylab", "1982-033A": "Salyut 7", "2003-003A": "Columbia"}


def grids():
    c = gpd.read_file("countries.geojson")
    c = c[c.POP_EST > 0].reset_index(drop=True)
    ids = features.rasterize(((g, i + 1) for i, g in enumerate(c.geometry)), out_shape=(NY, NX),
                             transform=from_origin(-180, 90, R, R), fill=0, dtype="int32", all_touched=False)
    s = np.sin(np.radians(90 - np.arange(NY + 1) * R))
    cell_km2 = (6371.0088 ** 2 * np.radians(R) * (s[:-1] - s[1:]))[:, None] * np.ones((1, NX))
    try:
        pop = np.load("pop_grid.npz")["pop"]; source = "GHS-POP 2020 (0.25 deg)"
    except FileNotFoundError:
        area = np.bincount(ids.ravel(), weights=cell_km2.ravel(), minlength=len(c) + 1)
        dens = np.where(ids > 0, (c.POP_EST.values / np.maximum(area[1:], 1))[np.maximum(ids - 1, 0)], 0)
        pop = dens * cell_km2; source = "CRUDE: country population spread evenly"
    land = (ids > 0) * cell_km2
    return c, ids, pop, land, source


def band(inc):
    i = np.radians(min(inc, 180 - inc)); s = max(np.sin(i), 1e-6)
    edge = lambda p: 0.5 + np.arcsin(np.clip(np.sin(np.radians(p)) / s, -1, 1)) / np.pi
    return edge(lat_c + R / 2) - edge(lat_c - R / 2)          # share of time in each row


def events():
    d = pd.read_csv("esa_recovered.csv")
    d.columns = ["cospar", "name", "date", "loc", "country", "mass", "shape", "size", "material", "type", "cls"]
    ll = d["loc"].str.extract(r"(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)").astype(float)
    d["lat"], d["lon"] = ll[0], ll[1]
    d["country"] = d.country.str.split(" - ").str[0].str.strip()
    sat = pd.read_csv("raw/satcat.csv", usecols=["OBJECT_ID", "INCLINATION", "OWNER", "OBJECT_TYPE", "DECAY_DATE"])
    d = d.merge(sat, left_on="cospar", right_on="OBJECT_ID", how="left")
    # an event = one object (or, without a COSPAR ID, one country and date)
    d["event"] = d.cospar.fillna("?" + d.country.fillna("") + "|" + d.date.fillna("") + "|" + d.lat.round(0).astype(str))
    lim = d.INCLINATION.where(d.INCLINATION <= 90, 180 - d.INCLINATION)
    d["impossible"] = d.lat.abs() > lim + 1.0                 # found further from the equator than the orbit reaches
    return d


def expected(c, ids, pop, land, ev):
    E = {"land": np.zeros(len(c) + 1), "pop": np.zeros(len(c) + 1)}
    for inc in ev.INCLINATION:
        p = band(inc)[:, None] / NX                           # impact probability per cell (uniform longitude)
        for k, w in (("land", land), ("pop", pop)):
            e = np.bincount(ids.ravel(), weights=(p * w).ravel(), minlength=len(c) + 1)
            E[k] += e / e[1:].sum()
    return E


ALIAS = {"United States": "United States of America", "USA": "United States of America", "Czech Republic": "Czechia",
         "Ivory Coast": "Côte d'Ivoire", "Russia": "Russia", "UK": "United Kingdom"}

if __name__ == "__main__":
    c, ids, pop, land, source = grids()
    d = events()
    ev = d.sort_values("date").groupby("event").first().reset_index()
    ev["country"] = ev.country.map(lambda x: ALIAS.get(x, x))
    print(f"population: {source}")
    print(f"fragments {len(d)}, events {len(ev)}, with orbit {ev.INCLINATION.notna().sum()}")
    bad = d[d.impossible].drop_duplicates("event")
    print(f"QA: {len(bad)} events have fragments beyond their orbit's latitude reach:")
    print(bad[["cospar", "name", "date", "country", "lat", "INCLINATION"]].to_string(index=False))
    use = ev[ev.INCLINATION.notna() & ~ev.event.isin(bad.event)]
    unmatched = sorted(set(use.country) - set(c.NAME)); print("unmatched countries:", unmatched)
    out = {}
    for tag, sel in (("all", use), ("no_dedicated_searches", use[~use.cospar.isin(DEDICATED)])):
        E = expected(c, ids, pop, land, sel)
        t = pd.DataFrame({"country": c.NAME, "iso": c.ISO_A3_EH, "economy": c.ECONOMY, "income": c.INCOME_GRP,
                          "pop": c.POP_EST, "gdp_pc": c.GDP_MD * 1e6 / c.POP_EST,
                          "exp_land": E["land"][1:], "exp_pop": E["pop"][1:]})
        t["obs"] = t.country.map(sel.country.value_counts()).fillna(0)
        t["obs_over_pop"] = t.obs / t.exp_pop
        out[tag] = t
        n = len(sel)
        print(f"\n== {tag}: {n} events")
        print(t.sort_values("exp_pop", ascending=False).head(12)[["country", "obs", "exp_pop", "exp_land", "obs_over_pop"]].round(2).to_string(index=False))
        rich = t.income.str[:1].astype(int) <= 2
        for k in ("obs", "exp_pop", "exp_land"):
            print(f"  high-income share of {k:8s}: {t.loc[rich, k].sum() / t[k].sum():.2f}")
        t.to_csv(f"country_{tag}.csv", index=False)
    use.to_csv("events_used.csv", index=False)
