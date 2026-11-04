import numpy as np, pandas as pd, statsmodels.api as sm
from scipy.stats import binomtest
for tag in ("all", "no_dedicated_searches"):
    t = pd.read_csv(f"country_{tag}.csv"); n = int(t.obs.sum())
    rich = t.income.str[:1].astype(int) <= 2; k = int(t.loc[rich, "obs"].sum())
    for m in ("exp_pop", "exp_land"):
        p = t.loc[rich, m].sum() / t[m].sum()
        print(tag, m, f"high-income {k}/{n} observed vs {p:.2f} expected -> x{k/n/p:.1f}, p={binomtest(k, n, p, alternative='greater').pvalue:.1e}")
    # Poisson regression across countries: does wealth predict finds beyond exposure?
    u = t[(t.exp_land > 0) & t.gdp_pc.notna() & (t.gdp_pc > 0)].copy()
    X = pd.DataFrame({"log_exp_land": np.log(u.exp_land), "log_pop_ratio": np.log(u.exp_pop / u.exp_land + 1e-9),
                      "log_gdp_pc": np.log(u.gdp_pc)}); X = sm.add_constant(X)
    r = sm.GLM(u.obs, X, family=sm.families.Poisson()).fit(cov_type="HC0")
    print(r.summary().tables[1])
