"""
analyzer_v2.py  -  Niche Alpha project, Week 2 analysis (version 2)

Question: are changes in China's manufacturing PMI associated with copper
returns in the SAME month, or do they lead copper returns by ONE month?

Input : pmi_copper_matched.csv  (month, manufacturing_pmi, copper_price in US cents/lb)
Output: lag_results.csv, pmi_vs_copper_returns.png, pmi_copper_lag_scatter.png
        (new files only; nothing existing is overwritten)

Timing note: NBS publishes month t's PMI on the last day of month t (or the 1st of t+1),
so pairing PMI(t) with the copper return over month t+1 uses only information that was
already public when that return period began.
"""
import math

import matplotlib.pyplot as plt
import pandas as pd

df = pd.read_csv("pmi_copper_matched.csv", parse_dates=["month"]).sort_values("month")

# Make sure the months are consecutive before shifting anything
gaps = (df["month"].dt.to_period("M").astype(int).diff().dropna() != 1).sum()
if gaps:
    raise SystemExit(f"STOPPED: {gaps} gap(s) in the monthly series - fix before shifting.")

# Variables
df["copper_return_pct"] = df["copper_price"].pct_change() * 100          # return over month t
df["pmi_change"] = df["manufacturing_pmi"].diff()                         # PMI(t) - PMI(t-1)
df["copper_return_next_pct"] = df["copper_return_pct"].shift(-1)         # return over month t+1


def corr_test(x, y):
    """Pearson r, n and an approximate two-sided p-value (normal approximation to t)."""
    d = pd.concat([x, y], axis=1).dropna()
    n = len(d)
    r = d.iloc[:, 0].corr(d.iloc[:, 1])
    t = r * math.sqrt((n - 2) / (1 - r ** 2))
    p = math.erfc(abs(t) / math.sqrt(2))
    return round(r, 3), n, round(p, 3)


tests = {
    "Same month: PMI change(t) vs copper return(t)":
        (df["pmi_change"], df["copper_return_pct"]),
    "1-month lead: PMI change(t) vs copper return(t+1)":
        (df["pmi_change"], df["copper_return_next_pct"]),
    "Same month: PMI level(t) vs copper return(t)":
        (df["manufacturing_pmi"], df["copper_return_pct"]),
    "1-month lead: PMI level(t) vs copper return(t+1)":
        (df["manufacturing_pmi"], df["copper_return_next_pct"]),
}

rows = []
for name, (x, y) in tests.items():
    r, n, p = corr_test(x, y)
    rows.append({"test": name, "pearson_r": r, "n_months": n, "p_value_approx": p})
results = pd.DataFrame(rows)

# Spot-check the lag pairing so it can be verified by eye
check = df[["month", "pmi_change", "copper_return_next_pct"]].dropna().head(3)

print(f"Data: {df['month'].min():%Y-%m} to {df['month'].max():%Y-%m}, {len(df)} months\n")
print(results.to_string(index=False))
print("\nLag pairing check (PMI change in 'month' is paired with copper return in the NEXT month):")
print(check.to_string(index=False))
results.to_csv("lag_results.csv", index=False)

# Chart 1: PMI vs copper returns over time
fig, ax1 = plt.subplots(figsize=(12, 5))
ax1.plot(df["month"], df["manufacturing_pmi"], color="tab:red", label="China manufacturing PMI")
ax1.axhline(50, color="tab:red", linestyle=":", linewidth=1)
ax1.set_ylabel("PMI (50 = no change)")
ax2 = ax1.twinx()
ax2.bar(df["month"], df["copper_return_pct"], width=20, color="tab:blue", alpha=0.4,
        label="Copper monthly return (%)")
ax2.set_ylabel("Copper return, % (COMEX HG)")
ax1.set_title("China manufacturing PMI and COMEX copper monthly returns")
fig.legend(loc="upper left", bbox_to_anchor=(0.07, 0.92))
fig.tight_layout()
fig.savefig("pmi_vs_copper_returns.png", dpi=150)

# Chart 2: lag scatter
lag = df[["pmi_change", "copper_return_next_pct"]].dropna()
r_lag = results.loc[1, "pearson_r"]
fig, ax = plt.subplots(figsize=(6, 5))
ax.scatter(lag["pmi_change"], lag["copper_return_next_pct"], alpha=0.6)
ax.axhline(0, color="grey", linewidth=0.8)
ax.axvline(0, color="grey", linewidth=0.8)
ax.set_xlabel("PMI change in month t (points)")
ax.set_ylabel("Copper return in month t+1 (%)")
ax.set_title(f"Does PMI lead copper by one month?  r = {r_lag}, n = {len(lag)}")
fig.tight_layout()
fig.savefig("pmi_copper_lag_scatter.png", dpi=150)

print("\nSaved: lag_results.csv, pmi_vs_copper_returns.png, pmi_copper_lag_scatter.png")
