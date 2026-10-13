"""Forecast Expert: a small, transparent ensemble for annual macro series.

Members
-------
* ``naive``  – no change from the last observation (the benchmark to beat)
* ``drift``  – random walk with the median change of the last 10 years (robust to one-off shocks)
* ``holt``   – damped-trend exponential smoothing (statsmodels)
* ``trend``  – OLS linear trend on the last 10 years

GDP-type series are modelled in logs.  Bounded ratios (employment, unemployment) are
clipped to [0, 100].  Ensemble weights are inverse squared backtest MAE (learned per country &
series in :mod:`asiapulse.models.backtest`); without weights, members are averaged equally.
Prediction intervals use a robust (MAD) volatility partially pooled with the panel median,
widen with sqrt(horizon), and are
rescaled by a per-series factor calibrated on early backtest origins (split-conformal);
coverage is then checked on later, held-out origins.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

MEMBERS = ("naive", "drift", "holt", "trend", "ets")
EXTRA_MEMBERS = ("panel",)            # cross-country model, supplied from models.panel_growth
ALL_MEMBERS = MEMBERS + EXTRA_MEMBERS

SERIES = {
    # key: (log-transform?, lower bound, upper bound, label)
    "gdp_real": (True, None, None, "Real GDP (constant 2015 US$)"),
    "gdp_pc_ppp": (True, None, None, "GDP per capita, PPP"),
    "emp_ratio": (False, 0.0, 100.0, "Employment-to-population ratio, 15+"),
    "unemp": (False, 0.0, 100.0, "Unemployment rate"),
}

Z80 = 1.2816


def _member_paths(y: np.ndarray, h: int) -> dict[str, np.ndarray]:
    n = len(y)
    steps = np.arange(1, h + 1)
    d = np.diff(y)
    drift = np.median(d[-10:]) if len(d) else 0.0
    paths = {"naive": np.full(h, y[-1]), "drift": y[-1] + drift * steps}

    tail = y[-10:]
    x = np.arange(len(tail))
    slope, intercept = np.polyfit(x, tail, 1) if len(tail) >= 3 else (0.0, y[-1])
    paths["trend"] = intercept + slope * (len(tail) - 1 + steps)

    holt = None
    ets = None
    if n >= 8:
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fit = ExponentialSmoothing(y, trend="add", damped_trend=True,
                                           initialization_method="estimated").fit(optimized=True)
                holt = np.asarray(fit.forecast(h))
        except Exception:
            holt = None
        try:
            from statsmodels.tsa.exponential_smoothing.ets import ETSModel

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ets_fit = ETSModel(y, error="add", trend="add", damped_trend=True).fit(disp=False)
                ets = np.asarray(ets_fit.forecast(h))
        except Exception:
            ets = None
    paths["holt"] = holt if holt is not None and np.all(np.isfinite(holt)) else paths["drift"]
    paths["ets"] = ets if ets is not None and np.all(np.isfinite(ets)) else paths["holt"]
    return paths


def robust_sigma(y: np.ndarray) -> float:
    """MAD-based volatility of annual changes (last 15 years), floored at 1/4 of the plain std."""
    d15 = np.diff(y)[-15:]
    if len(d15) <= 3:
        return 0.0
    s = 1.4826 * np.median(np.abs(d15 - np.median(d15)))
    return float(max(s, 0.25 * np.std(d15, ddof=1)))


def pooled_sigma(panel: pd.DataFrame, key: str) -> float:
    """Median robust volatility across the panel (in model units) for partial pooling."""
    log = SERIES[key][0]
    vals = []
    for _, g in panel[key].groupby(level="iso3"):
        s = g.dropna().values
        if len(s) > 6:
            vals.append(robust_sigma(np.log(s) if log else s))
    return float(np.median(vals)) if vals else 0.0


def _band_for_h(h_idx: int) -> str:
    if h_idx < 3:
        return "short"
    if h_idx < 6:
        return "medium"
    return "long"


def forecast_series(s: pd.Series, key: str, end_year: int, weights: dict[str, float] | None = None,
                    calib: float = 1.0, sigma_pool: float | None = None,
                    extra: dict[str, np.ndarray] | None = None,
                    band_weights: dict[str, dict[str, float]] | None = None) -> pd.DataFrame | None:
    """Forecast one country-series. ``s`` is indexed by year. Returns year/value/lo/hi/member columns."""
    log, lo_b, hi_b, _ = SERIES[key]
    s = s.dropna().sort_index()
    if len(s) < 6:
        return None
    last_year = int(s.index.max())
    h = end_year - last_year
    if h <= 0:
        return None
    y = np.log(s.values) if log else s.values.astype(float)
    paths = _member_paths(y, h)
    for name, arr in (extra or {}).items():
        arr = np.asarray(arr, dtype=float)
        if len(arr) >= 1 and np.all(np.isfinite(arr)):
            if len(arr) < h:
                step = arr[-1] - (arr[-2] if len(arr) > 1 else y[-1])
                arr = np.concatenate([arr, arr[-1] + step * np.arange(1, h - len(arr) + 1)])
            paths[name] = arr[:h]
    used = [m for m in ALL_MEMBERS if m in paths]
    if band_weights:
        ens = np.zeros(h)
        for i in range(h):
            band = _band_for_h(i)
            bw = band_weights.get(band, weights or {})
            w = {m: max(bw.get(m, 0.0) or 0.0, 0.0) for m in used}
            tot = sum(w.values())
            if tot <= 0:
                w, tot = {m: 1.0 for m in used}, float(len(used))
            ens[i] = sum(paths[m][i] * w[m] for m in used) / tot
    else:
        w = {m: 1.0 for m in used} if not weights else {m: max(weights.get(m, 0.0) or 0.0, 0.0) for m in used}
        tot = sum(w.values())
        if tot <= 0:
            w, tot = {m: 1.0 for m in used}, float(len(used))
        ens = sum(paths[m] * w[m] for m in used) / tot

    sigma = robust_sigma(y)
    if sigma_pool:  # partial pooling: geometric mean of own and panel volatility
        sigma = float(np.sqrt(max(sigma, 1e-9) * sigma_pool))
    sigma = max(sigma, 0.005 if log else 0.1)  # never claim zero uncertainty (0.5% for levels, 0.1 pp for ratios)
    half = calib * Z80 * sigma * np.sqrt(np.arange(1, h + 1))
    lo, hi = ens - half, ens + half

    def back(a):
        a = np.exp(a) if log else a
        if lo_b is not None or hi_b is not None:
            a = np.clip(a, lo_b, hi_b)
        return a

    out = pd.DataFrame({"year": np.arange(last_year + 1, end_year + 1),
                        "value": back(ens), "lo": back(lo), "hi": back(hi)})
    for m in ALL_MEMBERS:
        out[m] = back(paths[m]) if m in paths else np.nan
    return out


def cagr(start: float, end: float, years: int) -> float:
    if start is None or end is None or start <= 0 or end <= 0 or years <= 0:
        return np.nan
    return ((end / start) ** (1 / years) - 1) * 100
