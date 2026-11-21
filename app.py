"""
app.py  -  Niche Alpha: China PMI vs LATAM markets (Streamlit dashboard)

Run with:  python run_dashboard.py     (or: streamlit run app.py)
Data    :  latam_monthly.csv, made by data_fetcher_v2.py + latam_heatmap.py.
           The dashboard reads saved files; it does not download live data.

v2 (21 Nov 2026): lead of 0-6 months, 3-month-average PMI, lag-profile chart,
rolling 36-month correlation, and a switch to exclude the COVID shock (Feb-Apr 2020).
"""
import math
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

st.set_page_config(page_title="Niche Alpha: China PMI vs LATAM", layout="wide")

COVID_PMI_MONTHS = ["2020-02", "2020-03"]                 # PMI fell 14.3, then rose 16.3 points
COVID_RETURN_MONTHS = ["2020-02", "2020-03", "2020-04"]   # market crash and rebound
WINDOW = 36
N_TESTS_SCAN = 112   # lag_scan.py: 4 indicators x 4 markets x 7 leads


@st.cache_data
def load():
    df = pd.read_csv("latam_monthly.csv", parse_dates=["month"]).sort_values("month").reset_index(drop=True)
    ret = pd.DataFrame({"month": df["month"]})
    ret["Copper"] = df["copper_price"].pct_change() * 100
    for ccy in ["CLP", "MXN", "BRL"]:
        c = f"usd{ccy.lower()}"
        if c in df:
            ret[f"{ccy} vs USD"] = (df[c].shift(1) / df[c] - 1) * 100   # + = LATAM currency stronger
    return df, ret


df, ret = load()
ym = df["month"].dt.strftime("%Y-%m")

CHINA = {
    "Manufacturing PMI": ("manufacturing_pmi", 1),
    "Manufacturing PMI (3-month avg)": ("manufacturing_pmi", 3),
    "Non-manufacturing PMI": ("nonmanufacturing_pmi", 1),
    "Non-manufacturing PMI (3-month avg)": ("nonmanufacturing_pmi", 3),
}
MARKETS = [c for c in ret.columns if c != "month"]
LEVELS = {"Copper": ("copper_price", "US cents/lb"), "CLP vs USD": ("usdclp", "CLP per USD"),
          "MXN vs USD": ("usdmxn", "MXN per USD"), "BRL vs USD": ("usdbrl", "BRL per USD")}


def pmi_change(name, exclude):
    col, avg = CHINA[name]
    s = (df[col].rolling(avg).mean() if avg > 1 else df[col]).diff()
    return s.mask(ym.isin(COVID_PMI_MONTHS)) if exclude else s


def market_return(name, exclude):
    s = ret[name]
    return s.mask(ym.isin(COVID_RETURN_MONTHS)) if exclude else s


def corr(x, y):
    d = pd.concat([x, y], axis=1).dropna()
    n = len(d)
    r = d.iloc[:, 0].corr(d.iloc[:, 1])
    t = r * math.sqrt((n - 2) / (1 - r ** 2))
    return r, n, math.erfc(abs(t) / math.sqrt(2)), d


# ---------------- Sidebar ----------------
st.sidebar.title("Settings")
market = st.sidebar.selectbox("LATAM market", MARKETS, index=MARKETS.index("Copper"))
china_name = st.sidebar.selectbox("China indicator", list(CHINA))
lead = st.sidebar.slider("PMI lead (months)", 0, 6, 1,
                         help="0 = same month. 1 = PMI change last month vs this month's return, etc.")
exclude = st.sidebar.toggle("Exclude COVID shock (Feb–Apr 2020)", value=False,
                            help="Drops the Feb–Mar 2020 PMI changes and Feb–Apr 2020 market returns.")
lang = st.sidebar.radio("Commentary language", ["English", "Español", "中文"], horizontal=True)
st.sidebar.caption(f"Data: {df['month'].min():%b %Y} – {df['month'].max():%b %Y}. "
                   "Saved files, not live prices.")

x = pmi_change(china_name, exclude).shift(lead)
y = market_return(market, exclude)
r, n, p, pairs = corr(x, y)
# the same pairing computed the other way, for the robustness note
r_alt, n_alt, p_alt, _ = corr(pmi_change(china_name, not exclude).shift(lead), market_return(market, not exclude))

# ---------------- Header & metrics ----------------
st.title("Niche Alpha: China PMI vs LATAM markets")
st.caption("Does China's factory activity give an early hint about copper and Latin American currencies?")
st.warning("**Robustness check:** the apparent one-month lead of China's PMI on copper and the Mexican peso "
           "comes almost entirely from the COVID shock (Feb–Apr 2020). Without those months it disappears "
           "(copper r 0.20 → 0.02; MXN r 0.21 → −0.06). Use the sidebar switch to see this for yourself.")

col_pmi, _ = CHINA[china_name]
last, prev = df.iloc[-1], df.iloc[-2]
lvl_col, lvl_unit = LEVELS[market]
c1, c2, c3, c4 = st.columns(4)
pmi_label = "Manufacturing PMI" if col_pmi == "manufacturing_pmi" else "Non-manufacturing PMI"
c1.metric(f"{pmi_label} ({last['month']:%b %Y})", f"{last[col_pmi]:.1f}",
          f"{last[col_pmi] - prev[col_pmi]:+.1f} vs prior month")
c2.metric(f"{market} return ({last['month']:%b %Y})", f"{ret[market].iloc[-1]:+.2f}%")
c3.metric(f"Level: {lvl_unit}", f"{last[lvl_col]:,.2f}")
c4.metric(f"Correlation (r), lead {lead}", f"{r:+.2f}", f"n = {n}, p ≈ {p:.3f}", delta_color="off")

# ---------------- Time series + scatter ----------------
left, right = st.columns([3, 2])
with left:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=df["month"], y=df[col_pmi], name=pmi_label,
                             line=dict(color="#c0392b")), secondary_y=False)
    fig.add_trace(go.Bar(x=ret["month"], y=ret[market], name=f"{market} return (%)",
                         marker_color="#2e86c1", opacity=0.45), secondary_y=True)
    fig.add_hline(y=50, line_dash="dot", line_color="#c0392b", secondary_y=False)
    fig.add_vrect(x0="2020-01-15", x1="2020-04-15", fillcolor="grey", opacity=0.15, line_width=0,
                  annotation_text="COVID shock", annotation_position="top left")
    fig.update_yaxes(title_text="PMI (50 = no change)", secondary_y=False)
    fig.update_yaxes(title_text="Monthly return, %", secondary_y=True)
    fig.update_layout(title=f"{pmi_label} and {market} monthly returns",
                      legend=dict(orientation="h", y=-0.2), height=430, margin=dict(t=50))
    st.plotly_chart(fig)

with right:
    sc = pairs.copy()
    sc.columns = ["PMI change", "Return"]
    sc["month"] = df.loc[sc.index, "month"].dt.strftime("%b %Y")
    sc["COVID months"] = df.loc[sc.index, "month"].dt.strftime("%Y-%m").isin(COVID_RETURN_MONTHS)
    fig2 = px.scatter(sc, x="PMI change", y="Return", hover_data=["month"], color="COVID months",
                      color_discrete_map={False: "#2e86c1", True: "#e67e22"})
    fig2.add_hline(y=0, line_color="grey", line_width=1)
    fig2.add_vline(x=0, line_color="grey", line_width=1)
    fig2.update_layout(title=f"r = {r:+.2f}  (n = {n})", height=430, margin=dict(t=50),
                       xaxis_title=f"{china_name} change, {lead} month(s) earlier (points)",
                       yaxis_title=f"{market} return in month t, %", legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig2)

# ---------------- Lag profile + rolling correlation ----------------
lp, rc = st.columns(2)
with lp:
    st.subheader("Lag profile")
    prof = []
    for k in range(7):
        for ex, label in [(False, "All months"), (True, "Excl. COVID")]:
            rk, nk, pk, _ = corr(pmi_change(china_name, ex).shift(k), market_return(market, ex))
            prof.append({"lead": k, "r": rk, "p": pk, "sample": label})
    prof = pd.DataFrame(prof)
    fig4 = px.line(prof, x="lead", y="r", color="sample", markers=True,
                   color_discrete_map={"All months": "#2e86c1", "Excl. COVID": "#e67e22"},
                   hover_data={"p": ":.3f"})
    fig4.add_hline(y=0, line_color="grey", line_width=1)
    fig4.update_layout(height=360, margin=dict(t=20), xaxis_title="PMI lead (months)",
                       yaxis_title="Pearson r", legend=dict(orientation="h", y=-0.3))
    st.plotly_chart(fig4)
    st.caption("Correlation between the PMI change k months earlier and this month's return.")

with rc:
    st.subheader(f"Stability: rolling {WINDOW}-month r")
    roll = pd.DataFrame({"month": df["month"],
                         "r": pmi_change(china_name, False).shift(lead).rolling(WINDOW).corr(ret[market])})
    fig5 = px.line(roll.dropna(), x="month", y="r")
    fig5.add_hline(y=0, line_color="grey", line_width=1)
    fig5.add_vrect(x0="2020-03-01", x1="2023-03-01", fillcolor="grey", opacity=0.12, line_width=0,
                   annotation_text="windows containing COVID", annotation_position="top left")
    fig5.update_layout(height=360, margin=dict(t=20), yaxis_title="Pearson r", xaxis_title=None)
    st.plotly_chart(fig5)
    st.caption(f"Each point uses the previous {WINDOW} months (all months). A stable relationship "
               "would stay at a similar level; here it jumps when COVID enters the window and drops when it leaves.")

# ---------------- Heatmap ----------------
st.subheader("All combinations at a glance" + (" (COVID excluded)" if exclude else ""))
rows = {}
for cname in CHINA:
    for k in (0, 1):
        rows[f"{cname} change ({'t' if k == 0 else 't-1'})"] = {
            m: corr(pmi_change(cname, exclude).shift(k), market_return(m, exclude))[0] for m in MARKETS}
heat = pd.DataFrame(rows).T
fig3 = px.imshow(heat.round(2), text_auto=True, color_continuous_scale="RdBu_r",
                 zmin=-0.4, zmax=0.4, aspect="auto", labels=dict(color="Pearson r"))
fig3.update_layout(height=440, margin=dict(t=20))
st.plotly_chart(fig3)
st.caption("Positive = market tends to rise (currency strengthens vs USD) when the PMI change is positive. "
           "CLP uses monthly average rates (OECD via FRED); MXN, BRL and copper use month-end values.")

# ---------------- Commentary (updates with the sidebar choices) ----------------
st.subheader({"English": "Market commentary", "Español": "Comentario de mercado", "中文": "市场评论"}[lang])

strength = 0 if abs(r) < 0.1 else (1 if abs(r) < 0.3 else 2)
positive = r > 0
significant = p < 0.05
is_ccy = market != "Copper"
ccy = market.split()[0]
NAMES = {
    "English": {"Copper": "copper", "CLP": "the Chilean peso", "MXN": "the Mexican peso", "BRL": "the Brazilian real",
                "manufacturing_pmi": "manufacturing PMI", "nonmanufacturing_pmi": "non-manufacturing PMI"},
    "Español": {"Copper": "el cobre", "CLP": "el peso chileno", "MXN": "el peso mexicano", "BRL": "el real brasileño",
                "manufacturing_pmi": "el PMI manufacturero", "nonmanufacturing_pmi": "el PMI no manufacturero"},
    "中文": {"Copper": "铜价", "CLP": "智利比索", "MXN": "墨西哥比索", "BRL": "巴西雷亚尔",
            "manufacturing_pmi": "制造业PMI", "nonmanufacturing_pmi": "非制造业PMI"},
}
nm = NAMES[lang]
mk = nm[ccy] if is_ccy else nm["Copper"]
ind = nm[col_pmi]
r_txt, p_txt, share = f"{r:+.2f}", f"{p:.3f}", round(r * r * 100, 1)
alt_r, alt_p = f"{r_alt:+.2f}", f"{p_alt:.3f}"

if lang == "English":
    when = "in the same month" if lead == 0 else ("the following month" if lead == 1 else f"{lead} months later")
    if strength == 0:
        body = f"There is almost no link between changes in China's {ind} and {mk} {when} (r = {r_txt})."
    else:
        word = "weak" if strength == 1 else "moderate"
        move = ("strengthen" if positive else "weaken") if is_ccy else ("rise" if positive else "fall")
        body = (f"There is a {word} {'positive' if positive else 'negative'} link (r = {r_txt}): when China's {ind} "
                f"rises, {mk} has tended to {move} {when}.")
    sig = (f"This passes the usual significance test (p ≈ {p_txt}, n = {n})." if significant else
           f"This is not statistically significant (p ≈ {p_txt}, n = {n}), so it may be chance.")
    rob = (f"{'Including' if exclude else 'Excluding'} the COVID shock (Feb–Apr 2020) gives r = {alt_r} "
           f"(p ≈ {alt_p}).")
    tail = (f"Across all {N_TESTS_SCAN} lead/indicator/market combinations tested, none survive a correction for "
            "multiple testing, so treat any single result as a hint, not a trading signal.")
elif lang == "Español":
    when = "en el mismo mes" if lead == 0 else ("al mes siguiente" if lead == 1 else f"{lead} meses después")
    if strength == 0:
        body = f"Casi no hay relación entre los cambios en {ind} de China y {mk} {when} (r = {r_txt})."
    else:
        word = "débil" if strength == 1 else "moderada"
        move = ("fortalecerse" if positive else "debilitarse") if is_ccy else ("subir" if positive else "bajar")
        body = (f"Hay una relación {'positiva' if positive else 'negativa'} {word} (r = {r_txt}): cuando sube {ind} "
                f"de China, {mk} ha tendido a {move} {when}.")
    sig = (f"Supera la prueba de significancia habitual (p ≈ {p_txt}, n = {n})." if significant else
           f"No es estadísticamente significativa (p ≈ {p_txt}, n = {n}), así que podría deberse al azar.")
    rob = (f"{'Incluyendo' if exclude else 'Excluyendo'} el shock del COVID (feb–abr 2020), r = {alt_r} "
           f"(p ≈ {alt_p}).")
    tail = (f"De las {N_TESTS_SCAN} combinaciones analizadas, ninguna supera una corrección por pruebas "
            "múltiples, así que cualquier resultado aislado es una pista, no una señal de inversión.")
else:
    when = "同月" if lead == 0 else ("下个月" if lead == 1 else f"{lead}个月后")
    if strength == 0:
        body = f"中国{ind}的变化与{when}{mk}之间几乎没有关联（r = {r_txt}）。"
    else:
        word = "较弱的" if strength == 1 else "中等的"
        move = ("走强" if positive else "走弱") if is_ccy else ("上涨" if positive else "下跌")
        body = f"两者存在{word}{'正' if positive else '负'}相关（r = {r_txt}）：中国{ind}上升时，{mk}在{when}往往{move}。"
    sig = (f"该结果通过了常用的显著性检验（p ≈ {p_txt}，n = {n}）。" if significant else
           f"该结果在统计上不显著（p ≈ {p_txt}，n = {n}），可能只是偶然。")
    rob = f"{'计入' if exclude else '剔除'}新冠冲击月份（2020年2–4月）后，r = {alt_r}（p ≈ {alt_p}）。"
    tail = f"在检验的全部{N_TESTS_SCAN}种组合中，经过多重检验校正后没有一个结果仍然显著，因此任何单一结果都只是线索，而不是交易信号。"

if lang == "Español":   # Spanish uses decimal commas
    body, sig, rob, tail = (re.sub(r"(\d)\.(\d)", r"\1,\2", t) for t in (body, sig, rob, tail))
sep = "" if lang == "中文" else " "
st.markdown(f"{body}{sep}{sig}{sep}{rob}\n\n{tail}")

with st.expander("Data sources and method"):
    st.markdown(
        "- **China PMI:** National Bureau of Statistics, via AkShare (`macro_china_pmi`).\n"
        "- **Copper:** COMEX HG futures, month-end close, US cents/lb, via Sina Finance / AkShare.\n"
        "- **Currencies:** FRED – DEXMXUS, DEXBZUS (daily, month-end), CCUSMA02CLM618N (Chile, monthly average).\n"
        "- **Method:** Pearson correlation between the monthly PMI change k months earlier and the monthly return. "
        "PMI is published at month-end, so a lead of 1+ month uses only information public at the time.\n"
        "- **3-month avg:** change in the 3-month moving average of the PMI.\n"
        "- **COVID switch:** drops the Feb–Mar 2020 PMI changes and Feb–Apr 2020 market returns.\n"
        f"- **Multiple testing:** {N_TESTS_SCAN} combinations were scanned (lag_scan.py); none pass a Bonferroni "
        "correction. p-values are approximate (normal approximation)."
    )
    st.dataframe(df.assign(month=df["month"].dt.strftime("%Y-%m")), width="stretch")
