"""Validation Expert: rolling-origin backtests with an honest train / held-out split.

For every origin year T the models see data up to T only and forecast T+1 … T+10.

* **Fit origins** (2008-2013) are used to *learn* the ensemble weights and the interval
  calibration factor per series.
* **Held-out origins** (2014-2020, incl. the 2020 COVID shock) are used only to *evaluate*:
  error, skill versus a naive no-change forecast, and 80%-interval coverage. Origins 2014-15
  are scored all the way to a 10-year horizon (2024-25), matching the product's 10-year claim.

Ensemble weights are inverse squared error per member, blended 50/50 between the economy's
own record and the Asia-wide record (shrinkage: one country's short history is noisy).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .forecast import ALL_MEMBERS, SERIES, forecast_series, pooled_sigma
from .panel_growth import build_features, predict_paths

FIT_ORIGINS = range(2008, 2014)
HELDOUT_ORIGINS = range(2014, 2021)
MAX_H = 10
PANEL_SERIES = ("gdp_real", "gdp_pc_ppp")
SHRINK = 0.5


def _err(key: str, actual, pred):
    if SERIES[key][0]:  # percentage error for level series
        return np.abs(pred - actual) / np.abs(actual) * 100
    return np.abs(pred - actual)  # percentage points for ratios


def _t(key: str, x):
    return np.log(x) if SERIES[key][0] else x


def run_backtest(panel: pd.DataFrame, use_panel: bool = True, log=print) -> pd.DataFrame:
    rows = []
    feats = build_features(panel) if use_panel else None
    origins = list(FIT_ORIGINS) + list(HELDOUT_ORIGINS)
    for key in SERIES:
        if key not in panel.columns:
            continue
        pool = pooled_sigma(panel, key)
        ppaths = {T: predict_paths(panel, key, T, MAX_H, feats) for T in origins} if use_panel and key in PANEL_SERIES else {}
        for iso, g in panel[key].groupby(level="iso3"):
            s = g.droplevel("iso3").dropna()
            for T in origins:
                train = s[s.index <= T]
                test = s[(s.index > T) & (s.index <= T + MAX_H)]
                if len(train) < 8 or test.empty:
                    continue
                extra = None
                if ppaths and int(train.index.max()) == T and iso in ppaths.get(T, {}):
                    extra = {"panel": ppaths[T][iso]}
                fc = forecast_series(train, key, T + MAX_H, sigma_pool=pool, extra=extra)
                if fc is None:
                    continue
                fc = fc.set_index("year")
                for yr, actual in test.items():
                    if yr not in fc.index:
                        continue
                    f = fc.loc[yr]
                    half = (_t(key, f.hi) - _t(key, f.lo)) / 2
                    row = {"iso3": iso, "series": key, "origin": T, "h": int(yr - T), "year": int(yr),
                           "split": "fit" if T in FIT_ORIGINS else "heldout", "actual": actual, "base": float(train.iloc[-1]),
                           "pred_equal": f.value,
                           "z": abs(_t(key, actual) - _t(key, f.value)) / half if half > 0 else np.nan}
                    for m in ALL_MEMBERS:
                        row[f"pred_{m}"] = f[m]
                    rows.append(row)
        log(f"  OK backtested {key}{' (+ panel model)' if ppaths else ''}")
    bt = pd.DataFrame(rows)
    for m in ALL_MEMBERS:
        bt[f"err_{m}"] = [_err(k, a, p) for k, a, p in zip(bt.series, bt.actual, bt[f"pred_{m}"])]
    return bt


def _inv(errs: dict) -> dict:
    w = {m: 1 / max(e, 1e-6) ** 2 for m, e in errs.items() if pd.notna(e)}
    tot = sum(w.values()) or 1.0
    return {m: v / tot for m, v in w.items()}


HORIZON_BANDS = {"short": range(1, 4), "medium": range(4, 7), "long": range(7, 11)}


def ensemble_weights(bt: pd.DataFrame, split: str | None = "fit") -> dict[tuple[str, str], dict[str, float]]:
    """Member weights per (iso3, series): 50% own record + 50% Asia-wide record (inverse squared MAE)."""
    src = bt if split is None else bt[bt.split == split]
    glob = {k: _inv({m: g[f"err_{m}"].mean() for m in ALL_MEMBERS}) for k, g in src.groupby("series")}
    out = {}
    for (iso, key), g in src.groupby(["iso3", "series"]):
        own = _inv({m: g[f"err_{m}"].mean() for m in ALL_MEMBERS})
        members = set(own) | set(glob.get(key, {}))
        out[(iso, key)] = {m: (1 - SHRINK) * own.get(m, glob[key].get(m, 0.0)) + SHRINK * glob[key].get(m, 0.0) for m in members}
    return out


def ensemble_weights_by_band(bt: pd.DataFrame, split: str | None = "fit") -> dict[str, dict[tuple[str, str], dict[str, float]]]:
    """Horizon-band weights: separate weights for short (1-3y), medium (4-6y), long (7-10y)."""
    src = bt if split is None else bt[bt.split == split]
    band_weights = {}
    for band_name, hrs in HORIZON_BANDS.items():
        band_src = src[src.h.isin(hrs)]
        if band_src.empty:
            continue
        glob = {k: _inv({m: g[f"err_{m}"].mean() for m in ALL_MEMBERS}) for k, g in band_src.groupby("series")}
        w = {}
        for (iso, key), g in band_src.groupby(["iso3", "series"]):
            own = _inv({m: g[f"err_{m}"].mean() for m in ALL_MEMBERS})
            members = set(own) | set(glob.get(key, {}))
            w[(iso, key)] = {m: (1 - SHRINK) * own.get(m, glob[key].get(m, 0.0)) + SHRINK * glob[key].get(m, 0.0) for m in members}
        band_weights[band_name] = w
    return band_weights


def global_weights(bt: pd.DataFrame, split: str | None = None) -> dict[str, dict[str, float]]:
    src = bt if split is None else bt[bt.split == split]
    return {k: _inv({m: g[f"err_{m}"].mean() for m in ALL_MEMBERS}) for k, g in src.groupby("series")}


def calibration(bt: pd.DataFrame) -> dict[str, dict]:
    """Interval scale factor per series (80th pct of |error|/half-width on fit origins)."""
    out = {}
    for key, g in bt.groupby("series"):
        fit, ho = g[g.split == "fit"].z.dropna(), g[g.split == "heldout"].z.dropna()
        factor = float(np.quantile(fit, 0.8)) if len(fit) else 1.0
        out[key] = {"factor": round(factor, 3),
                    "coverage_raw_heldout": round(float((ho <= 1).mean()), 3),
                    "coverage_calibrated_heldout": round(float((ho <= factor).mean()), 3)}
    return out


def evaluate_heldout(bt: pd.DataFrame, weights, calib: dict, band_weights=None) -> pd.DataFrame:
    """Score the *weighted* ensemble on held-out origins. Adds pred, err, covered80."""
    ho = bt[bt.split == "heldout"].copy()
    gw = global_weights(bt, "fit")
    preds = []
    for r in ho.itertuples():
        if band_weights:
            band = "short" if r.h <= 3 else ("medium" if r.h <= 6 else "long")
            bw = band_weights.get(band, {})
            w = bw.get((r.iso3, r.series)) or weights.get((r.iso3, r.series)) or gw.get(r.series) or {m: 1.0 for m in ALL_MEMBERS}
        else:
            w = weights.get((r.iso3, r.series)) or gw.get(r.series) or {m: 1.0 for m in ALL_MEMBERS}
        num = den = 0.0
        for m in ALL_MEMBERS:
            p = getattr(r, f"pred_{m}")
            if pd.notna(p) and w.get(m, 0) > 0:
                num += p * w[m]
                den += w[m]
        preds.append(num / den if den else r.pred_equal)
    ho["pred"] = preds
    ho["err"] = [_err(k, a, p) for k, a, p in zip(ho.series, ho.actual, ho.pred)]
    # err_naive already exists: it is the "naive" ensemble member's error column.
    ho["covered80"] = ho.z <= ho.series.map(lambda k: calib[k]["factor"])
    return ho


def summarize(ho: pd.DataFrame) -> pd.DataFrame:
    """One row per (iso3, series): held-out error (horizons 1-5), skill vs naive, coverage, confidence."""
    h5 = ho[ho.h <= 5]
    s = (h5.groupby(["iso3", "series"])
           .agg(error=("err", "mean"), error_naive=("err_naive", "mean"),
                coverage80=("covered80", "mean"), n=("err", "size"))
           .reset_index())
    s["skill_vs_naive"] = 1 - s.error / s.error_naive.replace(0, np.nan)
    s["unit"] = s.series.map(lambda k: "MAPE %" if SERIES[k][0] else "MAE pp")
    s["confidence"] = [confidence(r.series, r.error) for r in s.itertuples()]
    return s


def confidence(series: str, error: float) -> str:
    """Translate backtest error into a plain-language reliability label (single source of truth)."""
    if error is None or pd.isna(error):
        return "Unavailable"
    cuts = (5, 10, 20, 30) if SERIES[series][0] else (0.75, 1.5, 3, 5)
    for c, lab in zip(cuts, ("Very High", "High", "Moderate", "Low")):
        if error < c:
            return lab
    return "Very Low"


def by_horizon(ho: pd.DataFrame) -> pd.DataFrame:
    return (ho.groupby(["series", "h"])
              .agg(error=("err", "median"), error_naive=("err_naive", "median"), coverage80=("covered80", "mean"),
                   n=("err", "size"))
              .reset_index())


def growth_accuracy(ho: pd.DataFrame, key: str = "gdp_real") -> pd.DataFrame:
    """Error in the *average annual growth rate* (pp) and direction hit-rate, by horizon."""
    g = ho[ho.series == key].copy()
    g["g_act"] = ((g.actual / g.base) ** (1 / g.h) - 1) * 100
    g["g_fc"] = ((g.pred / g.base) ** (1 / g.h) - 1) * 100
    g["abs_pp"] = (g.g_act - g.g_fc).abs()
    g["hit"] = (g.g_act > 0) == (g.g_fc > 0)
    return g.groupby("h").agg(growth_mae_pp=("abs_pp", "mean"), growth_median_pp=("abs_pp", "median"),
                              direction_hit=("hit", "mean"), n=("abs_pp", "size")).reset_index()
