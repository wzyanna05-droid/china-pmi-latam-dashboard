"""
robustness_v2.py  -  Improvements 2 and 5

2. Dollar control: does last month's PMI change still matter once this month's US dollar
   move is accounted for?   return_t = a + b1 * PMIchange_(t-1) + b2 * USDreturn_t
5. Out-of-sample: fit  return_t = a + b * PMIchange_(t-1)  on Dec 2016 - Dec 2022, then
   predict Jan 2023 - Oct 2026. Out-of-sample R^2 compares the model with simply
   predicting the training-period average return (positive = PMI helped; negative = worse).

Each test is run on all months and with the COVID shock excluded (Feb-Mar 2020 PMI changes,
Feb-Apr 2020 returns), matching the dashboard switch.

Input : latam_monthly.csv + FRED DTWEXBGS (Broad US Dollar Index, daily -> month-end)
Output: usd_index_monthly.csv, robustness_results.csv   (new files only)
p-values use a normal approximation (no scipy/statsmodels needed).
"""
import io
import math
import sys

import numpy as np
import pandas as pd
import requests

TRAIN_END = "2022-12"
COVID_PMI = ["2020-02", "2020-03"]
COVID_RET = ["2020-02", "2020-03", "2020-04"]

df = pd.read_csv("latam_monthly.csv", parse_dates=["month"]).sort_values("month").reset_index(drop=True)
ym = df["month"].dt.strftime("%Y-%m")

# ---------- US dollar index from FRED ----------
print("Fetching Broad US Dollar Index from FRED (DTWEXBGS, daily)...")
try:
    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS", timeout=30)
    r.raise_for_status()
    u = pd.read_csv(io.StringIO(r.text))
    u = pd.DataFrame({"date": pd.to_datetime(u.iloc[:, 0], errors="coerce"),
                      "usd": pd.to_numeric(u.iloc[:, 1], errors="coerce")}).dropna()
    if u.empty:
        raise ValueError("no rows")
except Exception as e:
    print(f"STOPPED: dollar index download failed ({type(e).__name__}: {e}). Nothing written.")
    sys.exit(1)
u["month"] = u["date"].dt.to_period("M").dt.to_timestamp()
usd = u.sort_values("date").groupby("month", as_index=False)["usd"].last()
df = df.merge(usd, on="month", how="left")
if df["usd"].isna().any():
    print(f"Note: dollar index missing for {df['usd'].isna().sum()} month(s).")
usd.assign(month=usd["month"].dt.strftime("%Y-%m")).to_csv("usd_index_monthly.csv", index=False)

# ---------- variables ----------
ret = {"Copper": df["copper_price"].pct_change() * 100}
for c in ["CLP", "MXN", "BRL"]:
    ret[f"{c} vs USD"] = (df[f"usd{c.lower()}"].shift(1) / df[f"usd{c.lower()}"] - 1) * 100
usd_ret = df["usd"].pct_change() * 100                      # + = dollar stronger
pmi_lag = df["manufacturing_pmi"].diff().shift(1)           # PMI change last month


def mask(s, months):
    return s.mask(ym.isin(months))


def ols(y, X):
    """OLS with intercept. Returns coefs, std errors, n."""
    d = pd.concat([y] + X, axis=1).dropna()
    yv = d.iloc[:, 0].to_numpy()
    Xv = np.column_stack([np.ones(len(d))] + [d.iloc[:, i].to_numpy() for i in range(1, d.shape[1])])
    beta, *_ = np.linalg.lstsq(Xv, yv, rcond=None)
    resid = yv - Xv @ beta
    sigma2 = resid @ resid / (len(d) - Xv.shape[1])
    se = np.sqrt(np.diag(sigma2 * np.linalg.inv(Xv.T @ Xv)))
    return beta, se, len(d), d.index


def pval(b, se):
    return math.erfc(abs(b / se) / math.sqrt(2))


rows = []
for excl in (False, True):
    sample = "excl. COVID" if excl else "all months"
    x = mask(df["manufacturing_pmi"].diff(), COVID_PMI).shift(1) if excl else pmi_lag
    for m, y0 in ret.items():
        y = mask(y0, COVID_RET) if excl else y0
        # --- 2. dollar control ---
        b0, se0, n0, _ = ols(y, [x])
        b1, se1, n1, _ = ols(y, [x, usd_ret])
        # --- 5. out-of-sample ---
        train = df["month"] <= pd.Timestamp(TRAIN_END + "-01")
        bt, _, ntr, _ = ols(y.where(train), [x.where(train)])
        test = pd.concat([y, x], axis=1).where(~train).dropna()
        pred = bt[0] + bt[1] * test.iloc[:, 1]
        sse_model = ((test.iloc[:, 0] - pred) ** 2).sum()
        train_mean = y.where(train).dropna().mean()
        sse_mean = ((test.iloc[:, 0] - train_mean) ** 2).sum()
        oos_r2 = 1 - sse_model / sse_mean
        r_test = test.iloc[:, 0].corr(test.iloc[:, 1])
        rows.append({
            "sample": sample, "market": m,
            "pmi_coef_no_control": round(b0[1], 3), "p_no_control": round(pval(b0[1], se0[1]), 3),
            "pmi_coef_with_usd": round(b1[1], 3), "p_with_usd": round(pval(b1[1], se1[1]), 3),
            "usd_coef": round(b1[2], 3), "p_usd": round(pval(b1[2], se1[2]), 4), "n": n1,
            "train_slope": round(bt[1], 3), "n_train": ntr, "n_test": len(test),
            "test_period_r": round(r_test, 3), "oos_r2_pct": round(oos_r2 * 100, 2),
        })

res = pd.DataFrame(rows)
res.to_csv("robustness_results.csv", index=False)
pd.set_option("display.width", 200)
print(f"\nTraining: Dec 2016 - {TRAIN_END}; test: {TRAIN_END[:4]}+1 to {df['month'].max():%Y-%m}")
print("\n=== 2. Dollar control (PMI coefficient = % return per 1-point PMI change last month) ===")
print(res[["sample", "market", "pmi_coef_no_control", "p_no_control", "pmi_coef_with_usd", "p_with_usd",
           "usd_coef", "p_usd", "n"]].to_string(index=False))
print("\n=== 5. Out-of-sample (2023 onwards) ===")
print(res[["sample", "market", "train_slope", "n_train", "n_test", "test_period_r", "oos_r2_pct"]].to_string(index=False))
print("\nSaved: usd_index_monthly.csv, robustness_results.csv")
