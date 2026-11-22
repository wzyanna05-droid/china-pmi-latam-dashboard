"""
fetch_new_orders_nbs.py  -  Improvement 1 (remaining part): NBS manufacturing PMI NEW ORDER INDEX

Source: National Bureau of Statistics of China, English press releases "Purchasing Managers'
Index for <month>" (www.stats.gov.cn/english/PressRelease). Each release contains a 13-month
table "China's Manufacturing PMI and Sub-indexes (Seasonally Adjusted)":
    PMI | Production | New Order | Raw Materials Inventory | Employment | Supplier Delivery Time

Strict checks (the script STOPS if any fails - nothing is written):
  1. column order in each table must be exactly the six columns above;
  2. a month appearing in several releases must have identical values in all of them;
  3. headline PMI must equal china_pmi.csv (AkShare) for every overlapping month;
  4. independent spot checks of New Order values from other published sources;
  5. no missing months between 2016-11 and the latest month.

Output (new files only): china_new_orders.csv, latam_monthly_plus.csv
"""
import re
import sys
import time
from collections import defaultdict

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://www.stats.gov.cn/english/PressRelease/"
RELEASES = [  # (release month, URL path) - found via the NBS site; each covers 13 months
    ("2016-11", "201612/t20161201_1436224.html"), ("2017-10", "201710/t20171031_1548112.html"),
    ("2017-12", "201801/t20180103_1569401.html"), ("2018-01", "201802/t20180202_1580233.html"), ("2018-12", "201901/t20190103_1642836.html"),
    ("2019-05", "201905/t20190531_1668204.html"), ("2019-08", "201909/t20190902_1695139.html"),
    ("2019-11", "201912/t20191202_1712936.html"), ("2020-01", "202002/t20200203_1724922.html"),
    ("2020-02", "202003/t20200302_1729254.html"), ("2020-04", "202005/t20200505_1742978.html"),
    ("2020-05", "202006/t20200601_1753274.html"), ("2020-06", "202007/t20200701_1771424.html"),
    ("2020-11", "202012/t20201201_1806423.html"), ("2021-06", "202107/t20210701_1818892.html"),
    ("2021-11", "202112/t20211201_1824972.html"), ("2022-04", "202205/t20220506_1830262.html"),
    ("2022-06", "202207/t20220704_1861829.html"), ("2022-10", "202211/t20221101_1889909.html"),
    ("2022-12", "202301/t20230106_1891506.html"), ("2023-06", "202307/t20230704_1941008.html"),
    ("2023-10", "202311/t20231107_1944255.html"), ("2023-11", "202312/t20231201_1945102.html"),
    ("2024-06", "202407/t20240703_1955367.html"), ("2024-11", "202412/t20241204_1957641.html"),
    ("2025-06", "202507/t20250707_1960346.html"), ("2025-10", "202511/t20251103_1961770.html"),
    ("2025-09", "202510/t20251010_1961466.html"), ("2025-11", "202512/t20251202_1961963.html"),
    ("2026-02", "202603/t20260305_1962714.html"), ("2026-01", "202602/t20260202_1962478.html"),
    ("2026-04", "202605/t20260506_1963595.html"), ("2026-06", "202607/t20260701_1964047.html"),
    ("2026-09", "202610/t20261008_1965466.html"), ("2026-10", "202611/t20261103_1965735.html"),
]
COLS = ["pmi", "production", "new_orders", "raw_materials_inventory", "employment", "supplier_delivery"]
LABELS = [("pmi", r"^pmi$"), ("production", r"production"), ("new_orders", r"new order"),
          ("raw_materials_inventory", r"raw material"), ("employment", r"employ"),
          ("supplier_delivery", r"supplier")]
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}
SPOT = {  # independent published New Order values (month: value, source)
    "2020-02": (29.3, "Trading Economics: record low 29.30 in Feb 2020"),
    "2026-03": (51.6, "Trading Economics: 51.60 in Mar 2026"),
    "2017-11": (53.6, "CFLP/HKUST PMI report Nov 2017: new orders 53.6"),
    "2018-11": (50.4, "CFLP/HKUST PMI report Nov 2018; CGTN: 50.4"),
    "2025-10": (48.8, "NBS Oct 2025 release text: new order index 48.8%"),
    "2026-04": (50.6, "NBS Apr 2026 release text: new order index 50.6%"),
    "2018-03": (53.3, "Xinhua/cnfin republished NBS table (Sep 2018): 53.3"),
    "2018-04": (52.9, "Xinhua/cnfin republished NBS table (Sep 2018): 52.9"),
    "2019-02": (50.6, "CFLP/HKUST PMI report Feb 2019: new orders 50.6"),
}


def stop(msg):
    print(f"\nSTOPPED: {msg}\nNothing was written.")
    sys.exit(1)


def clean(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def parse_release(html, rel):
    soup = BeautifulSoup(html, "lxml")
    for tbl in soup.find_all("table"):
        rows = [[clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])] for tr in tbl.find_all("tr")]
        text = " ".join(" ".join(r) for r in rows).lower()
        if "production" not in text or "new order" not in text or "supplier" not in text:
            continue                       # not the manufacturing sub-index table
        # header order check (strict)
        header_cells = [c.lower() for r in rows for c in r if c and not re.search(r"\d", c)]
        order = []
        for c in header_cells:
            for key, pat in LABELS:
                if re.search(pat, c) and key not in order:
                    order.append(key)
                    break
        if order != COLS:
            raise ValueError(f"{rel}: unexpected column order {order}")
        out, year = {}, None
        for r in rows:
            cells = [c for c in r if c != ""]
            if not cells:
                continue
            m = re.match(r"^(?:(\d{4})\s*-\s*)?([A-Za-z]+)$", cells[0])
            if not m or m.group(2).lower() not in MONTHS:
                continue
            if m.group(1):
                year = int(m.group(1))
            if year is None:
                raise ValueError(f"{rel}: month row before any year label")
            vals = [float(v) for v in cells[1:] if re.fullmatch(r"-?\d+(\.\d+)?", v)]
            if len(vals) != 6:
                raise ValueError(f"{rel}: row {cells[0]} has {len(vals)} values, expected 6")
            out[f"{year}-{MONTHS[m.group(2).lower()]:02d}"] = dict(zip(COLS, vals))
        months = sorted(out)
        # year carry-forward sanity: consecutive months
        p = pd.PeriodIndex(months, freq="M")
        if len(months) < 6 or (p[1:] - p[:-1]).map(lambda d: d.n).tolist() != [1] * (len(p) - 1):
            raise ValueError(f"{rel}: months not consecutive {months}")
        if months[-1] != rel:
            raise ValueError(f"{rel}: table ends at {months[-1]}, expected {rel}")
        return out
    raise ValueError(f"{rel}: manufacturing sub-index table not found")


values = defaultdict(dict)          # month -> {release: row}
s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Macintosh) research-script"
for rel, path in RELEASES:
    url = BASE + path
    try:
        r = s.get(url, timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        rows = parse_release(r.text, rel)
    except Exception as e:
        stop(f"release {rel} ({url}) failed: {type(e).__name__}: {e}")
    for mth, row in rows.items():
        values[mth][rel] = row
    print(f"  {rel}: {len(rows)} months {min(rows)} to {max(rows)}")
    time.sleep(0.6)

# ---- Check 2: consistency across releases ----
conflicts = []
final = {}
for mth, by_rel in sorted(values.items()):
    rows = list(by_rel.values())
    for col in ("pmi", "new_orders"):
        vals = {row[col] for row in rows}
        if len(vals) > 1:
            conflicts.append(f"{mth} {col}: {dict((k, v[col]) for k, v in by_rel.items())}")
    final[mth] = {"pmi_nbs_release": rows[0]["pmi"], "new_orders_index": rows[0]["new_orders"],
                  "n_releases": len(rows)}
if conflicts:
    stop("values differ between releases:\n  " + "\n  ".join(conflicts))
print(f"\nCheck 2 passed: {sum(len(v) > 1 for v in values.values())} months appear in 2+ releases, all identical.")

no = pd.DataFrame.from_dict(final, orient="index").rename_axis("month").reset_index()
no["month"] = pd.to_datetime(no["month"])

# ---- Check 3: headline PMI matches AkShare ----
ak = pd.read_csv("china_pmi.csv", parse_dates=["month"])
chk = ak.merge(no, on="month")
bad = chk[(chk["manufacturing_pmi"] - chk["pmi_nbs_release"]).abs() > 1e-9]
if len(bad):
    stop("headline PMI differs from china_pmi.csv:\n" + bad.to_string(index=False))
print(f"Check 3 passed: headline PMI identical to AkShare for all {len(chk)} overlapping months.")

# ---- Check 4: independent spot checks ----
for mth, (val, src) in SPOT.items():
    got = final.get(mth, {}).get("new_orders_index")
    if got is None or abs(got - val) > 1e-9:
        stop(f"spot check {mth}: got {got}, expected {val} ({src})")
print(f"Check 4 passed: {len(SPOT)} independent spot checks match.")

# ---- Check 5: coverage ----
base = pd.read_csv("latam_monthly.csv", parse_dates=["month"])
need = pd.period_range("2016-11", base["month"].max().strftime("%Y-%m"), freq="M").to_timestamp()
missing = sorted(set(need) - set(no["month"]))
if missing:
    stop("missing months: " + ", ".join(m.strftime("%Y-%m") for m in missing))
print(f"Check 5 passed: no gaps from 2016-11 to {base['month'].max():%Y-%m}.")

# ---- Save ----
no = no.sort_values("month")
no.assign(month=no["month"].dt.strftime("%Y-%m")).to_csv("china_new_orders.csv", index=False)
plus = base.merge(no[["month", "new_orders_index"]], on="month", how="left")
plus.assign(month=plus["month"].dt.strftime("%Y-%m")).to_csv("latam_monthly_plus.csv", index=False)
print(f"\nSaved china_new_orders.csv ({len(no)} months, {no['month'].min():%Y-%m} to {no['month'].max():%Y-%m})")
print("Saved latam_monthly_plus.csv (latam_monthly.csv + new_orders_index)")
print(no[no["month"].dt.strftime("%Y-%m").isin(["2020-01", "2020-02", "2020-03", "2026-10"])].to_string(index=False))
