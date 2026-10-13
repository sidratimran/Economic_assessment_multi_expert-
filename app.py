"""AsiaPulse AI — real-time economic assessment & policy intelligence for 47 Asian economies."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from asiapulse import live  # noqa: E402
from asiapulse.agents.orchestrator import ask  # noqa: E402
from asiapulse.config import PROCESSED, qwen_settings  # noqa: E402
from asiapulse.indicators import BY_KEY, INDICATORS, PILLAR_LABELS  # noqa: E402
from asiapulse.models.risk import FLAGS, LEVELS, PILLARS, risk_label  # noqa: E402
from asiapulse.models.scenario import Levers  # noqa: E402
from asiapulse.report.brief import markdown_brief, pdf_brief  # noqa: E402
from asiapulse.store import Store  # noqa: E402
from asiapulse.ui.theme import (BAND, BLUE_RAMP, CSS, INK, SERIES, chip, esc, fig_layout, fmt, kpi,  # noqa: E402
                                page_head, section, spark)

st.set_page_config(page_title="AsiaPulse AI · Economic Intelligence", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown(CSS, unsafe_allow_html=True)

if not (PROCESSED / "metadata.json").exists():
    st.error("No processed data found. Run `python pipeline/run_pipeline.py` first.")
    st.stop()


# ---------------------------------------------------------------- data access (cached)
@st.cache_resource
def get_store() -> Store:
    return Store()


@st.cache_data(ttl=900, show_spinner=False)
def get_global():
    return live.global_snapshot()


@st.cache_data(ttl=900, show_spinner=False)
def get_regional_fx(isos: tuple):
    return live.regional_fx(list(isos))


@st.cache_data(ttl=600, show_spinner=False)
def get_live(iso: str):
    return live.live_assessment(get_store(), iso, get_global())


S = get_store()
META = S.meta
N_VARS = len(INDICATORS) + 3
COUNTRIES = S.countries()
PCOLS = [c for c in S.scores.columns if c.startswith("pillar_")]
PNAMES = {c: PILLAR_LABELS[c.replace("pillar_", "")] for c in PCOLS}


def show(fig, key=None):
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)


def html(s):
    st.markdown(s, unsafe_allow_html=True)


def kpis(items):
    cols = st.columns(len(items))
    for c, it in zip(cols, items):
        with c:
            html(kpi(*it))


# ---------------------------------------------------------------- sidebar
PAGES = {"Overview": "🌏", "Live monitor": "⚡", "Country profile": "📊", "Policy lab": "⚖️",
         "AI analyst": "✨", "Compare": "⇄", "Methodology": "📘"}
with st.sidebar:
    html('<div class="brand">AsiaPulse AI</div><div class="brand-sub">Economic assessment & policy intelligence</div>')
    country = st.selectbox("Economy", COUNTRIES, index=COUNTRIES.index("Pakistan") if "Pakistan" in COUNTRIES else 0)
    ISO = S.iso(country)
    page = st.radio("Navigate", list(PAGES), format_func=lambda p: f"{PAGES[p]}  {p}", label_visibility="collapsed")
    st.divider()
    try:
        g = get_global()
        b = g["brent"]
        dot = "stale-dot" if b["stale"] else "live-dot"
        html(f'<div class="muted"><span class="{dot}"></span>Markets live · Brent <b>${fmt(b["price"], 2)}</b>'
             f' ({fmt(b["chg_1m"], 1, "%", "+" if (b["chg_1m"] or 0) > 0 else "")} 1m)</div>')
    except Exception:
        html('<div class="muted"><span class="stale-dot"></span>Market data unavailable</div>')
    cfg = qwen_settings()
    html(f'<div class="muted" style="margin-top:6px">{"🟢" if cfg["api_key"] else "🟡"} AI analyst: '
         f'{esc(cfg["model"]) if cfg["api_key"] else "offline mode"}</div>')
    html(f'<div class="muted" style="margin-top:6px">Official data: {META["generated_utc"]} UTC</div>')
    html('<div class="muted" style="margin-top:14px">Sources: World Bank WDI & WGI · IMF WEO · Yahoo Finance (markets)</div>')


# ================================================================ OVERVIEW
def page_overview():
    sc = S.scores.join(S.snap[["country", "region", "gdp_cagr_fc", "population", "imf_growth_2026_30"]]).join(
        S.clusters[["cluster_name"]])
    html(page_head("Asia economic overview",
                   f"Structural vulnerability, outlook and economic profiles for {META['economies_covered']} economies, "
                   f"built from {N_VARS} official variables across 13 policy areas.",
                   f"Reference year {META['reference_year']}<br>Forecast horizon {META['forecast_end']}"))
    high = sc[sc.label == "High"]
    kpis([("Economies assessed", f"{META['economies_covered']}", "Taiwan & DPRK: no WDI coverage"),
          ("Variables tracked", f"{N_VARS}", "13 policy areas incl. technology"),
          ("High vulnerability", f"{len(high)}", f"{fmt(high.population.sum() / 1e6, 0)} m people"),
          ("Median growth outlook", fmt(sc.gdp_cagr_fc.median(), 1, "%"), "Real GDP CAGR to 2035"),
          ("Red flags raised", f"{len(S.flags)}", f"avg {len(S.flags) / len(sc):.1f} per economy")])

    html(section("Where vulnerability is concentrated"))
    a, b = st.columns([1.7, 1], gap="medium")
    with a:
        fig = px.choropleth(sc.reset_index(), locations="iso3", color="composite", hover_name="country",
                            color_continuous_scale=BLUE_RAMP, range_color=(20, 85), scope="asia",
                            custom_data=["label", "cluster_name"])
        fig.update_traces(hovertemplate="<b>%{hovertext}</b><br>Vulnerability %{z:.1f} · %{customdata[0]}"
                                        "<br>%{customdata[1]}<extra></extra>", marker_line_color="#ffffff", marker_line_width=0.6)
        fig.update_geos(bgcolor="rgba(0,0,0,0)", showframe=False, showcoastlines=False, landcolor="#efeee9",
                        showcountries=True, countrycolor="#ffffff", lataxis_range=[-11, 56], lonaxis_range=[26, 148])
        fig.update_layout(coloraxis_colorbar=dict(title="Vulnerability<br>(0–100)", thickness=10, len=0.7))
        show(fig_layout(fig, 430))
        st.caption("Darker = more vulnerable relative to Asian peers. Hover for details.")
    with b:
        top = sc.sort_values("composite", ascending=False)
        rows = "".join(f"<div><span>{esc(r.country)}</span><span>{fmt(r.composite, 1)} &nbsp;{chip(r.label)}</span></div>"
                       for r in top.head(7).itertuples())
        html(f'<div class="card"><h4>Most vulnerable</h4><div class="rowlist">{rows}</div></div>')
        rows = "".join(f"<div><span>{esc(r.country)}</span><span>{fmt(r.composite, 1)} &nbsp;{chip(r.label)}</span></div>"
                       for r in top.tail(5)[::-1].itertuples())
        html(f'<div class="card"><h4>Most resilient</h4><div class="rowlist">{rows}</div></div>')

    html(section("Vulnerability by policy area (0 = most resilient in Asia · 100 = most vulnerable)"))
    hm = sc.sort_values("composite", ascending=False)
    z = hm[PCOLS].rename(columns=PNAMES)
    fig = go.Figure(go.Heatmap(z=z.T.values, x=hm.country, y=list(z.columns), colorscale=BLUE_RAMP, zmin=0, zmax=100,
                               xgap=2, ygap=2, colorbar=dict(thickness=10, title="Score"),
                               hovertemplate="<b>%{x}</b><br>%{y}: %{z:.0f}<extra></extra>"))
    fig.update_xaxes(tickangle=-55, tickfont_size=10)
    fig.update_layout(hovermode="closest")
    show(fig_layout(fig, 440))

    html(section("Data-driven economic profiles (K-Means)"))
    groups = S.clusters.join(S.snap.country).groupby("cluster_name").country.apply(list)
    cols = st.columns(len(groups))
    for c, (name, members) in zip(cols, groups.items()):
        c.markdown(f'<div class="card"><h4>{esc(name)}</h4><div class="muted">{len(members)} economies</div>'
                   f'<div style="font-size:.85rem;margin-top:8px;color:{INK["secondary"]}">{esc(", ".join(sorted(members)))}</div></div>',
                   unsafe_allow_html=True)

    html(section("Full ranking"))
    tbl = sc.sort_values("composite", ascending=False)[["country", "region", "cluster_name", "composite", "label",
                                                         "gdp_cagr_fc", "imf_growth_2026_30", "coverage"]]
    tbl.columns = ["Economy", "Region", "Profile", "Vulnerability", "Level", "Model CAGR to 2035 %",
                   "IMF growth 2026-30 %", "Data coverage"]
    st.dataframe(tbl.round(2), width="stretch", hide_index=True, height=420,
                 column_config={"Vulnerability": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
                                "Data coverage": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})


# ================================================================ LIVE MONITOR
@st.fragment(run_every=300)
def page_live():
    t0 = time.time()
    with st.spinner("Pulling live market data…"):
        g = get_global()
        la = get_live(ISO)
    now = datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC")
    stale = any(v["stale"] for v in g.values())
    html(page_head("Live monitor",
                   "Real-time market signals turned into a live growth nowcast and a live risk reading. "
                   "Official statistics lag by months; markets move every day.",
                   f'<span class="{"stale-dot" if stale else "live-dot"}"></span>{"Cached" if stale else "Live"} · {now}<br>'
                   "Auto-refreshes every 5 min"))
    if st.button("↻ Refresh now"):
        get_global.clear(); get_live.clear(); get_regional_fx.clear()
        st.rerun()

    html(section("Global drivers"))
    cols = st.columns(len(g))
    for c, (k, v) in zip(cols, g.items()):
        ch = v["chg_1m"]
        tone = None if ch is None or np.isnan(ch) else ("down" if (ch > 0) == (k in ("brent", "vix", "us10y", "dxy")) else "up")
        with c:
            html(kpi(v["label"], fmt(v["price"], 0 if (v["price"] or 0) > 1000 else 2), f"{fmt(ch, 1, '%', '+' if (ch or 0) > 0 else '')} 1m · "
                                                     f"{fmt(v['chg_1y'], 1, '%', '+' if (v['chg_1y'] or 0) > 0 else '')} 1y", tone))
            if len(v["series"]):
                show(spark(v["series"].tail(180), SERIES[0]), key=f"spark_{k}")
    st.caption("Red/green notes show whether the 1-month move is a headwind or tailwind for oil-importing emerging Asia.")

    nc, stv, sig = la["nowcast"], la["stress"], la["signals"]
    html(section(f"{country} · real-time assessment"))
    lr_label = risk_label(la["live_risk"])
    kpis([(f"Growth nowcast {nc['year']}", fmt(nc["nowcast"], 2, "%"),
           f"Model {fmt(nc['asiapulse_model'], 2, '%')} · IMF {fmt(nc['imf_weo'], 2, '%')} · oil {fmt(nc['oil_adjustment_pp'], 2, ' pp', '+' if nc['oil_adjustment_pp'] > 0 else '')}"),
          ("Live risk reading", f"{fmt(la['live_risk'], 1)} {chip(lr_label)}", f"Structural {fmt(la['structural'], 1)} + market stress"),
          ("Market stress", fmt(stv["score"], 0, "/100"), f"{len(stv['components'])} live components"),
          ("Currency vs US$ (3m)",
           "Pegged" if sig["pegged"] else (fmt(sig["fx"]["depr_3m"], 1, "%", "+" if (sig["fx"]["depr_3m"] or 0) > 0 else "") if sig["fx"] else "—"),
           "positive = depreciation" if sig["fx"] and not sig["pegged"] else "no floating-rate signal"),
          ("Inflation pass-through", fmt(nc.get("inflation_passthrough_pp"), 2, " pp"), "from 3m currency move (×0.2)")])

    a, b = st.columns([1, 1.25], gap="medium")
    with a:
        comp = pd.Series(stv["components"]).dropna().sort_values()
        if len(comp):
            fig = go.Figure(go.Bar(x=comp.values, y=comp.index, orientation="h", marker_color=SERIES[0],
                                   marker_line_width=0, text=[f"{v:.0f}" for v in comp.values], textposition="outside",
                                   hovertemplate="%{y}: %{x:.0f}/100<extra></extra>"))
            fig.update_xaxes(range=[0, 110], showgrid=True)
            fig.update_layout(hovermode="closest")
            show(fig_layout(fig, 300, "Market stress components (0–100)", legend=False))
        if la["alerts"]:
            for a_ in la["alerts"]:
                html(f'<div class="flag">⚠️ <div>{esc(a_)}<small>Above the 60/100 alert threshold</small></div></div>')
        else:
            html('<div class="note-box">No live market alerts for this economy.</div>')
    with b:
        fx = sig.get("fx")
        if fx is not None and len(fx["series"]) > 30:
            s = fx["series"]
            fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines", line=dict(color=SERIES[0], width=2),
                                       name=f"{fx['currency']} per US$"))
            show(fig_layout(fig, 300, f"{fx['currency']} per US$ · 1 year (up = weaker {fx['currency']})", legend=False))
        eq = sig.get("equity")
        if eq is not None:
            s = eq["series"]
            fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines", line=dict(color=SERIES[0], width=2), name=eq["symbol"]))
            show(fig_layout(fig, 260, f"Equity index {eq['symbol']} · drawdown from 52-week high {fmt(eq['drawdown'], 1, '%')}", legend=False))
        if (fx is None or len(fx["series"]) <= 30) and eq is None:
            html('<div class="note-box">No liquid daily market series for this economy; the live reading relies on global drivers.</div>')

    hist = live.nowcast_history(ISO)
    if len(hist) >= 2:
        fig = go.Figure(go.Scatter(x=pd.to_datetime(hist.ts), y=hist.nowcast, mode="lines+markers",
                                   line=dict(color=SERIES[0], width=2), marker=dict(size=8)))
        show(fig_layout(fig, 240, f"How the {nc['year']} nowcast has evolved (each app refresh is logged)", legend=False))

    html(section("Region · currency moves over the last 3 months (floating currencies)"))
    fxr = get_regional_fx(tuple(S.snap.index))
    if len(fxr):
        fxr = fxr.assign(country=fxr.iso3.map(S.snap.country)).sort_values("depr_3m")
        colors = ["#e34948" if v > 0 else "#2a78d6" for v in fxr.depr_3m]
        fig = go.Figure(go.Bar(x=fxr.country, y=fxr.depr_3m, marker_color=colors, marker_line_width=0,
                               customdata=fxr.currency, hovertemplate="<b>%{x}</b> (%{customdata})<br>%{y:+.1f}% vs US$<extra></extra>"))
        fig.add_hline(y=0, line_color=INK["axis"], line_width=1)
        fig.update_layout(hovermode="closest", yaxis_title="% change vs US$ (+ = depreciation)")
        fig.update_xaxes(tickangle=-50, tickfont_size=10)
        show(fig_layout(fig, 340, legend=False))
        st.caption("Red = currency weakened against the US dollar (imported-inflation and external-debt pressure); blue = strengthened.")
    brent = g["brent"]["series"]
    if len(brent):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=brent.index, y=brent.values, name="Brent (US$/bbl)", line=dict(color=SERIES[0], width=2)))
        fig.add_trace(go.Scatter(x=brent.index, y=brent.rolling(250, min_periods=60).mean(), name="Trailing 12-month average",
                                 line=dict(color=INK["muted"], width=1.5, dash="dot")))
        show(fig_layout(fig, 300, f"Oil shock monitor · 30-day average vs prior 12 months: {fmt(nc['oil_move_pct'], 1, '%', '+')}"))
    st.caption(f"Live layer computed in {time.time() - t0:.1f}s · market data: Yahoo Finance public endpoint · "
               "nowcast method in Methodology.")


# ================================================================ COUNTRY PROFILE
def page_country():
    prof, risk, fc, val, peers = S.profile(ISO), S.risk(ISO), S.forecast(ISO), S.validation(ISO), S.peers(ISO)
    ind = prof["indicators"]

    def iv(k):
        return ind.get(k, {}).get("value")

    html(page_head(country, f"{esc(prof['region'])} · {esc(prof['economic_profile'])} · vulnerability "
                            f"{fmt(risk['composite_vulnerability'])}/100, rank {risk['rank_most_vulnerable']} of {risk['of']} "
                            f"(1 = most vulnerable)", chip(risk["label"])))
    kpis([("GDP (current US$)", fmt(ind.get("gdp_usd", {}).get("value_bn"), 0, " bn", "$"), f"{ind.get('gdp_usd', {}).get('year', '')}"),
          ("Real growth, 5-yr avg", fmt(iv("growth_5y_avg"), 1, "%"), ""),
          ("GDP per capita, PPP", fmt(iv("gdp_pc_ppp"), 0, "", "$"), f"{ind.get('gdp_pc_ppp', {}).get('year', '')}"),
          ("Unemployment", fmt(iv("unemp"), 1, "%"), f"youth {fmt(iv('youth_unemp'), 1, '%')}"),
          ("Inflation", fmt(iv("inflation"), 1, "%"), f"{ind.get('inflation', {}).get('year', '')}"),
          ("Public debt", fmt(iv("gov_debt"), 1, "% GDP"), "IMF WEO")])
    st.write("")
    kpis([("Internet users", fmt(iv("internet"), 0, "%"), "technology"),
          ("R&D spending", fmt(iv("rnd"), 2, "% GDP"), "technology"),
          ("High-tech exports", fmt(iv("hightech_exports"), 1, "%"), "of manufactured exports"),
          ("Tertiary enrolment", fmt(iv("tertiary_enrol"), 0, "%"), "human capital"),
          ("Female labour participation", fmt(iv("female_lfp"), 1, "%"), "labour"),
          ("Electricity access", fmt(iv("electricity"), 0, "%"), "infrastructure")])

    html(section("Real-time prediction"))
    c1, c2 = st.columns([3, 1])
    with c2:
        if st.button("▶ Re-run forecast now", width="stretch"):
            t0 = time.time()
            st.session_state[f"refit_{ISO}"] = {k: S.refit(ISO, k) for k in ("gdp_real", "unemp", "emp_ratio")}
            st.session_state[f"refit_meta_{ISO}"] = (time.time() - t0, datetime.now().strftime("%H:%M:%S"))
        try:
            la = get_live(ISO)
            nc = la["nowcast"]
        except Exception:
            la, nc = None, None
        if nc:
            html(kpi(f"Live nowcast {nc['year']}", fmt(nc["nowcast"], 2, "%"), f"computed {nc['computed_at']}"))
        meta = st.session_state.get(f"refit_meta_{ISO}")
        if meta:
            st.caption(f"Ensemble re-fitted live at {meta[1]} in {meta[0] * 1000:.0f} ms (4 models × 3 series).")
    refit = st.session_state.get(f"refit_{ISO}", {})
    with c1:
        gh = S.history(ISO, "gdp_growth")
        gf = refit.get("gdp_real") if refit.get("gdp_real") is not None else S.fc(ISO, "gdp_real")
        lvl = pd.concat([S.history(ISO, "gdp_real"), gf.set_index("year").value])
        gfg = (lvl.pct_change() * 100).loc[gf.year.min():]
        imf = live.PROCESSED_IMF()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=gh.index, y=gh.values, name="Actual", line=dict(color=INK["primary"], width=2)))
        fig.add_trace(go.Scatter(x=gfg.index, y=gfg.values, name="AsiaPulse forecast", line=dict(color=SERIES[0], width=2, dash="dash")))
        if imf is not None and ISO in imf.index:
            ip = imf.loc[ISO].dropna()
            ip.index = ip.index.astype(int)
            ip = ip[ip.index > gh.index.max()]
            fig.add_trace(go.Scatter(x=ip.index, y=ip.values, name="IMF WEO", line=dict(color=SERIES[1], width=2)))
        if nc and pd.notna(nc["nowcast"]):
            fig.add_trace(go.Scatter(x=[nc["year"]], y=[nc["nowcast"]], name="Live nowcast", mode="markers",
                                     marker=dict(size=13, color=SERIES[2], line=dict(color="#fff", width=2))))
        fig.add_hline(y=0, line_color=INK["axis"], line_width=1)
        show(fig_layout(fig, 330, "Real GDP growth (%) · actual, forecasts and live nowcast"))

    html(section("Outlook to 2035 · ensemble forecast with calibrated 80% interval"))
    cols = st.columns(3)
    for col, key, scale, ttl in [(cols[0], "gdp_real", 1e9, "Real GDP (constant 2015 US$ bn)"),
                                 (cols[1], "unemp", 1, "Unemployment rate (%)"),
                                 (cols[2], "emp_ratio", 1, "Employment-to-population, 15+ (%)")]:
        h = S.history(ISO, key) / scale
        f = refit.get(key) if refit.get(key) is not None else S.fc(ISO, key)
        fig = go.Figure()
        if f is not None and len(f):
            fig.add_trace(go.Scatter(x=list(f.year) + list(f.year[::-1]), y=list(f.hi / scale) + list(f.lo[::-1] / scale),
                                     fill="toself", fillcolor=BAND, line=dict(width=0), name="80% interval", hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=[h.index[-1]] + list(f.year), y=[h.values[-1]] + list(f.value / scale),
                                     name="Forecast", line=dict(color=SERIES[0], width=2, dash="dash")))
        fig.add_trace(go.Scatter(x=h.index, y=h.values, name="Actual", line=dict(color=INK["primary"], width=2)))
        v = val["series"].get(key, {})
        with col:
            show(fig_layout(fig, 290, ttl))
            st.caption(f"Confidence: **{v.get('confidence', 'n/a')}** · held-out error {fmt(v.get('error'), 2)} "
                       f"{'%' if key == 'gdp_real' else 'pp'} · skill vs naive {fmt(v.get('skill_vs_naive'), 2)}")

    html(section("Diagnosis"))
    l, r = st.columns([1.15, 1], gap="medium")
    with l:
        own = pd.Series({PNAMES[c]: S.scores.loc[ISO, c] for c in PCOLS}).dropna().sort_values()
        members = S.clusters.index[S.clusters.cluster == S.clusters.loc[ISO, "cluster"]]
        peer = pd.Series({PNAMES[c]: S.scores.loc[members, c].median() for c in PCOLS}).reindex(own.index)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=own.values, y=own.index, orientation="h", name=country, marker_color=SERIES[0],
                             marker_line_width=0, hovertemplate="%{y}: %{x:.0f}<extra></extra>"))
        fig.add_trace(go.Scatter(x=peer.values, y=peer.index, mode="markers", name="Peer-group median",
                                 marker=dict(symbol="diamond", size=10, color=INK["primary"], line=dict(color="#fff", width=1.5)),
                                 hovertemplate="Peer median: %{x:.0f}<extra></extra>"))
        fig.update_xaxes(range=[0, 100], showgrid=True, title="Vulnerability score (higher = weaker than Asian peers)")
        fig.update_layout(hovermode="closest")
        show(fig_layout(fig, 450, "Vulnerability by policy area"))
    with r:
        html(f'<div class="card"><h4>Red flags ({len(risk["red_flags"])})</h4>'
             '<div class="muted">Absolute thresholds with a stated basis — not relative rankings.</div></div>')
        if not risk["red_flags"]:
            html('<div class="note-box">No threshold-based red flags.</div>')
        for fl in risk["red_flags"]:
            html(f'<div class="flag">🚩<div><b>{esc(fl["flag"])}</b> — value {fmt(fl["value"], 2)}'
                 f'<small>{esc(fl["basis"])}</small></div></div>')
        html(f'<div class="card"><h4>Nearest peers</h4><div>{" · ".join(esc(p["country"]) for p in peers["nearest_peers"])}</div>'
             f'<div class="muted" style="margin-top:6px">Profile: {esc(peers["economic_profile"])}</div></div>')
    with st.expander("All indicators for this economy (latest value, year, source area)"):
        rows = [{"Indicator": d["label"], "Value": d["value"], "Unit": d["unit"], "Year": d["year"],
                 "Area": PILLAR_LABELS.get(BY_KEY[k].pillar, BY_KEY[k].pillar.title()) if k in BY_KEY else "Derived"}
                for k, d in ind.items()]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# ================================================================ POLICY LAB
LEVER_UI = [
    ("demand_shock_pp", "Global demand shock (growth, pp)", -5.0, 3.0, 0.25, "shock"),
    ("oil_price_pct", "Oil-price change (%)", -60.0, 100.0, 5.0, "shock"),
    ("remittance_pct", "Remittance inflows change (%)", -50.0, 30.0, 5.0, "shock"),
    ("fiscal_consolidation_pp", "Fiscal consolidation (primary balance, % GDP)", -3.0, 5.0, 0.25, "policy"),
    ("public_investment_pp", "Extra public investment (% GDP per year)", 0.0, 4.0, 0.25, "policy"),
    ("flfp_increase_pp", "Raise female labour participation by 2035 (pp)", 0.0, 20.0, 1.0, "policy"),
    ("digital_adoption_pp", "Raise internet adoption by 2035 (pp)", 0.0, 50.0, 5.0, "policy"),
    ("interest_rate_pp", "Change in interest rate on public debt (pp)", -3.0, 5.0, 0.25, "policy"),
]
for _n, *_ in LEVER_UI:
    st.session_state.setdefault(f"lv_{_n}", 0.0)


def _load_package(lever: dict):
    for name, *_ in LEVER_UI:
        st.session_state[f"lv_{name}"] = float(lever.get(name, 0.0))


def _reset_levers():
    _load_package({})


def _live_oil():
    try:
        st.session_state["lv_oil_price_pct"] = float(round(live.oil_move(get_global()) / 5) * 5)
    except Exception:
        pass


def page_policy():
    pols = S.policies(ISO, top_n=6)
    html(page_head(f"Policy lab · {country}",
                   "Ranked policy packages for the diagnosed vulnerabilities, each with SDG targets, a measurable KPI, "
                   "a peer-based target and Asian precedents — then test them in the scenario simulator.",
                   chip(S.scores.loc[ISO, "label"])))
    for i, p in enumerate(pols, 1):
        with st.expander(f"**{i}. {p['title']}** · {p['horizon']} · priority {p['priority']:.0f}/100", expanded=i <= 2):
            a, b = st.columns([1.6, 1], gap="medium")
            with a:
                st.markdown(f"**Why now:** {p['trigger']}  \n**Objective:** {p['objective']}")
                st.markdown("\n".join(f"- {x}" for x in p["actions"]))
                st.caption(f"Lead: {p['lead']} · {' · '.join(p['sdgs'])} · Area: {p['pillar']}")
            with b:
                html(kpi(p["kpi_label"], fmt(p["kpi_now"], 2),
                         f"Peer-group target: {fmt(p['kpi_peer_target'], 2)}" if p["kpi_peer_target"] is not None else ""))
                if p["precedents"]:
                    rows = "".join(f"<div><span>{esc(d['country'])}</span><span>{fmt(d['from'], 1)} ({d['from_year']}) → "
                                   f"<b>{fmt(d['to'], 1)}</b> ({d['to_year']})</span></div>" for d in p["precedents"])
                    html(f'<div class="card" style="margin-top:8px"><div class="muted">Precedents · largest 10-year improvement in Asia</div>'
                         f'<div class="rowlist">{rows}</div></div>')
                if p["lever"]:
                    st.button("Simulate this package ↓", key=f"sim_{p['key']}", on_click=_load_package, args=(p["lever"],))

    html(section("Scenario simulator"))
    html('<div class="note-box">Baseline = validated forecast. Unemployment responds through Okun\'s law estimated for this '
         'economy; public debt follows the IMF debt-dynamics identity with the country\'s IMF-implied interest rate. '
         'Shocks fade 50% a year. <b>Scenarios are simulations, not forecasts.</b></div>')
    st.write("")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**External shocks**")
        for name, lab, lo, hi, step, grp in LEVER_UI:
            if grp == "shock":
                st.slider(lab, lo, hi, step=step, key=f"lv_{name}")
        st.button("⚡ Use today's live oil move", on_click=_live_oil,
                  help="Sets the oil shock to Brent's latest 30-day average vs its prior 12-month average.")
    with c2:
        st.markdown("**Policy levers**")
        for name, lab, lo, hi, step, grp in LEVER_UI:
            if grp == "policy":
                st.slider(lab, lo, hi, step=step, key=f"lv_{name}")
    with st.expander("Model assumptions (editable)"):
        a1, a2, a3, a4 = st.columns(4)
        fm = a1.number_input("Fiscal multiplier", 0.0, 2.0, 0.5, 0.1)
        im = a2.number_input("Investment multiplier", 0.0, 2.0, 0.8, 0.1)
        de = a3.number_input("Digital elasticity (% GDP per pp)", 0.0, 0.3, 0.05, 0.01)
        ise = a4.number_input("Investment supply effect", 0.0, 0.5, 0.1, 0.05)
    st.button("Reset levers", on_click=_reset_levers)

    lv = Levers(**{name: float(st.session_state[f"lv_{name}"]) for name, *_ in LEVER_UI},
                fiscal_multiplier=fm, investment_multiplier=im, digital_elasticity=de, investment_supply_effect=ise)
    path, summ = S.scenario(ISO, lv)
    d_risk = summ["risk_scenario"]["score"] - summ["risk_baseline"]["score"]
    kpis([("GDP level in 2035 vs baseline", fmt(summ["gdp_end_diff_pct"], 2, "%", "+" if summ["gdp_end_diff_pct"] > 0 else ""), "",
           "up" if summ["gdp_end_diff_pct"] > 0.005 else "down" if summ["gdp_end_diff_pct"] < -0.005 else None),
          ("Average growth", fmt(summ["cagr_scen"], 2, "%"), f"baseline {fmt(summ['cagr_base'], 2, '%')}"),
          ("Unemployment 2035", fmt(summ["unemp_end_scen"], 1, "%"), f"peak change {summ['peak_unemp_diff_pp']:+.2f} pp"),
          ("Public debt 2035", fmt(summ["debt_end_scen"], 1, "% GDP"), f"baseline {fmt(summ['debt_end_base'], 1, '% GDP')}"),
          ("Vulnerability", f"{fmt(summ['risk_scenario']['score'], 1)} {chip(summ['risk_scenario']['label'])}",
           f"{d_risk:+.1f} vs baseline", "up" if d_risk < -0.05 else "down" if d_risk > 0.05 else None)])
    cols = st.columns(3)
    for col, (b_, s_, ttl) in zip(cols, [("growth_base", "growth_scen", "Real GDP growth (%)"),
                                         ("unemp_base", "unemp_scen", "Unemployment rate (%)"),
                                         ("debt_base", "debt_scen", "Public debt (% of GDP)")]):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=path.year, y=path[b_], name="Baseline", line=dict(color=SERIES[0], width=2)))
        fig.add_trace(go.Scatter(x=path.year, y=path[s_], name="Scenario", line=dict(color=SERIES[1], width=2)))
        with col:
            show(fig_layout(fig, 290, ttl))
    notes = [f"Okun coefficient {summ['okun_beta']:.2f}", f"inflation {summ['inflation_assumed']:.1f}%",
             f"interest on debt {summ['nominal_rate_assumed']:.1f}% ({'IMF-implied' if summ['rate_from_data'] else 'assumed'})",
             f"baseline primary balance {summ['primary_balance_assumed']:.1f}% GDP"]
    if summ["debt_assumed"]:
        notes.append("⚠ public debt not reported — 50% of GDP assumed")
    st.caption("Assumptions: " + " · ".join(notes))


# ================================================================ AI ANALYST
def page_ai():
    cfg = qwen_settings()
    html(page_head("AI policy analyst",
                   "A Qwen agent that decides which experts to consult, calls them as tools, and writes a brief using only "
                   "their outputs. Every number in the answer is then verified against the tool outputs.",
                   f"Model: {esc(cfg['model']) if cfg['api_key'] else 'offline analyst'}"))
    key = f"chat_{ISO}"
    st.session_state.setdefault(key, [])
    sugg = [f"Give me a full policy assessment of {country}.",
            f"What are the three most urgent reforms for {country}?",
            f"What if oil prices rise 50% and remittances fall 20%?",
            f"How can technology and digital adoption lift {country}'s growth?",
            f"How trustworthy are the forecasts for {country}?",
            f"Compare {country} with its nearest peers."]
    cols = st.columns(3)
    clicked = None
    for i, q in enumerate(sugg):
        if cols[i % 3].button(q, key=f"sugg_{i}", width="stretch"):
            clicked = q
    for turn in st.session_state[key]:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
            res = turn.get("result")
            if res:
                gr = res.grounding
                ok = gr.get("ratio", 1) >= 0.95
                html(f'{chip("Low" if ok else "Elevated").replace("● Low", "✓ Grounded").replace("◆ Elevated", "⚠ Check")} '
                     f'<span class="muted">{gr.get("verified", 0)}/{gr.get("checked", 0)} numbers verified against expert '
                     f'outputs · mode: {res.mode}</span>')
                if gr.get("unverified"):
                    st.caption("Not found in tool outputs (derived or unverified): " + ", ".join(gr["unverified"]))
                with st.expander(f"Agent trace · {len(res.trace)} expert calls"):
                    st.dataframe(pd.DataFrame(res.trace), width="stretch", hide_index=True)
                    if res.error:
                        st.caption(res.error)
    q = st.chat_input(f"Ask about {country}…") or clicked
    if q:
        st.session_state[key].append({"role": "user", "content": q})
        with st.spinner("Consulting Pattern · Forecast · Validation · Risk · Policy experts…"):
            history = [{"role": t["role"], "content": t["content"]} for t in st.session_state[key][:-1]]
            res = ask(S, q, country, history)
        st.session_state[key].append({"role": "assistant", "content": res.answer, "result": res})
        st.rerun()
    last = next((t for t in reversed(st.session_state[key]) if t.get("result")), None)
    if last:
        md = markdown_brief(country, last["content"], S.risk(ISO), S.policies(ISO), META)
        d1, d2, d3 = st.columns([1, 1, 3])
        d1.download_button("⬇ Policy brief (PDF)", pdf_brief(md), file_name=f"AsiaPulse_{ISO}_policy_brief.pdf",
                           mime="application/pdf")
        d2.download_button("⬇ Markdown", md, file_name=f"AsiaPulse_{ISO}_policy_brief.md")
        if d3.button("Clear conversation"):
            st.session_state[key] = []
            st.rerun()


# ================================================================ COMPARE
def page_compare():
    html(page_head("Compare economies", "Side-by-side indicators, vulnerability by policy area and trends over time.", ""))
    defaults = [c for c in [country] + [p["country"] for p in S.peers(ISO)["nearest_peers"][:2]] if c in COUNTRIES]
    picks = st.multiselect("Select 2–6 economies", COUNTRIES, default=defaults, max_selections=6)
    if len(picks) < 2:
        html('<div class="note-box">Select at least two economies.</div>')
        return
    isos = [S.iso(c) for c in picks]
    df = pd.DataFrame(S.compare(isos)).set_index("country")
    st.dataframe(df.rename(columns={"profile": "Profile", "gdp_growth_5y_avg": "Growth 5y %", "gdp_cagr_fc": "Fcst CAGR %",
                                    "gdp_pc_ppp": "GDP pc PPP", "unemp": "Unemp %", "youth_unemp": "Youth unemp %",
                                    "female_lfp": "Female LFP %", "inflation": "Inflation %", "gov_debt": "Debt % GDP",
                                    "vulnerability": "Vulnerability", "risk_label": "Level"}).round(2), width="stretch")
    a, b = st.columns([1, 1], gap="medium")
    with a:
        z = S.scores.loc[isos, PCOLS].rename(columns=PNAMES)
        fig = go.Figure(go.Heatmap(z=z.T.values, x=[S.snap.loc[i, "country"] for i in isos], y=list(z.columns),
                                   colorscale=BLUE_RAMP, zmin=0, zmax=100, xgap=3, ygap=3,
                                   text=np.round(z.T.values), texttemplate="%{text:.0f}", colorbar=dict(thickness=10),
                                   hovertemplate="<b>%{x}</b><br>%{y}: %{z:.0f}<extra></extra>"))
        fig.update_layout(hovermode="closest")
        show(fig_layout(fig, 470, "Vulnerability by policy area (higher = weaker)", legend=False))
    with b:
        opts = {i.label: i.key for i in INDICATORS if i.key in S.panel.columns and i.pillar != "context"}
        pick = st.selectbox("Indicator over time", list(opts), index=list(opts).index(BY_KEY["internet"].label))
        fig = go.Figure()
        for j, i_ in enumerate(isos):
            h = S.history(i_, opts[pick])
            fig.add_trace(go.Scatter(x=h.index, y=h.values, name=S.snap.loc[i_, "country"],
                                     line=dict(color=SERIES[j], width=2)))
        show(fig_layout(fig, 400, pick))


# ================================================================ METHODOLOGY
def page_method():
    html(page_head("Methodology & data", "How every number is produced, validated and explained.",
                   f"Pipeline run {META['generated_utc']} UTC"))
    steps = [("1 · Data", f"{N_VARS} variables from World Bank WDI & WGI and IMF WEO (via DBnomics), fetched by API with source and year kept for every value."),
             ("2 · Real-time layer", "Daily market data (Brent, VIX, US yields, dollar, gold, Asian FX and equity indices) feeds a live growth nowcast and a live stress index."),
             ("3 · Pattern", f"K-Means on standardised structural features; k = {META['cluster']['k']} chosen by silhouette ({META['cluster']['silhouette']}); names generated from centroids."),
             ("4 · Forecast", "Ensemble of naive, drift, damped-Holt and trend models; weights = inverse squared backtest error per economy; intervals calibrated (split-conformal)."),
             ("5 · Validate", f"Rolling-origin backtests: weights and calibration learned on origins {META['backtest_design']['fit_origins']}, scored on held-out {META['backtest_design']['heldout_origins']} (incl. COVID); benchmarked against IMF WEO."),
             ("6 · Risk, policy & AI", "12-area percentile index + 31 absolute red-flag rules → ranked SDG-tagged policy packages → scenario model → Qwen agent with tool calls and a grounding check.")]
    cols = st.columns(3)
    for i, (t, d) in enumerate(steps):
        cols[i % 3].markdown(f'<div class="card"><h4>{esc(t)}</h4><div style="font-size:.88rem;color:{INK["secondary"]}">{esc(d)}</div></div>',
                             unsafe_allow_html=True)

    html(section("Forecast validation (held-out)"))
    bo = pd.DataFrame(META["backtest_overall"])
    cal = META["interval_calibration"]
    bo["unit"] = bo.series.map(lambda s: "MAPE %" if s.startswith("gdp") else "MAE pp")
    bo["coverage_raw"] = bo.series.map(lambda s: cal[s]["coverage_raw_heldout"])
    st.dataframe(bo.rename(columns={"series": "Series", "median_error": "Median error", "median_skill": "Median skill vs naive",
                                    "share_beating_naive": "Share beating naive", "coverage80": "80% coverage (calibrated)",
                                    "coverage_raw": "Coverage before calibration"}), width="stretch", hide_index=True)
    st.caption("Skill = 1 − error ÷ naive error (positive = better than 'no change'). GDP forecasts beat the naive benchmark; for "
               "labour-market ratios 'no change' is hard to beat, so the ensemble learns to lean on it — reported, not hidden.")
    hz = S.backtest_h
    fig = go.Figure()
    for j, (k, g_) in enumerate(hz.groupby("series")):
        fig.add_trace(go.Scatter(x=g_.h, y=g_.coverage80, name=k, mode="lines+markers", line=dict(color=SERIES[j], width=2),
                                 marker=dict(size=8)))
    fig.add_hline(y=0.8, line_dash="dot", line_color=INK["muted"], annotation_text="target 80%")
    fig.update_xaxes(title="Horizon (years)")
    show(fig_layout(fig, 300, "Calibrated 80% interval coverage by horizon (held-out)"))

    html(section("Real-time layer"))
    st.markdown("""
- **Nowcast** = average of the AsiaPulse ensemble and IMF WEO for the current year, **plus** an oil adjustment: the Policy-Lab
  oil elasticity × the move in Brent's 30-day average vs its prior 12-month average × share of the year still ahead.
- **Market stress (0–100)** averages: 3-month currency depreciation (15% = 100), currency-volatility z-score (only when
  annualised volatility ≥ 4%), equity drawdown from the 52-week high (30% = 100), oil-price exposure (importer vs exporter),
  and global risk appetite (VIX 15→40). Pegged currencies are excluded from FX signals.
- **Live risk** = 70% structural vulnerability + 30% market stress. Data refresh every 15 minutes; the page auto-refreshes every 5.
""")
    html(section("Risk areas and red-flag rules"))
    st.dataframe(pd.DataFrame([{"Area": PILLAR_LABELS[p], "Indicators (direction)": ", ".join(f"{f} ({'+' if d > 0 else '−'})" for f, d in feats)}
                               for p, feats in PILLARS.items()]), width="stretch", hide_index=True)
    st.dataframe(pd.DataFrame([{"Flag": f.text, "Rule": f"{f.feature} {f.op} {f.threshold}", "Basis": f.basis} for f in FLAGS]),
                 width="stretch", hide_index=True)
    st.caption("Levels: " + " · ".join(f"{lab} ≥ {cut}" for cut, lab in LEVELS if cut) + " · Low otherwise.")

    html(section("Data sources"))
    man = pd.DataFrame(META["indicators"])
    reg = pd.DataFrame([{"key": i.key, "label": i.label, "area": PILLAR_LABELS.get(i.pillar, i.pillar.title())} for i in INDICATORS])
    st.dataframe(man.merge(reg, on="key", how="left")[["label", "area", "code", "source", "countries", "latest_year", "status"]],
                 width="stretch", hide_index=True)
    html(section("Responsible AI & limitations"))
    st.markdown(f"""
- **Coverage:** {', '.join(f'{k} ({v})' for k, v in META['excluded'].items())}.
- **Relative index:** vulnerability ranks economies *within Asia*; "Low" is not an absolute all-clear.
- **Data lags:** each value carries its year; values beyond a per-indicator staleness limit are treated as missing, never imputed for scoring.
- **Market data:** from a public endpoint without a service-level guarantee; when unavailable the last cached values are used and marked.
- **Scenario model:** a small structural model with editable assumptions for exploring direction and magnitude, not a forecast.
- **AI:** the model never computes numbers; it explains tool outputs, and every number is verified. Decision support, not financial advice.
""")


{"Overview": page_overview, "Live monitor": page_live, "Country profile": page_country, "Policy lab": page_policy,
 "AI analyst": page_ai, "Compare": page_compare, "Methodology": page_method}[page]()

html('<div style="text-align:center;margin-top:40px;color:#898781;font-size:.75rem">AsiaPulse AI · World Bank WDI/WGI · '
     'IMF WEO · market data via Yahoo Finance · decision support, not financial advice</div>')
