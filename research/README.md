# Fallen: research

Is the record of space debris found on the ground a record of risk, or of who is looking?

## Data
- `esa_recovered.csv`: ESA re-entry portal, "Recovered debris" table (235 fragments, 99 events, 1962–2025).
  Source: https://reentry.esoc.esa.int/home/recovereddebris (public JSON, snapshot of 2026-10-24, `raw/esa_api_home.json`,
  sha256 eb31b0df…). ESA states the list makes no claim to completeness.
- `raw/satcat.csv`: CelesTrak SATCAT (inclination, owner), via github.com/astrion-tech/celestrak-mirror.
- `pop_grid.npz`: GHS-POP 2020 (JRC, CC BY 4.0) summed to 0.25°, made by `agg_pop.py`.
- `countries.geojson`: Natural Earth 1:50m admin-0 (borders, population, GDP, World Bank income group).

## Method
- **Events.** Each recovered event is one object, so 4–500 fragments from one re-entry count once.
- **Expected finds.** Each event's orbit sets the latitudes it can reach, in proportion to time spent at each:
  P(lat < φ) = ½ + arcsin(sin φ / sin i)/π. Longitude is taken as uniform.
- **Two models.** Expected finds per country are computed (a) on land area and (b) on population.
- **Comparison.** Observed vs expected by World Bank income group (binomial test), and a country-level Poisson/negative
  binomial regression of finds on log exposure and log GDP per capita.
- **Exclusions.**
  - Two events with fragments beyond their orbit's latitude reach (QA flags).
  - 19 events with no catalogued orbit.
- **Sensitivity.** A rerun without the four large dedicated searches (Cosmos 954, Skylab, Salyut 7, Columbia).

## First results (75 events, dedicated searches removed, GHS-POP)
- **Income gap.** High-income countries hold 43% of recorded events but only 12% of population-weighted
  exposure (3.6×, p ≈ 2e-11) and 24% of land exposure (1.8×, p ≈ 2e-4).
- **Wealth effect.** At equal exposure, a 10× richer country has ≈2.8× more recorded finds
  (negative binomial: 0.44 per log GDP pc, 95% CI 0.20–0.68).
- **Over time.** The gap holds before 2010 (45% vs 10%) and since 2010 (38% vs 14%).
- **Largest gaps.** India has 4 finds against ≈15 expected. China, Pakistan, Nigeria and Bangladesh have none against ≈13, 2.4, 2.3 and 1.9 expected.

## Caveats
- **Source.** ESA's list is compiled from papers, government documents and news. Language and media reach are part of the bias being measured, not separable from it.
- **Sample size.** It is small (75 events).
- **Orbits.** The inclination is the last catalogued orbit, and longitude is assumed uniform.
- **China.** Launch-phase drops of stages over China's interior are not orbital re-entries and are not in this list.

## Multilingual news check (2026-11-04)
I searched news in Hindi, Portuguese, Spanish, Indonesian, French, Arabic, Vietnamese, Swahili, Tagalog, Thai, Urdu, Bengali,
Persian, Russian, Turkish and Chinese, and checked every find against ESA's list (`extra_events.csv`, with sources).
- **Missing from ESA, before its snapshot, all in middle- or low-income countries:**
  - Indonesia 2003: CZ-3A R/B 1994-080B (strong).
  - Indonesia 2007: Okean-3 debris 1991-039C (strong).
  - Thailand 2017: 14 pieces, confirmed re-entry by GISTDA, object unidentified.
  - Uganda 2023: reported, attribution weak.
  - Kazakhstan 2018: weak.
- **English control.** Maley's English-language list gave no confirmed orbital land finds missing from ESA.
- **Since the snapshot:** Indonesia, Oct 2026 (Zhuque-2E, BRIN) and USA, Oct 2026 (Zhuque-2E upper stage).
- **Effect on the result.** Adding the strong cases leaves it unchanged: high-income 42% of events vs 12% of exposure, GDP coefficient 0.44.
- **What the gaps show.** The misses are the direction the hypothesis predicts. ESA's compilation under-records finds reported only in local languages.
