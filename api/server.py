"""AsiaPulse AI — web API + dashboard server.

    python -m uvicorn api.server:app --port 8000      (or: python run.py)

Serves the single-page dashboard from /web and JSON endpoints under /api that wrap the
pipeline outputs (Store), the real-time layer (live), the scenario model and the Qwen agent.
"""
from __future__ import annotations

import math
import sys
import threading
import time
from dataclasses import fields
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from asiapulse import live  # noqa: E402
from asiapulse.agents.orchestrator import ask  # noqa: E402
from asiapulse.config import qwen_settings  # noqa: E402
from asiapulse.indicators import BY_KEY, INDICATORS, PILLAR_LABELS  # noqa: E402
from asiapulse.models.forecast import SERIES  # noqa: E402
from asiapulse.models.risk import FLAGS, LEVELS, PILLARS, risk_label  # noqa: E402
from asiapulse.models.scenario import Levers  # noqa: E402
from asiapulse.report.brief import markdown_brief, pdf_brief  # noqa: E402
from asiapulse.store import Store  # noqa: E402

app = FastAPI(title="AsiaPulse AI", version="3.0")
S = Store()
N_VARS = len(INDICATORS) + 3
PCOLS = [c for c in S.scores.columns if c.startswith("pillar_")]
PKEYS = [c.replace("pillar_", "") for c in PCOLS]
SMALL_STATES = {"SGP": [103.82, 1.35], "MDV": [73.5, 3.2], "BHR": [50.55, 26.07]}


# ---------------------------------------------------------------- JSON helpers
def clean(o):
    """Recursively convert numpy/pandas objects into JSON-safe Python (NaN → null)."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, pd.Series):
        return [[_ts(i), clean(v)] for i, v in o.items()]
    if isinstance(o, pd.DataFrame):
        return clean(o.to_dict("records"))
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return _ts(o)
    return o


def _ts(i):
    if isinstance(i, (pd.Timestamp, datetime)):
        return i.strftime("%Y-%m-%d")
    if isinstance(i, (np.integer,)):
        return int(i)
    return i


def J(o):
    return JSONResponse(clean(o))


def _iso(x: str) -> str:
    try:
        return S.iso(x)
    except KeyError:
        raise HTTPException(404, f"Unknown economy {x}")


def _hist(iso, key, scale=1.0):
    h = S.history(iso, key)
    return [[int(y), v / scale] for y, v in h.items()]


# ---------------------------------------------------------------- warm caches in background
def _warm():
    try:
        live.global_snapshot()
        live.regional_fx(list(S.snap.index))
    except Exception:
        pass


threading.Thread(target=_warm, daemon=True).start()


# ---------------------------------------------------------------- endpoints
@app.get("/api/meta")
def meta():
    m = S.meta
    sc = S.scores.join(S.snap[["country", "region"]]).join(S.clusters[["cluster_name"]])
    cfg = qwen_settings()
    return J({
        "generated_utc": m["generated_utc"], "reference_year": m["reference_year"], "forecast_end": m["forecast_end"],
        "economies": m["economies_covered"], "variables": N_VARS, "excluded": m["excluded"],
        "ai": {"live": bool(cfg["api_key"]), "model": cfg["model"]},
        "pillars": [{"key": k, "label": PILLAR_LABELS[k]} for k in PKEYS],
        "countries": [{"iso3": i, "name": r.country, "region": r.region, "score": r.composite, "label": r.label,
                       "profile": r.cluster_name} for i, r in sc.sort_values("country").iterrows()],
        "levels": [{"label": lab, "min": cut} for cut, lab in LEVELS],
    })


@app.get("/api/overview")
def overview():
    sc = S.scores.join(S.snap[["country", "region", "gdp_cagr_fc", "population", "imf_growth_2026_30", "gdp_usd"]]) \
        .join(S.clusters[["cluster_name", "cluster", "pc1", "pc2"]])
    nflags = S.flags.groupby("iso3").size() if len(S.flags) else pd.Series(dtype=int)
    rows = []
    for iso, r in sc.iterrows():
        rows.append({"iso3": iso, "name": r.country, "region": r.region, "score": r.composite, "label": r.label,
                     "rank": r["rank"], "coverage": r.coverage, "cagr": r.gdp_cagr_fc, "imf_growth": r.imf_growth_2026_30,
                     "population": r.population, "gdp_usd": r.gdp_usd, "profile": r.cluster_name, "cluster": r.cluster,
                     "pc": [r.pc1, r.pc2], "flags": int(nflags.get(iso, 0)),
                     "pillars": {k: r[f"pillar_{k}"] for k in PKEYS}})
    high = sc[sc.label == "High"]
    return J({"rows": rows, "small_states": SMALL_STATES,
              "kpis": {"economies": len(sc), "variables": N_VARS, "high": len(high),
                       "high_pop_m": high.population.sum() / 1e6, "median_cagr": sc.gdp_cagr_fc.median(),
                       "flags": len(S.flags), "median_imf": sc.imf_growth_2026_30.median()},
              "clusters": S.meta["cluster"]})


def _outlook_rows():
    """10-year growth forecast per economy: base year (last actual) → 2035."""
    fc, bt = S.forecasts, S.backtest
    rows = []
    for iso in S.snap.index:
        h = S.history(iso, "gdp_real")
        f = fc[(fc.iso3 == iso) & (fc.series == "gdp_real")].set_index("year")
        if h.empty or f.empty:
            continue
        y0, g0 = int(h.index.max()), float(h.iloc[-1])
        y1 = int(f.index.max())
        n = y1 - y0
        cagr = lambda end: ((end / g0) ** (1 / n) - 1) * 100 if end and end > 0 else None  # noqa: E731
        pc_h, pc_f = S.history(iso, "gdp_pc_ppp"), fc[(fc.iso3 == iso) & (fc.series == "gdp_pc_ppp")]
        pc_cagr = (((pc_f.value.iloc[-1] / pc_h.iloc[-1]) ** (1 / (int(pc_f.year.iloc[-1]) - int(pc_h.index.max()))) - 1) * 100
                   if len(pc_h) and len(pc_f) else None)
        v = bt[(bt.iso3 == iso) & (bt.series == "gdp_real")]
        path = pd.concat([h, f.value])
        growth_path = (path.pct_change() * 100).loc[y0 + 1:]
        rows.append({
            "iso3": iso, "name": S.snap.loc[iso, "country"], "region": S.snap.loc[iso, "region"],
            "profile": S.clusters.loc[iso, "cluster_name"], "base_year": y0, "end_year": y1, "years": n,
            "gdp_base_bn": g0 / 1e9, "gdp_end_bn": f.value.iloc[-1] / 1e9,
            "gdp_end_lo_bn": f.lo.iloc[-1] / 1e9, "gdp_end_hi_bn": f.hi.iloc[-1] / 1e9,
            "cagr": cagr(f.value.iloc[-1]), "cagr_lo": cagr(f.lo.iloc[-1]), "cagr_hi": cagr(f.hi.iloc[-1]),
            "multiple": f.value.iloc[-1] / g0, "pc_cagr": pc_cagr,
            "imf_2026_30": S.snap.loc[iso].get("imf_growth_2026_30"), "hist_10y": S.history(iso, "gdp_growth").tail(10).mean(),
            "confidence": v.confidence.iloc[0] if len(v) else "Unavailable",
            "mape": v.error.iloc[0] if len(v) else None, "skill": v.skill_vs_naive.iloc[0] if len(v) else None,
            "risk_label": S.scores.loc[iso, "label"],
            "path": [[int(y), g] for y, g in growth_path.items()],
        })
    return rows


_OUTLOOK: dict = {}


@app.get("/api/outlook")
def outlook():
    if "v" in _OUTLOOK:
        return _OUTLOOK["v"]
    rows = _outlook_rows()
    df = pd.DataFrame(rows)
    # Asia aggregate: sum of real GDP (constant 2015 US$) across covered economies, per year.
    fc = S.forecasts[S.forecasts.series == "gdp_real"].pivot(index="iso3", columns="year", values="value")
    hist = S.panel["gdp_real"].unstack("year")
    wide = hist.combine_first(fc).loc[df.iso3]
    agg = [[int(y), float(wide[y].sum()) / 1e12] for y in wide.columns if 2015 <= y <= int(fc.columns.max())]
    base_y = int(df.base_year.mode().iloc[0])
    a0 = dict(agg)[base_y]
    a1 = agg[-1][1]
    asia_cagr = ((a1 / a0) ** (1 / (agg[-1][0] - base_y)) - 1) * 100
    top_gainer = df.assign(add=df.gdp_end_bn - df.gdp_base_bn).sort_values("add", ascending=False)
    _OUTLOOK["v"] = J({
        "rows": rows, "aggregate": agg, "base_year": base_y, "end_year": int(agg[-1][0]),
        "summary": {"asia_cagr": asia_cagr, "asia_base_tn": a0, "asia_end_tn": a1,
                    "median_cagr": df.cagr.median(), "n": len(df),
                    "fastest": df.sort_values("cagr", ascending=False).head(1)[["name", "cagr"]].to_dict("records")[0],
                    "slowest": df.sort_values("cagr").head(1)[["name", "cagr"]].to_dict("records")[0],
                    "above_5": int((df.cagr >= 5).sum()), "contracting": int((df.cagr < 0).sum()),
                    "biggest_gain": {"name": top_gainer.name.iloc[0], "add_bn": float(top_gainer["add"].iloc[0])}},
    })
    return _OUTLOOK["v"]


@app.get("/api/country/{c}")
def country(c: str):
    iso = _iso(c)
    fc = {}
    for key, scale in (("gdp_real", 1e9), ("unemp", 1), ("emp_ratio", 1), ("gdp_pc_ppp", 1)):
        f = S.fc(iso, key)
        fc[key] = {"label": SERIES[key][3], "history": _hist(iso, key, scale),
                   "forecast": [[int(r.year), r.value / scale, r.lo / scale, r.hi / scale] for r in f.itertuples()]}
    gh = _hist(iso, "gdp_growth")
    f = S.fc(iso, "gdp_real")
    lvl = pd.concat([S.history(iso, "gdp_real"), f.set_index("year").value])
    g_fc = (lvl.pct_change() * 100).loc[f.year.min():] if len(f) else pd.Series(dtype=float)
    imf = live.PROCESSED_IMF()
    imf_path = []
    if imf is not None and iso in imf.index:
        ip = imf.loc[iso].dropna()
        imf_path = [[int(y), v] for y, v in ip.items() if int(y) >= 2015]
    prof = S.profile(iso)
    members = S.clusters.index[S.clusters.cluster == S.clusters.loc[iso, "cluster"]]
    peer_med = {k: S.scores.loc[members, f"pillar_{k}"].median() for k in PKEYS}
    asia_med = {k: S.scores[f"pillar_{k}"].median() for k in PKEYS}
    indicators = [{"key": k, **d, "area": PILLAR_LABELS.get(BY_KEY[k].pillar, BY_KEY[k].pillar.title()) if k in BY_KEY else "Derived"}
                  for k, d in prof["indicators"].items()]
    return J({"iso3": iso, "profile": prof, "risk": S.risk(iso), "validation": S.validation(iso), "peers": S.peers(iso),
              "policies": S.policies(iso, top_n=6), "forecast": fc, "forecast_summary": S.forecast(iso),
              "growth": {"actual": gh, "forecast": [[int(y), v] for y, v in g_fc.items()], "imf": imf_path},
              "pillars": {k: S.scores.loc[iso, f"pillar_{k}"] for k in PKEYS}, "peer_median": peer_med,
              "asia_median": asia_med, "indicators": indicators})


@app.post("/api/refit/{c}")
def refit(c: str):
    iso = _iso(c)
    t0 = time.time()
    out = {}
    for key, scale in (("gdp_real", 1e9), ("unemp", 1), ("emp_ratio", 1)):
        f = S.refit(iso, key)
        out[key] = [] if f is None else [[int(r.year), r.value / scale, r.lo / scale, r.hi / scale] for r in f.itertuples()]
    return J({"forecast": out, "ms": (time.time() - t0) * 1000, "at": datetime.now().strftime("%H:%M:%S")})


def _series(s: pd.Series, n=400):
    s = s.dropna()
    return [[i.strftime("%Y-%m-%d"), float(v)] for i, v in s.tail(n).items()]


@app.get("/api/live/global")
def live_global():
    g = live.global_snapshot()
    return J({"at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "oil_move": live.oil_move(g),
              "items": [{"key": k, "label": v["label"], "unit": v["unit"], "price": v["price"], "as_of": v["as_of"],
                         "stale": v["stale"], "chg_1m": v["chg_1m"], "chg_3m": v["chg_3m"], "chg_1y": v["chg_1y"],
                         "series": _series(v["series"], 260)} for k, v in g.items()]})


@app.get("/api/live/country/{c}")
def live_country(c: str):
    iso = _iso(c)
    g = live.global_snapshot()
    a = live.live_assessment(S, iso, g)
    sig = a["signals"]
    fx, eq = sig.get("fx"), sig.get("equity")
    hist = live.nowcast_history(iso)
    return J({
        "iso3": iso, "at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "nowcast": a["nowcast"],
        "structural": a["structural"], "live_risk": a["live_risk"], "live_label": risk_label(a["live_risk"]),
        "stress": a["stress"], "alerts": a["alerts"], "pegged": sig["pegged"],
        "fx": None if not fx else {k: v for k, v in fx.items() if k != "series"} | {"series": _series(fx["series"])},
        "equity": None if not eq else {k: v for k, v in eq.items() if k != "series"} | {"series": _series(eq["series"])},
        "history": hist.to_dict("records") if len(hist) else [],
    })


@app.get("/api/live/regional-fx")
def live_fx():
    d = live.regional_fx(list(S.snap.index))
    if len(d):
        d["name"] = d.iso3.map(S.snap.country)
    return J(d.sort_values("depr_3m").to_dict("records") if len(d) else [])


class ScenarioIn(BaseModel):
    levers: dict = {}


@app.post("/api/scenario/{c}")
def scenario(c: str, body: ScenarioIn):
    iso = _iso(c)
    valid = {f.name for f in fields(Levers)}
    lv = Levers(**{k: float(v) for k, v in body.levers.items() if k in valid and v is not None})
    path, summ = S.scenario(iso, lv)
    return J({"path": path.to_dict("list"), "summary": summ})


@app.get("/api/live-oil")
def live_oil():
    return J({"oil_move": live.oil_move(live.global_snapshot())})


class AskIn(BaseModel):
    question: str
    history: list = []


@app.post("/api/ask/{c}")
def ask_ep(c: str, body: AskIn):
    iso = _iso(c)
    t0 = time.time()
    res = ask(S, body.question, S.snap.loc[iso, "country"], body.history[-6:])
    return J({"answer": res.answer, "trace": res.trace, "grounding": res.grounding, "mode": res.mode,
              "error": res.error, "seconds": time.time() - t0})


class BriefIn(BaseModel):
    answer: str = ""


@app.post("/api/brief/{c}")
def brief(c: str, body: BriefIn):
    iso = _iso(c)
    md = markdown_brief(S.snap.loc[iso, "country"], body.answer or "(no AI assessment generated)",
                        S.risk(iso), S.policies(iso), S.meta)
    return Response(pdf_brief(md), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="AsiaPulse_{iso}_policy_brief.pdf"'})


@app.get("/api/compare")
def compare(isos: str, indicator: str = "internet"):
    lst = [_iso(x) for x in isos.split(",") if x][:6]
    return J({"rows": S.compare(lst),
              "pillars": {i: {k: S.scores.loc[i, f"pillar_{k}"] for k in PKEYS} for i in lst},
              "indicator": {"key": indicator, "label": BY_KEY[indicator].label if indicator in BY_KEY else indicator,
                            "series": {i: _hist(i, indicator) for i in lst}},
              "names": {i: S.snap.loc[i, "country"] for i in lst}})


@app.get("/api/indicators")
def indicators():
    return J([{"key": i.key, "label": i.label, "area": PILLAR_LABELS.get(i.pillar, i.pillar.title()), "unit": i.unit}
              for i in INDICATORS if i.key in S.panel.columns and i.pillar != "context"])


@app.get("/api/methodology")
def methodology():
    m = S.meta
    reg = {i.key: {"label": i.label, "area": PILLAR_LABELS.get(i.pillar, i.pillar.title())} for i in INDICATORS}
    sources = [{**x, **reg.get(x["key"], {})} for x in m["indicators"]]
    return J({"backtest_overall": m["backtest_overall"], "calibration": m["interval_calibration"],
              "design": m["backtest_design"], "cluster": m["cluster"], "by_horizon": S.backtest_h.to_dict("records"),
              "pillars": [{"area": PILLAR_LABELS[p], "indicators": [{"key": f, "label": BY_KEY[f].label if f in BY_KEY else f,
                                                                     "dir": d} for f, d in feats]} for p, feats in PILLARS.items()],
              "flags": [{"text": f.text, "rule": f"{f.feature} {f.op} {f.threshold}", "basis": f.basis, "area": PILLAR_LABELS.get(f.pillar, f.pillar)}
                        for f in FLAGS],
              "sources": sources, "excluded": m["excluded"], "okun_pooled": m.get("okun_pooled_beta")})


# ---------------------------------------------------------------- static dashboard
WEB = ROOT / "web"
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})
