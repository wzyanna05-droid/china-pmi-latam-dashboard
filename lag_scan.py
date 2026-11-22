"""
lag_scan.py  -  Improvements 1 and 4

1. Lag scan: correlation between China PMI changes in month t-k and each market's
   return in month t, for k = 0..6, using six PMI versions (incl. NBS new order index).
4. Stability: rolling 36-month correlation for the one-month lead.

Input : latam_monthly_plus.csv (latam_monthly.csv + NBS new order index from fetch_new_orders_nbs.py)
Output: lag_scan_results.csv, rolling_correlation.csv,
        lag_profile.png, rolling_correlation.png          (new files only)

Note on multiple testing: this runs 6 indicators x 4 markets x 7 lags = 168 tests.
At p < 0.05 about 8-9 'significant' results are expected by chance alone, so the
script also reports a Bonferroni-adjusted threshold (0.05 / 168).
"""
import math

import matplotlib.pyplot as plt
import pandas as pd

MAX_LAG = 6
WINDOW = 36

df = pd.read_csv("latam_monthly_plus.csv", parse_dates=["month"]).sort_values("month").reset_index(drop=True)
if (df["month"].dt.to_period("M").astype(int).diff().dropna() != 1).any():
    raise SystemExit("STOPPED: gap in the monthly series.")

# Market returns (currencies: + = LATAM currency stronger vs USD)
ret = {"Copper": df["copper_price"].pct_change() * 100}
for ccy in ["CLP", "MXN", "BRL"]:
    ret[f"{ccy} vs USD"] = (df[f"usd{ccy.lower()}"].shift(1) / df[f"usd{ccy.lower()}"] - 1) * 100

# PMI versions: monthly change of each
ind = {
    "Mfg PMI": df["manufacturing_pmi"].diff(),
    "Mfg PMI (3-month avg)": df["manufacturing_pmi"].rolling(3).mean().diff(),
    "Non-mfg PMI": df["nonmanufacturing_pmi"].diff(),
    "Non-mfg PMI (3-month avg)": df["nonmanufacturing_pmi"].rolling(3).mean().diff(),
    "New orders": df["new_orders_index"].diff(),
    "New orders (3-month avg)": df["new_orders_index"].rolling(3).mean().diff(),
}
if df["new_orders_index"].isna().any():
    raise SystemExit("STOPPED: new_orders_index has missing months - rerun fetch_new_orders_nbs.py.")


def corr(x, y):
    d = pd.concat([x, y], axis=1).dropna()
    n = len(d)
    r = d.iloc[:, 0].corr(d.iloc[:, 1])
    t = r * math.sqrt((n - 2) / (1 - r ** 2))
    return r, n, math.erfc(abs(t) / math.sqrt(2))


rows = []
for iname, x in ind.items():
    for mname, y in ret.items():
        for k in range(MAX_LAG + 1):
            r, n, p = corr(x.shift(k), y)
            rows.append({"indicator": iname, "market": mname, "lead_months": k,
                         "pearson_r": round(r, 3), "n_months": n, "p_value_approx": round(p, 4)})
res = pd.DataFrame(rows)
n_tests = len(res)
bonf = 0.05 / n_tests
res["significant_p05"] = res["p_value_approx"] < 0.05
res["significant_bonferroni"] = res["p_value_approx"] < bonf
res.to_csv("lag_scan_results.csv", index=False)

# Rolling 36-month correlation, 1-month lead, headline manufacturing PMI
roll = pd.DataFrame({"month": df["month"]})
for mname, y in ret.items():
    roll[mname] = ind["Mfg PMI"].shift(1).rolling(WINDOW).corr(y)
roll = roll.dropna(how="all", subset=list(ret))
roll.assign(month=roll["month"].dt.strftime("%Y-%m")).round(3).to_csv("rolling_correlation.csv", index=False)

# ---- Chart 1: lag profiles (headline vs 3-month avg, manufacturing) ----
fig, axes = plt.subplots(1, len(ret), figsize=(16, 4), sharey=True)
for ax, mname in zip(axes, ret):
    for iname, style in [("Mfg PMI", "-o"), ("Mfg PMI (3-month avg)", "--s"), ("New orders", ":^")]:
        s = res[(res["indicator"] == iname) & (res["market"] == mname)]
        ax.plot(s["lead_months"], s["pearson_r"], style, label=iname)
        sig = s[s["significant_p05"]]
        ax.scatter(sig["lead_months"], sig["pearson_r"], s=120, facecolors="none", edgecolors="black")
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.set_title(mname)
    ax.set_xlabel("PMI lead (months)")
axes[0].set_ylabel("Pearson r")
axes[0].legend(fontsize=8)
fig.suptitle("Lag profile: China PMI change k months earlier vs market return (circled: p < 0.05, unadjusted)")
fig.tight_layout()
fig.savefig("lag_profile.png", dpi=150)

# ---- Chart 2: rolling correlation ----
fig, ax = plt.subplots(figsize=(12, 4.5))
for mname in ret:
    ax.plot(roll["month"], roll[mname], label=mname)
ax.axhline(0, color="grey", linewidth=0.8)
ax.set_ylabel(f"Rolling {WINDOW}-month r")
ax.set_title(f"Stability check: rolling {WINDOW}-month correlation, Mfg PMI change (t-1) vs return (t)")
ax.legend()
fig.tight_layout()
fig.savefig("rolling_correlation.png", dpi=150)

# ---- Summary ----
print(f"Data {df['month'].min():%Y-%m} to {df['month'].max():%Y-%m}; {n_tests} tests; "
      f"Bonferroni threshold p < {bonf:.5f}")
print(f"Significant at p<0.05: {res['significant_p05'].sum()} (about {0.05 * n_tests:.1f} expected by chance)")
print(f"Significant after Bonferroni: {res['significant_bonferroni'].sum()}")
print("\nStrongest |r| per market:")
best = res.loc[res.groupby("market")["pearson_r"].apply(lambda s: s.abs().idxmax())]
print(best.to_string(index=False))
# COVID robustness for the new orders index (drop Feb-Mar 2020 changes, Feb-Apr 2020 returns)
ym = df["month"].dt.strftime("%Y-%m")
no_ex = df["new_orders_index"].diff().mask(ym.isin(["2020-02", "2020-03"]))
print("\nNew orders, 1-month lead: all months vs excluding COVID shock")
for mname, y in ret.items():
    ra, na, pa = corr(ind["New orders"].shift(1), y)
    rx, nx, px_ = corr(no_ex.shift(1), y.mask(ym.isin(["2020-02", "2020-03", "2020-04"])))
    print(f"  {mname:11} all: r={ra:+.3f} p={pa:.3f} n={na} | excl. COVID: r={rx:+.3f} p={px_:.3f} n={nx}")
print("\nRolling 36-month r (1-month lead, Mfg PMI): min / max per market")
print(roll[list(ret)].agg(["min", "max"]).round(2).to_string())
print("\nSaved: lag_scan_results.csv, rolling_correlation.csv, lag_profile.png, rolling_correlation.png")
