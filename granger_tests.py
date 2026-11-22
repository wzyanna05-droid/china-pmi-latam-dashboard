"""
granger_tests.py  -  Improvement 3: Granger causality tests in both directions

Question: do past values of X help predict Y beyond Y's own past?
   restricted:   Y_t = c + sum_{i=1..p} a_i Y_{t-i}
   unrestricted: Y_t = c + sum a_i Y_{t-i} + sum_{i=1..p} b_i X_{t-i}
   F-test on the b_i (same 'ssr F-test' as statsmodels; verified identical on test data).

Pairs (monthly, Nov 2016 - Oct 2026):
  China -> markets : Mfg PMI change / NBS new-orders change  ->  copper, CLP, MXN, BRL returns
  markets -> China : the reverse direction (do markets move first?)
  CLP <-> copper   : commodity-currency question from the literature
Lags p = 1, 2, 3.  Each run on all months and with the COVID shock excluded
(Feb-Mar 2020 PMI changes and Feb-Apr 2020 returns set to missing; affected rows dropped).

Input : latam_monthly_plus.csv      Output: granger_results.csv (new file)
p-values: exact F distribution (incomplete beta), no scipy/statsmodels needed.
"""
import math

import numpy as np
import pandas as pd


def _betacf(a, b, x, itmax=500, eps=3e-14):
    """Continued fraction for the incomplete beta function (Numerical Recipes)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c; c = c if abs(c) > 1e-300 else 1e-300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c; c = c if abs(c) > 1e-300 else 1e-300
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h

def betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * _betacf(b, a, 1 - x) / b

def f_sf(F, d1, d2):
    """P(F_{d1,d2} > F)."""
    if F <= 0: return 1.0
    return betainc(d2 / 2.0, d1 / 2.0, d2 / (d2 + d1 * F))


def granger(y, x, p):
    """Does x Granger-cause y?  Compares
         restricted:   y_t = c + sum_{i=1..p} a_i y_{t-i}
         unrestricted: y_t = c + sum a_i y_{t-i} + sum_{i=1..p} b_i x_{t-i}
       F = ((RSS_r - RSS_u)/p) / (RSS_u/(n - 2p - 1)).  Rows with any missing value are dropped.
       Returns F, p-value, n."""
    d = pd.DataFrame({"y": y})
    for i in range(1, p + 1):
        d[f"y{i}"] = y.shift(i)
        d[f"x{i}"] = x.shift(i)
    d = d.dropna()
    n = len(d)
    Y = d["y"].to_numpy()
    Xr = np.column_stack([np.ones(n)] + [d[f"y{i}"].to_numpy() for i in range(1, p + 1)])
    Xu = np.column_stack([Xr] + [d[f"x{i}"].to_numpy() for i in range(1, p + 1)])
    rss = lambda X: float(((Y - X @ np.linalg.lstsq(X, Y, rcond=None)[0]) ** 2).sum())
    rss_r, rss_u = rss(Xr), rss(Xu)
    df2 = n - Xu.shape[1]
    F = ((rss_r - rss_u) / p) / (rss_u / df2)
    return F, f_sf(F, p, df2), n


COVID_PMI = ["2020-02", "2020-03"]
COVID_RET = ["2020-02", "2020-03", "2020-04"]
LAGS = (1, 2, 3)

df = pd.read_csv("latam_monthly_plus.csv", parse_dates=["month"]).sort_values("month").reset_index(drop=True)
if (df["month"].dt.to_period("M").astype(int).diff().dropna() != 1).any():
    raise SystemExit("STOPPED: gap in the monthly series.")
ym = df["month"].dt.strftime("%Y-%m")

china = {"Mfg PMI change": df["manufacturing_pmi"].diff(),
         "New orders change": df["new_orders_index"].diff()}
markets = {"Copper return": df["copper_price"].pct_change() * 100}
for c in ["CLP", "MXN", "BRL"]:
    markets[f"{c} return"] = (df[f"usd{c.lower()}"].shift(1) / df[f"usd{c.lower()}"] - 1) * 100


def prep(s, kind, excl):
    if not excl:
        return s
    return s.mask(ym.isin(COVID_PMI if kind == "china" else COVID_RET))


rows = []
for excl in (False, True):
    sample = "excl. COVID" if excl else "all months"
    pairs = []
    for cn, cs in china.items():
        for mn, ms in markets.items():
            pairs.append(("China -> market", cn, mn, prep(cs, "china", excl), prep(ms, "mkt", excl)))
            pairs.append(("market -> China", mn, cn, prep(ms, "mkt", excl), prep(cs, "china", excl)))
    clp, cu = prep(markets["CLP return"], "mkt", excl), prep(markets["Copper return"], "mkt", excl)
    pairs.append(("CLP <-> copper", "CLP return", "Copper return", clp, cu))
    pairs.append(("CLP <-> copper", "Copper return", "CLP return", cu, clp))
    for direction, xname, yname, x, y in pairs:
        for p in LAGS:
            F, pv, n = granger(y, x, p)
            rows.append({"sample": sample, "direction": direction, "x_predictor": xname, "y_predicted": yname,
                         "lags": p, "F": round(F, 3), "p_value": round(pv, 4), "n": n})

res = pd.DataFrame(rows)
n_per_sample = len(res) // 2
bonf = 0.05 / n_per_sample
res["significant_p05"] = res["p_value"] < 0.05
res["significant_bonferroni"] = res["p_value"] < bonf
res.to_csv("granger_results.csv", index=False)

pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 300)
for sample in ("all months", "excl. COVID"):
    s = res[res["sample"] == sample]
    print(f"\n===== {sample}: {len(s)} tests, {s['significant_p05'].sum()} at p<0.05 "
          f"(~{0.05 * len(s):.1f} expected by chance), {s['significant_bonferroni'].sum()} after Bonferroni "
          f"(p<{bonf:.5f}) =====")
    piv = s.pivot_table(index=["direction", "x_predictor", "y_predicted"], columns="lags", values="p_value")
    piv.columns = [f"p (lags={c})" for c in piv.columns]
    print(piv.round(3).to_string())
print("\nSaved: granger_results.csv")
