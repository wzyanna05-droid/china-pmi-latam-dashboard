"""
fetch_clp_daily.py  -  Improvement 6: daily Chilean peso -> true MONTH-END rates

Source A: mindicador.cl API (Banco Central de Chile "dólar observado", daily)
Source B: Servicio de Impuestos Internos (SII) yearly "Dólar Observado" tables (same official rate)
Check C : FRED CCUSMA02CLM618N (OECD monthly average of daily rates) - the series used so far

Timing: the dólar observado dated D is the weighted average of trades on the banking day
immediately BEFORE D (BCCh methodology). So the month-end rate for month m is the FIRST value
dated in month m+1 (= trades on the last banking day of month m), matching MXN/BRL month-end.

Strict checks (STOPS - nothing written - if any fails):
  1. A and B agree (|diff| <= 0.01 peso) on at least 99.5% of common dates (if B is readable);
  2. monthly average of A within 0.5% of FRED/OECD for every month 2016-10 .. latest FRED month;
  3. a month-end value exists for every month 2016-10 .. 2026-10.

Outputs: clp_daily.csv, clp_month_end.csv,
         latam_monthly_plus_clp_avg.csv (backup of the current file, unchanged),
         latam_monthly_plus.csv updated: usdclp = month-end rate, usdclp_monthly_avg = old FRED average.
"""
import io
import re
import sys
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

YEARS = range(2016, 2027)
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (Macintosh) research-script"


def stop(msg):
    print(f"\nSTOPPED: {msg}\nNothing was written.")
    sys.exit(1)


# ---------- Source A: mindicador.cl ----------
rows = []
for y in YEARS:
    try:
        r = S.get(f"https://mindicador.cl/api/dolar/{y}", timeout=30)
        r.raise_for_status()
        serie = r.json()["serie"]
    except Exception as e:
        stop(f"mindicador.cl {y} failed: {type(e).__name__}: {e}")
    for o in serie:
        rows.append({"date": pd.to_datetime(o["fecha"][:10]), "clp_mindicador": float(o["valor"])})
    print(f"  mindicador {y}: {len(serie)} days")
    time.sleep(0.4)
a = pd.DataFrame(rows).drop_duplicates("date").sort_values("date").reset_index(drop=True)

# ---------- Source B: SII yearly tables ----------
MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def num(v):
    v = v.strip().replace("$", "").replace("\xa0", "")
    if not v:
        return None
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    return float(v) if re.fullmatch(r"\d+(\.\d+)?", v) else None


def parse_sii(html, y):
    soup = BeautifulSoup(html, "lxml")
    out = {}
    for tbl in soup.find_all("table"):
        trs = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])] for tr in tbl.find_all("tr")]
        header = next((r for r in trs if r and r[0].lower().startswith("d") and len(r) >= 13
                       and [c.lower()[:3] for c in r[1:13]] == MES), None)
        if header is None:
            continue
        for r in trs:
            if r and re.fullmatch(r"\d{1,2}", r[0]) and len(r) >= 13:
                d = int(r[0])
                for mi, cell in enumerate(r[1:13], 1):
                    v = num(cell)
                    if v is not None:
                        out[pd.Timestamp(y, mi, d)] = v
        if out:
            return out
    return out


bvals = {}
for y in YEARS:
    got = {}
    for url in (f"https://www.sii.cl/valores_y_fechas/dolar/dolar{y}.htm",
                f"https://www.sii.cl/pagina/valores/dolar/dolar{y}.htm"):
        try:
            r = S.get(url, timeout=30)
            if r.status_code != 200:
                continue
            r.encoding = r.apparent_encoding or "latin-1"
            got = parse_sii(r.text, y)
            if got:
                break
        except Exception:
            continue
    print(f"  SII {y}: {len(got)} days" + ("" if got else "  (not readable - skipped)"))
    bvals.update(got)
    time.sleep(0.4)

# ---------- Check 1: A vs B ----------
if bvals:
    b = pd.DataFrame({"date": list(bvals), "clp_sii": list(bvals.values())})
    ab = a.merge(b, on="date", how="inner")
    diff = (ab["clp_mindicador"] - ab["clp_sii"]).abs()
    share = (diff <= 0.01).mean()
    print(f"\nCheck 1: {len(ab)} common days; {share:.2%} identical within 0.01 peso; max diff {diff.max():.3f}")
    if share < 0.995:
        print(ab[diff > 0.01].head(20).to_string(index=False))
        stop("mindicador.cl and SII disagree on more than 0.5% of days.")
    a = a.merge(b, on="date", how="left")
else:
    print("\nCheck 1: SII tables not readable - cross-check skipped (FRED check below still applies).")
    a["clp_sii"] = float("nan")

# ---------- Month-end and monthly average ----------
a["month"] = a["date"].dt.to_period("M")
first_next = a.groupby("month")["clp_mindicador"].first()           # first value dated in each month
eom = first_next.shift(-1)                                            # -> month-end of the previous month
eom.index = first_next.index
avg = a.groupby("month")["clp_mindicador"].mean()
last_dated = a.groupby("month")["clp_mindicador"].last()
me = pd.DataFrame({"usdclp_month_end": eom, "usdclp_last_dated_in_month": last_dated,
                   "usdclp_avg_of_daily": avg}).reset_index()
me["month"] = me["month"].dt.to_timestamp()

# ---------- Check 2: monthly averages vs FRED/OECD ----------
try:
    r = S.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CCUSMA02CLM618N", timeout=30)
    r.raise_for_status()
    f = pd.read_csv(io.StringIO(r.text))
    f = pd.DataFrame({"month": pd.to_datetime(f.iloc[:, 0]), "fred_avg": pd.to_numeric(f.iloc[:, 1], errors="coerce")})
except Exception as e:
    stop(f"FRED download failed: {e}")
# OECD's exact averaging convention is not documented here, so compare three definitions and
# keep the check strict (max |diff| <= 0.5%) against the best-matching one.
d = a[["date", "clp_mindicador"]].copy()
# (a) by publication date (as published);  (b) by trade date = previous banking day;
# (c) calendar-day average (each value held until the next publication).
d["trade_date"] = d["date"].shift(1)                                       # value dated D <- trades on previous banking day
defs = {
    "a_dated": d.groupby(d["date"].dt.to_period("M"))["clp_mindicador"].mean(),
    "b_trade_date": d.dropna(subset=["trade_date"]).groupby(d["trade_date"].dt.to_period("M"))["clp_mindicador"].mean(),
}
cal = d.set_index("date")["clp_mindicador"].resample("D").ffill()
defs["c_calendar_days"] = cal.groupby(cal.index.to_period("M")).mean()
fp = f.dropna().assign(m=lambda x: x["month"].dt.to_period("M")).set_index("m")["fred_avg"]
fp = fp[fp.index >= pd.Period("2016-10", "M")]
results = {}
for k, ser in defs.items():
    common = fp.index.intersection(ser.index)
    rel_k = ((ser[common] / fp[common]) - 1).abs()
    results[k] = rel_k
    print(f"Check 2 [{k}]: {len(common)} months, max |diff| {rel_k.max():.3%}, mean {rel_k.mean():.3%}")
best = min(results, key=lambda k: results[k].mean())
rel = results[best]
print(f"Best-matching definition: {best}")
if rel.max() > 0.005:
    print(rel.sort_values(ascending=False).head(8).map(lambda v: f"{v:.3%}").to_string())
    stop(f"even the best definition ({best}) differs from FRED/OECD by more than 0.5% in some month.")

# ---------- Check 3: coverage ----------
need = pd.period_range("2016-10", "2026-10", freq="M").to_timestamp()
have = set(me.dropna(subset=["usdclp_month_end"])["month"])
missing = [m.strftime("%Y-%m") for m in need if m not in have]
if missing:
    stop("no month-end value for: " + ", ".join(missing))
print("Check 3 passed: month-end value for every month 2016-10 to 2026-10.")

# ---------- Save ----------
plus = pd.read_csv("latam_monthly_plus.csv", parse_dates=["month"])
if "usdclp_monthly_avg" in plus.columns:
    stop("latam_monthly_plus.csv already updated (usdclp_monthly_avg exists) - not overwriting twice.")
plus.assign(month=plus["month"].dt.strftime("%Y-%m")).to_csv("latam_monthly_plus_clp_avg.csv", index=False)
new = plus.rename(columns={"usdclp": "usdclp_monthly_avg"}).merge(
    me[["month", "usdclp_month_end"]].rename(columns={"usdclp_month_end": "usdclp"}), on="month", how="left")
if new["usdclp"].isna().any():
    stop("month-end CLP missing after merge.")
a.drop(columns="month").assign(date=a["date"].dt.strftime("%Y-%m-%d")).to_csv("clp_daily.csv", index=False)
me.assign(month=me["month"].dt.strftime("%Y-%m")).round(4).to_csv("clp_month_end.csv", index=False)
new.assign(month=new["month"].dt.strftime("%Y-%m")).to_csv("latam_monthly_plus.csv", index=False)

print(f"\nSaved clp_daily.csv ({len(a)} days, {a['date'].min():%Y-%m-%d} to {a['date'].max():%Y-%m-%d})")
print("Saved clp_month_end.csv; backup latam_monthly_plus_clp_avg.csv; updated latam_monthly_plus.csv")
print(me[me["month"].isin(pd.to_datetime(["2020-02-01", "2020-03-01", "2026-09-01", "2026-10-01"]))]
      .round(2).to_string(index=False))
