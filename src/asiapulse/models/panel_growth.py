"""Cross-country ("panel") growth model — the ensemble's fifth member.

Single-country trend models only see one economy's past. This model learns from all
Asian economies at once how growth evolves *conditional on where an economy stands*:
income level (convergence), recent momentum, volatility, inflation, demography,
structure and institutions. One gradient-boosted model is trained per horizon h
(direct multi-step forecasting) to predict the average annual log growth over the next
h years.

Strictly no look-ahead: for a forecast made at origin T, training pairs are restricted to
(t, t+h) with t + h <= T, and features only use data up to t.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

FEATURES = ["g1", "g3", "g5", "g10", "vol10", "lpc", "pop_g", "infl", "dep", "agri", "manuf", "gov_eff", "trade"]


def build_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Features at (iso3, year) using only information available in that year."""
    out = []
    for iso, g in panel.groupby(level="iso3"):
        g = g.droplevel("iso3").sort_index()
        gr = g.get("gdp_growth", pd.Series(dtype=float))
        f = pd.DataFrame(index=g.index)
        f["g1"] = gr
        f["g3"] = gr.rolling(3, min_periods=2).mean()
        f["g5"] = gr.rolling(5, min_periods=3).median()
        f["g10"] = gr.rolling(10, min_periods=5).median()
        f["vol10"] = gr.rolling(10, min_periods=5).std()
        pc = g.get("gdp_pc_ppp", pd.Series(dtype=float))
        f["lpc"] = np.log(pc.where(pc > 0))
        f["pop_g"] = g.get("pop_growth")
        f["infl"] = g.get("inflation", pd.Series(dtype=float)).clip(-10, 60)
        f["dep"] = g.get("dependency")
        f["agri"] = g.get("agri_emp")
        f["manuf"] = g.get("manufacturing")
        f["gov_eff"] = g.get("gov_effectiveness")
        f["trade"] = g.get("trade_open")
        f["iso3"] = iso
        out.append(f.reset_index().rename(columns={"index": "year"}))
    feats = pd.concat(out, ignore_index=True)
    if "year" not in feats.columns:
        feats = feats.rename(columns={feats.columns[0]: "year"})
    return feats.set_index(["iso3", "year"]).reindex(columns=FEATURES).astype(float)


def _targets(panel: pd.DataFrame, key: str, h: int) -> pd.Series:
    """Average annual log growth (x100) of `key` from t to t+h."""
    lv = np.log(panel[key].where(panel[key] > 0))
    fut = lv.groupby(level="iso3").shift(-h)
    return (fut - lv) / h * 100


def _model():
    return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=250, min_samples_leaf=15,
                                         l2_regularization=1.0, random_state=0)


def predict_paths(panel: pd.DataFrame, key: str, origin: int, H: int, feats: pd.DataFrame | None = None,
                  isos=None) -> dict[str, np.ndarray]:
    """Log-level paths for years origin+1 … origin+H for every economy observed at `origin`.

    Returns {iso3: array of length H} in log units (same space as the univariate members).
    """
    feats = build_features(panel) if feats is None else feats
    lv_all = np.log(panel[key].where(panel[key] > 0))
    years = feats.index.get_level_values("year")
    at_origin = feats[years == origin]
    if isos is not None:
        at_origin = at_origin[at_origin.index.get_level_values("iso3").isin(isos)]
    if at_origin.empty:
        return {}
    preds = {}
    for h in range(1, H + 1):
        y = _targets(panel, key, h)
        y = y.reindex(feats.index)
        mask = (years + h <= origin) & y.notna() & feats.g1.notna()
        if mask.sum() < 60:  # not enough history at this horizon: reuse the longest available horizon
            if h > 1:
                for iso in preds:
                    preds[iso].append(preds[iso][-1])
                continue
            return {}
        Xtr = feats[mask]
        cols = [c for c in FEATURES if Xtr[c].notna().sum() >= 20 and Xtr[c].nunique() > 3]  # drop empty/degenerate features
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = _model().fit(Xtr[cols].values, y[mask].values)
            gh = m.predict(at_origin[cols].values)
        for (iso, _), g_ in zip(at_origin.index, gh):
            preds.setdefault(iso, []).append(float(g_))
    out = {}
    for iso, gs in preds.items():
        try:
            base = float(lv_all.loc[(iso, origin)])
        except KeyError:
            continue
        if not np.isfinite(base):
            continue
        out[iso] = np.array([base + (h + 1) * gs[h] / 100 for h in range(len(gs))])
    return out
