"""Real-time layer: live market signals, a live growth nowcast and a live stress index.

Annual official statistics arrive with a lag of months. This module closes the gap with
market data that moves every day (Yahoo Finance public chart endpoint, no key):

* Global drivers  – Brent crude, VIX, US 10-year yield, US dollar index, gold
* Country signals – exchange rate vs US$ (where floating) and the main equity index

Nowcast (current year)
    consensus = mean(AsiaPulse ensemble, IMF WEO) for the current year's real growth
    + oil adjustment = the same oil elasticities as the Policy Lab, applied to the move in
      Brent's 30-day average versus its prior 12-month average, scaled by the share of the
      year still ahead.
Live stress index (0-100)
    average of the available market stress components (currency depreciation & volatility,
    equity drawdown, oil-price exposure, global risk appetite); blended 70/30 with the
    structural vulnerability index into a "live risk" reading.

Every value carries its timestamp; if the network is unavailable the last cached data is
used and flagged as stale.
"""
from __future__ import annotations

import concurrent.futures as cf
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from .config import DATA

LIVE = DATA / "live"
LIVE.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
TTL_SEC = 15 * 60

GLOBAL = {
    "brent": ("BZ=F", "Brent crude", "US$/bbl"),
    "vix": ("^VIX", "VIX (global risk)", "index"),
    "us10y": ("^TNX", "US 10-year yield", "%"),
    "dxy": ("DX-Y.NYB", "US dollar index", "index"),
    "gold": ("GC=F", "Gold", "US$/oz"),
}

CURRENCY = {
    "AFG": "AFN", "ARM": "AMD", "AZE": "AZN", "BHR": "BHD", "BGD": "BDT", "BTN": "BTN", "BRN": "BND",
    "KHM": "KHR", "CHN": "CNY", "CYP": "EUR", "GEO": "GEL", "IND": "INR", "IDN": "IDR", "IRN": "IRR",
    "IRQ": "IQD", "ISR": "ILS", "JPN": "JPY", "JOR": "JOD", "KAZ": "KZT", "KWT": "KWD", "KGZ": "KGS",
    "LAO": "LAK", "LBN": "LBP", "MYS": "MYR", "MDV": "MVR", "MNG": "MNT", "MMR": "MMK", "NPL": "NPR",
    "OMN": "OMR", "PAK": "PKR", "PSE": "ILS", "PHL": "PHP", "QAT": "QAR", "SAU": "SAR", "SGP": "SGD",
    "LKA": "LKR", "SYR": "SYP", "TJK": "TJS", "THA": "THB", "TLS": "USD", "TUR": "TRY", "TKM": "TMT",
    "ARE": "AED", "UZB": "UZS", "VNM": "VND", "YEM": "YER", "KOR": "KRW",
}
# Hard pegs / dollarised: FX moves are not a stress signal.
PEGGED = {"BHR", "JOR", "OMN", "QAT", "SAU", "ARE", "TLS", "BTN", "BRN", "NPL", "KWT", "TKM"}

EQUITY = {"JPN": "^N225", "KOR": "^KS11", "CHN": "000001.SS", "IND": "^BSESN", "IDN": "^JKSE",
          "MYS": "^KLSE", "SGP": "^STI", "TUR": "XU100.IS", "ISR": "TA35.TA"}


# ---------------------------------------------------------------- data access
def _cache(symbol: str):
    return LIVE / f"yf_{symbol.replace('^', '_').replace('=', '_').replace('.', '_')}.csv"


def chart(symbol: str, rng: str = "1y", ttl: int = TTL_SEC) -> tuple[pd.Series, dict]:
    """Daily closes for a symbol + metadata {price, as_of, stale, source}. Never raises."""
    path = _cache(symbol)
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        s = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
        return s, {"price": float(s.iloc[-1]), "as_of": s.index[-1], "stale": False, "source": "cache"}
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                         params={"range": rng, "interval": "1d"}, headers=UA, timeout=15)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        ts = res.get("timestamp") or []
        closes = res["indicators"]["quote"][0].get("close") or []
        s = pd.Series(closes, index=pd.to_datetime(ts, unit="s", utc=True).tz_convert(None), name=symbol).dropna()
        meta = res["meta"]
        price = meta.get("regularMarketPrice")
        t = meta.get("regularMarketTime")
        if price is not None and t:
            s.loc[pd.to_datetime(t, unit="s")] = float(price)
            s = s[~s.index.duplicated(keep="last")].sort_index()
        if s.empty:
            raise ValueError("empty series")
        s.to_frame().to_csv(path)
        return s, {"price": float(s.iloc[-1]), "as_of": s.index[-1], "stale": False, "source": "Yahoo Finance"}
    except Exception as ex:
        if path.exists():
            s = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
            return s, {"price": float(s.iloc[-1]), "as_of": s.index[-1], "stale": True, "source": f"cache ({type(ex).__name__})"}
        return pd.Series(dtype=float), {"price": None, "as_of": None, "stale": True, "source": f"unavailable ({type(ex).__name__})"}


def _pct(s: pd.Series, days: int) -> float:
    if len(s) < 2:
        return np.nan
    past = s[s.index <= s.index[-1] - pd.Timedelta(days=days)]
    return float((s.iloc[-1] / past.iloc[-1] - 1) * 100) if len(past) else np.nan


def global_snapshot() -> dict:
    out = {}
    with cf.ThreadPoolExecutor(5) as ex:
        res = dict(zip(GLOBAL, ex.map(lambda k: chart(GLOBAL[k][0]), GLOBAL)))
    for k, (s, m) in res.items():
        out[k] = {"label": GLOBAL[k][1], "unit": GLOBAL[k][2], "series": s, **m,
                  "chg_1m": _pct(s, 30), "chg_3m": _pct(s, 91), "chg_1y": _pct(s, 360)}
    return out


def country_signals(iso: str) -> dict:
    out = {"iso3": iso, "pegged": iso in PEGGED, "fx": None, "equity": None}
    cur = CURRENCY.get(iso)
    if cur and cur != "USD":
        s, m = chart(f"{cur}=X")
        if len(s) > 30:
            ret = np.log(s).diff().dropna()
            vol30 = float(ret.tail(21).std() * np.sqrt(252) * 100)
            vol_1y = ret.rolling(21).std().dropna() * np.sqrt(252) * 100
            z = float((vol30 - vol_1y.mean()) / vol_1y.std()) if len(vol_1y) > 30 and vol_1y.std() > 0 else np.nan
            out["fx"] = {"currency": cur, "series": s, **m, "depr_1m": _pct(s, 30), "depr_3m": _pct(s, 91),
                         "depr_1y": _pct(s, 360), "vol30": vol30, "vol_z": z}
        elif m["price"] is not None:
            out["fx"] = {"currency": cur, "series": s, **m, "depr_1m": np.nan, "depr_3m": np.nan, "depr_1y": np.nan,
                         "vol30": np.nan, "vol_z": np.nan}
    if iso in EQUITY:
        s, m = chart(EQUITY[iso])
        if len(s) > 30:
            out["equity"] = {"symbol": EQUITY[iso], "series": s, **m, "chg_1m": _pct(s, 30), "chg_3m": _pct(s, 91),
                             "drawdown": float((s.iloc[-1] / s.tail(252).max() - 1) * 100)}
    return out


# ---------------------------------------------------------------- live models
def _clip01(x):
    return float(np.clip(x, 0, 1)) if pd.notna(x) else np.nan


def oil_move(glob: dict) -> float:
    s = glob["brent"]["series"]
    if len(s) < 60:
        return np.nan
    recent = s[s.index > s.index[-1] - pd.Timedelta(days=30)].mean()
    prior = s[(s.index <= s.index[-1] - pd.Timedelta(days=30)) & (s.index > s.index[-1] - pd.Timedelta(days=395))].mean()
    return float((recent / prior - 1) * 100)


def stress(iso: str, sig: dict, glob: dict, snap_row: pd.Series) -> dict:
    """Live market stress components (0-100 each, higher = more stress)."""
    comp = {}
    fx = sig.get("fx")
    if fx and not sig["pegged"]:
        comp["Currency depreciation (3m)"] = 100 * _clip01(fx["depr_3m"] / 15)
        # Volatility only signals stress if it is material in absolute terms (managed pegs have tiny vol).
        comp["Currency volatility"] = 100 * _clip01(fx["vol_z"] / 3) if fx["vol30"] >= 4 else 0.0
    eq = sig.get("equity")
    if eq:
        comp["Equity drawdown"] = 100 * _clip01(-eq["drawdown"] / 30)
    om = oil_move(glob)
    rents = snap_row.get("oil_rents", np.nan)
    if pd.notna(om):
        exporter = pd.notna(rents) and rents >= 2
        exposure = (-om if exporter else om) * (min(rents, 40) / 20 if exporter else 1.0)
        comp["Oil-price exposure"] = 100 * _clip01(exposure / 40)
    vix = glob["vix"]["price"]
    if vix:
        comp["Global risk appetite (VIX)"] = 100 * _clip01((vix - 15) / 25)
    vals = [v for v in comp.values() if pd.notna(v)]
    return {"components": comp, "score": float(np.mean(vals)) if vals else np.nan}


def nowcast(store, iso: str, glob: dict, year: int | None = None) -> dict:
    """Real-time growth estimate for the current year."""
    year = year or datetime.now().year
    hist = store.history(iso, "gdp_real")
    f = store.fc(iso, "gdp_real").set_index("year").value
    lvl = pd.concat([hist, f])
    ours = float((lvl.loc[year] / lvl.loc[year - 1] - 1) * 100) if year in lvl.index and year - 1 in lvl.index else np.nan
    imf = np.nan
    p = PROCESSED_IMF()
    if p is not None and iso in p.index and str(year) in p.columns:
        imf = float(p.loc[iso, str(year)])
    base_parts = [v for v in (ours, imf) if pd.notna(v)]
    consensus = float(np.mean(base_parts)) if base_parts else np.nan

    row = store.snap.loc[iso]
    om = oil_move(glob)
    rents = row.get("oil_rents", np.nan)
    remaining = (12 - datetime.now().month + 1) / 12
    if pd.notna(om):
        coef = (rents / 100) * 0.15 if pd.notna(rents) and rents >= 2 else -0.015
        oil_adj = coef * om * remaining
    else:
        oil_adj = 0.0
    live = consensus + oil_adj if pd.notna(consensus) else np.nan
    return {"year": year, "asiapulse_model": ours, "imf_weo": imf, "consensus": consensus,
            "oil_move_pct": om, "oil_adjustment_pp": oil_adj, "nowcast": live,
            "computed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}


_IMF_CACHE: dict = {}


def PROCESSED_IMF():
    from .config import PROCESSED

    if "g" not in _IMF_CACHE:
        p = PROCESSED / "imf_gdp_growth.csv"
        _IMF_CACHE["g"] = pd.read_csv(p, index_col=0) if p.exists() else None
    return _IMF_CACHE["g"]


def live_assessment(store, iso: str, glob: dict) -> dict:
    sig = country_signals(iso)
    row = store.snap.loc[iso]
    st_ = stress(iso, sig, glob, row)
    nc = nowcast(store, iso, glob)
    structural = float(store.scores.loc[iso, "composite"])
    live_risk = 0.7 * structural + 0.3 * st_["score"] if pd.notna(st_["score"]) else structural
    alerts = [f"{k}: {v:.0f}/100" for k, v in st_["components"].items() if pd.notna(v) and v >= 60]
    fx = sig.get("fx")
    if fx and pd.notna(fx.get("depr_3m")) and not sig["pegged"]:
        nc["inflation_passthrough_pp"] = 0.2 * fx["depr_3m"]   # typical EM exchange-rate pass-through ≈ 0.2
    log_nowcast(iso, nc, live_risk)
    return {"signals": sig, "stress": st_, "nowcast": nc, "structural": structural, "live_risk": live_risk,
            "alerts": alerts}


def log_nowcast(iso: str, nc: dict, live_risk: float) -> None:
    """Append to a local log so the app can show how the nowcast evolves over time."""
    path = LIVE / "nowcast_log.csv"
    row = pd.DataFrame([{"ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "iso3": iso,
                         "nowcast": nc["nowcast"], "oil_move_pct": nc["oil_move_pct"], "live_risk": live_risk}])
    try:
        if path.exists():
            last = pd.read_csv(path).query("iso3 == @iso").tail(1)
            if len(last) and last.ts.iloc[0][:15] == row.ts.iloc[0][:15]:  # at most one entry per 10 minutes
                return
        row.to_csv(path, mode="a", header=not path.exists(), index=False)
    except Exception:
        pass


def nowcast_history(iso: str) -> pd.DataFrame:
    path = LIVE / "nowcast_log.csv"
    if not path.exists():
        return pd.DataFrame()
    d = pd.read_csv(path)
    return d[d.iso3 == iso]


def regional_fx(isos: list[str]) -> pd.DataFrame:
    """3-month currency moves for all floating currencies (parallel, cached)."""
    def one(iso):
        if iso in PEGGED or CURRENCY.get(iso) in (None, "USD"):
            return None
        s, m = chart(f"{CURRENCY[iso]}=X")
        if len(s) < 60:
            return None
        return {"iso3": iso, "currency": CURRENCY[iso], "depr_3m": _pct(s, 91), "depr_1m": _pct(s, 30),
                "as_of": m["as_of"], "stale": m["stale"]}
    with cf.ThreadPoolExecutor(12) as ex:
        rows = [r for r in ex.map(one, isos) if r]
    return pd.DataFrame(rows)
