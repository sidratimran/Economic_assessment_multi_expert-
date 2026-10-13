"""Before/after accuracy comparison on identical held-out origins.

  OLD = 4 univariate members, weights from each economy's own record only
  NEW = + cross-country panel model, weights shrunk 50/50 towards the Asia-wide record

Usage: python pipeline/compare_models.py   (writes data/processed/model_comparison.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asiapulse.config import PROCESSED  # noqa: E402
from asiapulse.models import backtest as bt  # noqa: E402


def score(raw: pd.DataFrame, shrink: float) -> dict:
    bt.SHRINK = shrink
    w = bt.ensemble_weights(raw, "fit")
    cal = bt.calibration(raw)
    ho = bt.evaluate_heldout(raw, w, cal)
    out = {}
    for key in ("gdp_real", "gdp_pc_ppp"):
        g = ho[ho.series == key]
        hz = g.groupby("h").err.median()
        ga = bt.growth_accuracy(ho, key).set_index("h")
        out[key] = {
            "median_mape_all": round(float(g.err.median()), 2),
            "mean_mape_all": round(float(g.err.mean()), 2),
            "median_mape_by_h": {int(h): round(float(v), 2) for h, v in hz.items()},
            "naive_median_by_h": {int(h): round(float(v), 2) for h, v in g.groupby("h").err_naive.median().items()},
            "growth_mae_pp_by_h": {int(h): round(float(v), 2) for h, v in ga.growth_mae_pp.items()},
            "direction_hit": round(float(((g.actual > g.base) == (g.pred > g.base)).mean()) * 100, 1),
            "coverage80": round(float(g.covered80.mean()), 3),
            "n": int(len(g)),
        }
    return out


def main():
    panel = pd.read_csv(PROCESSED / "panel.csv").set_index(["iso3", "year"])
    print("Backtesting OLD model…")
    old_raw = bt.run_backtest(panel, use_panel=False)
    print("Backtesting NEW model…")
    new_raw = bt.run_backtest(panel, use_panel=True)
    res = {"old": score(old_raw, 0.0), "new": score(new_raw, 0.5)}
    (PROCESSED / "model_comparison.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    for key in ("gdp_real", "gdp_pc_ppp"):
        o, n = res["old"][key], res["new"][key]
        print(f"\n=== {key} (held-out origins {min(bt.HELDOUT_ORIGINS)}-{max(bt.HELDOUT_ORIGINS)}) ===")
        print(f"median MAPE all horizons: {o['median_mape_all']}% -> {n['median_mape_all']}%")
        print(f"mean MAPE all horizons:   {o['mean_mape_all']}% -> {n['mean_mape_all']}%")
        for h in (1, 3, 5, 10):
            if h in n["median_mape_by_h"]:
                print(f"  h={h:>2}: MAPE {o['median_mape_by_h'][h]:>5}% -> {n['median_mape_by_h'][h]:>5}%  "
                      f"(naive {n['naive_median_by_h'][h]}%) | growth error {o['growth_mae_pp_by_h'][h]} -> {n['growth_mae_pp_by_h'][h]} pp")
        print(f"direction hit: {o['direction_hit']}% -> {n['direction_hit']}%   coverage80: {o['coverage80']} -> {n['coverage80']}")


if __name__ == "__main__":
    main()
