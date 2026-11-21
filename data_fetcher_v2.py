"""
data_fetcher_v2.py  -  Niche Alpha project, data collection (version 2)

Fetches:
  1. China NBS manufacturing PMI (monthly)        source: AkShare  ak.macro_china_pmi()
  2. COMEX copper futures, front month (HG)       source: Sina Finance via AkShare
     -> monthly close, US cents per pound

Saves NEW files only (never overwrites the original CSVs):
  china_pmi.csv          month, manufacturing_pmi
  copper_monthly.csv     month, copper_price
  pmi_copper_matched.csv month, manufacturing_pmi, copper_price  (one row per matched month)

If a download fails, the script STOPS with a clear message.
It never substitutes sample data or a different series.
"""
import re
import sys

import pandas as pd

START = "2010-01-01"


def stop(msg):
    print(f"STOPPED: {msg}")
    print("No files were written. Nothing was substituted.")
    sys.exit(1)


def to_month(text):
    """'2025年12月份' -> Timestamp('2025-12-01')"""
    m = re.search(r"(\d{4})\D+(\d{1,2})", str(text))
    return pd.Timestamp(int(m.group(1)), int(m.group(2)), 1) if m else pd.NaT


# ---------- 1. China manufacturing PMI ----------
print("Fetching China NBS manufacturing PMI (AkShare)...")
try:
    import akshare as ak
    raw = ak.macro_china_pmi()
except Exception as e:
    stop(f"PMI download failed: {e}")

if "月份" not in raw.columns or "制造业-指数" not in raw.columns:
    stop(f"PMI table has unexpected columns: {list(raw.columns)}")

pmi = pd.DataFrame({
    "month": raw["月份"].map(to_month),
    "manufacturing_pmi": pd.to_numeric(raw["制造业-指数"], errors="coerce"),
}).dropna()
pmi = pmi[pmi["month"] >= START].sort_values("month").reset_index(drop=True)
if pmi.empty:
    stop("PMI table is empty after cleaning.")

# ---------- 2. Copper, monthly ----------
# Source: COMEX copper futures (HG, continuous front month) via Sina Finance, through AkShare.
# Daily closes are reduced to the LAST trading day's close of each month (US cents per lb).
print("Fetching COMEX copper HG (AkShare / Sina Finance)...")
try:
    cu = ak.futures_foreign_hist(symbol="HG")
except Exception as e:
    stop(f"Copper download failed: {e}")

if cu is None or cu.empty or "date" not in cu.columns or "close" not in cu.columns:
    stop(f"Copper table is empty or has unexpected columns: {list(getattr(cu, 'columns', []))}")

cu = cu.assign(date=pd.to_datetime(cu["date"]), close=pd.to_numeric(cu["close"], errors="coerce"))
cu = cu.dropna(subset=["date", "close"]).sort_values("date")
cu["month"] = cu["date"].dt.to_period("M").dt.to_timestamp()
copper = (cu.groupby("month", as_index=False)["close"].last()
            .rename(columns={"close": "copper_price"}))
copper = copper[copper["month"] >= START].reset_index(drop=True)
if copper.empty:
    stop("Copper table is empty after cleaning.")

# ---------- 3. Join on calendar month ----------
matched = pd.merge(pmi, copper, on="month", how="inner").sort_values("month")

# ---------- 4. Save (new filenames only) ----------
for df in (pmi, copper, matched):
    df["month"] = df["month"].dt.strftime("%Y-%m")

pmi.to_csv("china_pmi.csv", index=False)
copper.to_csv("copper_monthly.csv", index=False)
matched.to_csv("pmi_copper_matched.csv", index=False)

print("\n--- RESULTS ---")
print(f"china_pmi.csv          {len(pmi):>4} months  {pmi['month'].iloc[0]} to {pmi['month'].iloc[-1]}")
print(f"copper_monthly.csv     {len(copper):>4} months  {copper['month'].iloc[0]} to {copper['month'].iloc[-1]}")
print(f"pmi_copper_matched.csv {len(matched):>4} months  {matched['month'].iloc[0]} to {matched['month'].iloc[-1]}")
print("\nNote: copper_price = COMEX HG month-end close, US cents per lb (Sina via AkShare).")
print("Last 5 matched rows:")
print(matched.tail().to_string(index=False))
