# Fallen

A live map of satellites and rocket bodies coming back to Earth. It shows:
- where each one can fall during its prediction window,
- who lives under that path,
- which debris has actually reached the ground, with sources.

**Site:** https://tilakkumar13.github.io/fallen/

| | |
|---|---|
| Live map and tracks | every active satellite, positions computed in your browser (SGP4, satellite.js) |
| Coming down | objects expected to re-enter, soonest first, with countdowns |
| Path over the uncertainty window | every stretch of ground it could cross while the window is open, not a fake landing pin |
| Countries and people under the path | GHS-POP 2020 population within 50 km of the path, by country |
| Debris actually found | ESA's recovered-debris list plus finds reported only in local-language news, each linked to its source |

## Data
- **Orbits:** [CelesTrak](https://celestrak.org) (active satellites, decaying objects, SATCAT), refreshed every 3 hours by a scheduled GitHub Action.
- **Prediction windows:** [The Aerospace Corporation](https://aerospace.org/reentries) where available. Otherwise a rough estimate: SGP4 with the orbit's drag term, ±20% of the time left.
- **Population:** JRC [GHS-POP 2020](https://human-settlement.emergency.copernicus.eu/) (CC BY 4.0), summed to 0.25°.
- **Finds:** [ESA re-entry portal, recovered debris](https://reentry.esoc.esa.int/home/recovereddebris), snapshot of 24 Oct 2026, plus a 16-language news search (`research/extra_events.csv`).

## Research
`research/` holds the analysis behind the "Fallen" layer. High-income countries hold 43% of recorded finds
but only 12% of the exposure their orbits put over people (75 events, 1962–2025). Method and caveats are in `research/README.md`.

## Run it
```
pip install sgp4 numpy
python pipeline/update.py        # writes docs/data/live.json and docs/data/sky.tle
python -m http.server -d docs    # open http://localhost:8000
```

Not an official warning service. For decisions, use your national space agency or ESA.
