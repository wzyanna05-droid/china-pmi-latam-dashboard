"""
latam_heatmap.py  -  Niche Alpha project, Week 2 heatmap

Which Chinese indicators move with which LATAM markets?

Rows    (China): change in NBS manufacturing PMI and non-manufacturing PMI,
                 same month (t) and previous month (t-1)
Columns (LATAM): monthly % return of COMEX copper, and of the Chilean peso (CLP),
                 Mexican peso (MXN) and Brazilian real (BRL) against the US dollar
                 (positive = the LATAM currency STRENGTHENED)

Inputs : pmi_copper_matched.csv (from data_fetcher_v2.py), non-mfg PMI via AkShare,
         currencies from FRED (MXN, BRL daily month-end; CLP OECD monthly average)
Outputs: latam_monthly.csv, heatmap_results.csv, correlation_heatmap.png  (new files only)

A currency that cannot be downloaded is reported and left out - never substituted.
Heatmap is drawn with matplotlib (no extra install needed).
"""
import math
import re
import sys

import io

import akshare as ak
import requests
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

START = "2016-11-01"


def stop(msg):
    print(f"STOPPED: {msg}")
    sys.exit(1)


def to_month(text):
    m = re.search(r"(\d{4})\D+(\d{1,2})", str(text))
    return pd.Timestamp(int(m.group(1)), int(m.group(2)), 1) if m else pd.NaT


# ---------- 1. China indicators ----------
base = pd.read_csv("pmi_copper_matched.csv", parse_dates=["month"])

print("Fetching China NBS non-manufacturing PMI (AkShare)...")
try:
    raw = ak.macro_china_pmi()
except Exception as e:
    stop(f"PMI download failed: {e}")
if "非制造业-指数" not in raw.columns:
    stop(f"PMI table has unexpected columns: {list(raw.columns)}")
nonmfg = pd.DataFrame({
    "month": raw["月份"].map(to_month),
    "nonmanufacturing_pmi": pd.to_numeric(raw["非制造业-指数"], errors="coerce"),
}).dropna()
df = base.merge(nonmfg, on="month", how="left")

# ---------- 2. LATAM currencies vs USD (FRED, St. Louis Fed - free, no sign-up) ----------
# MXN, BRL: daily rates (Fed H.10)  -> last trading day of each month (same as copper)
# CLP     : OECD monthly AVERAGE of daily rates (no daily CLP series on FRED) - noted on chart
fx_wanted = {
    "CLP": ("CCUSMA02CLM618N", "monthly average"),
    "MXN": ("DEXMXUS", "daily"),
    "BRL": ("DEXBZUS", "daily"),
}
missing = []
for ccy, (sid, kind) in fx_wanted.items():
    print(f"Fetching {ccy} per USD from FRED ({sid}, {kind})...")
    try:
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=30)
        r.raise_for_status()
        fx = pd.read_csv(io.StringIO(r.text))
        fx = pd.DataFrame({"date": pd.to_datetime(fx.iloc[:, 0], errors="coerce"),
                           "rate": pd.to_numeric(fx.iloc[:, 1], errors="coerce")}).dropna()
        if fx.empty:
            raise ValueError("no rows returned")
    except Exception as e:
        print(f"  -> {ccy} NOT available ({type(e).__name__}: {e}). Left out, nothing substituted.")
        missing.append(ccy)
        continue
    fx["month"] = fx["date"].dt.to_period("M").dt.to_timestamp()
    monthly = fx.sort_values("date").groupby("month", as_index=False)["rate"].last()
    monthly = monthly.rename(columns={"rate": f"usd{ccy.lower()}"})
    df = df.merge(monthly, on="month", how="left")
    print(f"  -> {ccy}: {monthly['month'].min():%Y-%m} to {monthly['month'].max():%Y-%m}")

df = df[df["month"] >= START].sort_values("month").reset_index(drop=True)
if (df["month"].dt.to_period("M").astype(int).diff().dropna() != 1).any():
    stop("gap in the monthly series - fix before shifting.")

# ---------- 3. Variables ----------
cols = {"Copper": df["copper_price"].pct_change() * 100}
for ccy in fx_wanted:
    c = f"usd{ccy.lower()}"
    if c in df:
        # LATAM currency return vs USD: + means the LATAM currency strengthened
        cols[f"{ccy} vs USD"] = (df[c].shift(1) / df[c] - 1) * 100
rows = {
    "Mfg PMI change (t)":          df["manufacturing_pmi"].diff(),
    "Mfg PMI change (t-1)":        df["manufacturing_pmi"].diff().shift(1),
    "Non-mfg PMI change (t)":      df["nonmanufacturing_pmi"].diff(),
    "Non-mfg PMI change (t-1)":    df["nonmanufacturing_pmi"].diff().shift(1),
}

R = pd.DataFrame(index=rows, columns=cols, dtype=float)
N = pd.DataFrame(index=rows, columns=cols, dtype="Int64")
P = pd.DataFrame(index=rows, columns=cols, dtype=float)
for rn, x in rows.items():
    for cn, y in cols.items():
        d = pd.concat([x, y], axis=1).dropna()
        n = len(d)
        r = d.iloc[:, 0].corr(d.iloc[:, 1])
        t = r * math.sqrt((n - 2) / (1 - r ** 2))
        R.loc[rn, cn], N.loc[rn, cn], P.loc[rn, cn] = r, n, math.erfc(abs(t) / math.sqrt(2))

# ---------- 4. Save ----------
out = df.copy()
out["month"] = out["month"].dt.strftime("%Y-%m")
out.to_csv("latam_monthly.csv", index=False)
long = (R.stack().rename("pearson_r").to_frame()
        .join(N.stack().rename("n_months")).join(P.stack().rename("p_value_approx")))
long.round(3).to_csv("heatmap_results.csv", index_label=["china_indicator", "latam_market"])

# ---------- 5. Heatmap ----------
fig, ax = plt.subplots(figsize=(1.9 * len(cols) + 3, 4.8))
im = ax.imshow(R.values.astype(float), cmap="RdBu_r", vmin=-0.4, vmax=0.4)
ax.set_xticks(range(len(cols)))
ax.set_xticklabels(cols)
ax.set_yticks(range(len(rows)))
ax.set_yticklabels(rows)
for i in range(len(rows)):
    for j in range(len(cols)):
        r, p = R.iat[i, j], P.iat[i, j]
        ax.text(j, i, f"{r:.2f}" + ("*" if p < 0.05 else ""), ha="center", va="center", fontsize=10)
fig.colorbar(im, ax=ax, label="Pearson r")
ax.set_title(f"China PMI changes vs LATAM monthly returns, "
             f"{df['month'].min():%Y-%m} to {df['month'].max():%Y-%m}\n"
             "* p < 0.05 (approx., not adjusted for multiple tests).  CLP = monthly average rate; MXN, BRL = month-end", fontsize=10)
fig.tight_layout()
fig.savefig("correlation_heatmap.png", dpi=150)

print("\n--- RESULTS (Pearson r) ---")
print(R.round(2).to_string())
print(f"\nMonths per cell: {int(N.min().min())}-{int(N.max().max())}")
if missing:
    print(f"Not available, left out: {', '.join(missing)}")
print("Saved: latam_monthly.csv, heatmap_results.csv, correlation_heatmap.png")
