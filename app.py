"""
app.py  -  Niche Alpha: China PMI vs LATAM markets (Streamlit dashboard, Week 3)

Run with:  python run_dashboard.py     (or: streamlit run app.py)
Data    :  latam_monthly.csv, made by data_fetcher_v2.py + latam_heatmap.py.
           The dashboard reads saved files; it does not download live data.
"""
import math
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

st.set_page_config(page_title="Niche Alpha: China PMI vs LATAM", layout="wide")


@st.cache_data
def load():
    df = pd.read_csv("latam_monthly.csv", parse_dates=["month"]).sort_values("month")
    ret = pd.DataFrame({"month": df["month"]})
    ret["Copper"] = df["copper_price"].pct_change() * 100
    for ccy in ["CLP", "MXN", "BRL"]:
        c = f"usd{ccy.lower()}"
        if c in df:
            ret[f"{ccy} vs USD"] = (df[c].shift(1) / df[c] - 1) * 100   # + = LATAM currency stronger
    return df, ret


df, ret = load()

CHINA = {
    "Manufacturing PMI": "manufacturing_pmi",
    "Non-manufacturing PMI": "nonmanufacturing_pmi",
}
MARKETS = [c for c in ret.columns if c != "month"]
LEVELS = {"Copper": ("copper_price", "US cents/lb"), "CLP vs USD": ("usdclp", "CLP per USD"),
          "MXN vs USD": ("usdmxn", "MXN per USD"), "BRL vs USD": ("usdbrl", "BRL per USD")}


def corr(x, y):
    d = pd.concat([x, y], axis=1).dropna()
    n = len(d)
    r = d.iloc[:, 0].corr(d.iloc[:, 1])
    t = r * math.sqrt((n - 2) / (1 - r ** 2))
    return r, n, math.erfc(abs(t) / math.sqrt(2)), d


# ---------------- Sidebar ----------------
st.sidebar.title("Settings")
market = st.sidebar.selectbox("LATAM market", MARKETS, index=MARKETS.index("MXN vs USD"))
china_name = st.sidebar.selectbox("China indicator", list(CHINA))
lag = st.sidebar.radio("Timing", ["Previous month's PMI change (t-1)", "Same month (t)"])
lang = st.sidebar.radio("Commentary language", ["English", "Español", "中文"], horizontal=True)
st.sidebar.caption(f"Data: {df['month'].min():%b %Y} – {df['month'].max():%b %Y}. "
                   "Saved files, not live prices.")

china_col = CHINA[china_name]
pmi_change = df[china_col].diff()
x = pmi_change.shift(1) if lag.startswith("Previous") else pmi_change
r, n, p, pairs = corr(x, ret[market])

# ---------------- Header & metrics ----------------
st.title("Niche Alpha: China PMI vs LATAM markets")
st.caption("Does China's factory activity give an early hint about copper and Latin American currencies?")

last = df.iloc[-1]
prev = df.iloc[-2]
lvl_col, lvl_unit = LEVELS[market]
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"{china_name} ({last['month']:%b %Y})", f"{last[china_col]:.1f}",
          f"{last[china_col] - prev[china_col]:+.1f} vs prior month")
c2.metric(f"{market} return ({last['month']:%b %Y})", f"{ret[market].iloc[-1]:+.2f}%")
c3.metric(f"Level: {lvl_unit}", f"{last[lvl_col]:,.2f}")
c4.metric("Correlation (r)", f"{r:+.2f}", f"n = {n}, p ≈ {p:.3f}", delta_color="off")

# ---------------- Charts ----------------
left, right = st.columns([3, 2])

with left:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=df["month"], y=df[china_col], name=china_name,
                             line=dict(color="#c0392b")), secondary_y=False)
    fig.add_trace(go.Bar(x=ret["month"], y=ret[market], name=f"{market} return (%)",
                         marker_color="#2e86c1", opacity=0.45), secondary_y=True)
    fig.add_hline(y=50, line_dash="dot", line_color="#c0392b", secondary_y=False)
    fig.update_yaxes(title_text="PMI (50 = no change)", secondary_y=False)
    fig.update_yaxes(title_text="Monthly return, %", secondary_y=True)
    fig.update_layout(title=f"{china_name} and {market} monthly returns",
                      legend=dict(orientation="h", y=-0.2), height=430, margin=dict(t=50))
    st.plotly_chart(fig, width="stretch")

with right:
    sc = pairs.copy()
    sc.columns = ["PMI change", "Return"]
    sc["month"] = df.loc[sc.index, "month"].dt.strftime("%b %Y")
    fig2 = px.scatter(sc, x="PMI change", y="Return", hover_data=["month"])
    fig2.add_hline(y=0, line_color="grey", line_width=1)
    fig2.add_vline(x=0, line_color="grey", line_width=1)
    fig2.update_layout(title=f"r = {r:+.2f}  (n = {n})", height=430, margin=dict(t=50),
                       xaxis_title=f"{china_name} change ({'t-1' if lag.startswith('Previous') else 't'}), points",
                       yaxis_title=f"{market} return in month t, %")
    st.plotly_chart(fig2, width="stretch")

# ---------------- Heatmap ----------------
st.subheader("All combinations at a glance")
rows = {}
for cname, ccol in CHINA.items():
    ch = df[ccol].diff()
    rows[f"{cname} change (t)"] = {m: corr(ch, ret[m])[0] for m in MARKETS}
    rows[f"{cname} change (t-1)"] = {m: corr(ch.shift(1), ret[m])[0] for m in MARKETS}
heat = pd.DataFrame(rows).T
fig3 = px.imshow(heat.round(2), text_auto=True, color_continuous_scale="RdBu_r",
                 zmin=-0.4, zmax=0.4, aspect="auto", labels=dict(color="Pearson r"))
fig3.update_layout(height=360, margin=dict(t=20))
st.plotly_chart(fig3, width="stretch")
st.caption("Positive = market tends to rise (currency strengthens vs USD) when the PMI change is positive. "
           "CLP uses monthly average rates (OECD via FRED); MXN, BRL and copper use month-end values.")

# ---------------- Commentary (updates with the sidebar choices) ----------------
st.subheader({"English": "Market commentary", "Español": "Comentario de mercado", "中文": "市场评论"}[lang])

prev_month = lag.startswith("Previous")
strength = 0 if abs(r) < 0.1 else (1 if abs(r) < 0.3 else 2)       # none / weak / moderate
positive = r > 0
significant = p < 0.05
is_ccy = market != "Copper"
ccy = market.split()[0]

NAMES = {
    "English": {"Copper": "copper", "CLP": "the Chilean peso", "MXN": "the Mexican peso", "BRL": "the Brazilian real",
                "Manufacturing PMI": "manufacturing PMI", "Non-manufacturing PMI": "non-manufacturing PMI"},
    "Español": {"Copper": "el cobre", "CLP": "el peso chileno", "MXN": "el peso mexicano", "BRL": "el real brasileño",
                "Manufacturing PMI": "el PMI manufacturero", "Non-manufacturing PMI": "el PMI no manufacturero"},
    "中文": {"Copper": "铜价", "CLP": "智利比索", "MXN": "墨西哥比索", "BRL": "巴西雷亚尔",
            "Manufacturing PMI": "制造业PMI", "Non-manufacturing PMI": "非制造业PMI"},
}
nm = NAMES[lang]
mk = nm[ccy] if is_ccy else nm["Copper"]
ind = nm[china_name]
r_txt = f"{r:+.2f}"
p_txt = f"{p:.3f}"
share = round(r * r * 100, 1)

if lang == "English":
    when = "the following month" if prev_month else "in the same month"
    if strength == 0:
        body = f"There is almost no link between changes in China's {ind} and {mk} {when} (r = {r_txt})."
    else:
        word = "weak" if strength == 1 else "moderate"
        move = ("strengthen" if positive else "weaken") if is_ccy else ("rise" if positive else "fall")
        body = (f"There is a {word} {'positive' if positive else 'negative'} link (r = {r_txt}): when China's {ind} "
                f"rises, {mk} has tended to {move} {when}.")
    sig = (f"This passes the usual significance test (p ≈ {p_txt}, n = {n})." if significant else
           f"This is not statistically significant (p ≈ {p_txt}, n = {n}), so it may be chance.")
    tail = (f"PMI explains only about {share}% of these monthly moves, and 16 combinations were tested, "
            "so treat this as a hint, not a trading signal.")
elif lang == "Español":
    when = "al mes siguiente" if prev_month else "en el mismo mes"
    if strength == 0:
        body = f"Casi no hay relación entre los cambios en {ind} de China y {mk} {when} (r = {r_txt})."
    else:
        word = "débil" if strength == 1 else "moderada"
        move = ("fortalecerse" if positive else "debilitarse") if is_ccy else ("subir" if positive else "bajar")
        body = (f"Hay una relación {'positiva' if positive else 'negativa'} {word} (r = {r_txt}): cuando sube {ind} "
                f"de China, {mk} ha tendido a {move} {when}.")
    sig = (f"Supera la prueba de significancia habitual (p ≈ {p_txt}, n = {n})." if significant else
           f"No es estadísticamente significativa (p ≈ {p_txt}, n = {n}), así que podría deberse al azar.")
    tail = (f"El PMI explica solo alrededor del {share} % de estos movimientos mensuales y se analizaron 16 "
            "combinaciones, así que es una pista, no una señal de inversión.")
else:
    when = "下个月" if prev_month else "同月"
    if strength == 0:
        body = f"中国{ind}的变化与{when}{mk}之间几乎没有关联（r = {r_txt}）。"
    else:
        word = "较弱的" if strength == 1 else "中等的"
        move = ("走强" if positive else "走弱") if is_ccy else ("上涨" if positive else "下跌")
        body = (f"两者存在{word}{'正' if positive else '负'}相关（r = {r_txt}）：中国{ind}上升时，"
                f"{mk}在{when}往往{move}。")
    sig = (f"该结果通过了常用的显著性检验（p ≈ {p_txt}，n = {n}）。" if significant else
           f"该结果在统计上不显著（p ≈ {p_txt}，n = {n}），可能只是偶然。")
    tail = f"PMI只能解释这些月度走势的约{share}%，且共检验了16种组合，因此这只是线索，而不是交易信号。"

if lang == "Español":   # Spanish uses decimal commas
    body, sig, tail = (re.sub(r"(\d)\.(\d)", r"\1,\2", t) for t in (body, sig, tail))
st.markdown(f"{body}{'' if lang == '中文' else ' '}{sig}\n\n{tail}")

with st.expander("Data sources and method"):
    st.markdown(
        "- **China PMI:** National Bureau of Statistics, via AkShare (`macro_china_pmi`).\n"
        "- **Copper:** COMEX HG futures, month-end close, US cents/lb, via Sina Finance / AkShare.\n"
        "- **Currencies:** FRED – DEXMXUS, DEXBZUS (daily, month-end), CCUSMA02CLM618N (Chile, monthly average).\n"
        "- **Method:** Pearson correlation between the monthly PMI change and monthly returns. "
        "PMI is published at month-end, so the (t-1) version uses only information public at the time.\n"
        "- **p-values** are approximate (normal approximation) and not adjusted for multiple tests."
    )
    st.dataframe(df.assign(month=df["month"].dt.strftime("%Y-%m")), width="stretch")
