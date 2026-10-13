"""End-to-end pipeline: fetch → panel → backtest → forecast → cluster → risk → artefacts.

Usage:
    python pipeline/run_pipeline.py            # use cached raw data where present
    python pipeline/run_pipeline.py --refresh  # re-download everything from the World Bank API
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asiapulse.config import FORECAST_END, PROCESSED  # noqa: E402
from asiapulse.countries import ALL_ISO, ISO_TO_NAME, NO_WDI_COVERAGE, WDI_ISO  # noqa: E402
from asiapulse.indicators import WB_INDICATORS  # noqa: E402
from asiapulse.models import backtest as bt  # noqa: E402
from asiapulse.models.cluster import fit_clusters  # noqa: E402
from asiapulse.models.forecast import SERIES, cagr, forecast_series, pooled_sigma  # noqa: E402
from asiapulse.models.panel_growth import build_features, predict_paths  # noqa: E402
from asiapulse.models.risk import score_all  # noqa: E402
from asiapulse.models.scenario import estimate_okun  # noqa: E402
from asiapulse.panel import build_panel, derived_features, latest_snapshot  # noqa: E402
from asiapulse.sources import imf_weo  # noqa: E402
from asiapulse.sources.worldbank import fetch_all  # noqa: E402


def main(refresh: bool = False) -> None:
    t0 = time.time()
    end_year = datetime.now().year
    print(f"[1/7] Fetching {len(WB_INDICATORS)} World Bank indicators for {len(WDI_ISO)} economies + IMF WEO")
    long, manifest = fetch_all(WB_INDICATORS, WDI_ISO, end_year, refresh=refresh)
    ref_year = int(long.year.max())
    try:
        imf = imf_weo.fetch(WDI_ISO, refresh=refresh)
        manifest.append({"key": "imf_weo", "code": ",".join(imf_weo.SUBJECTS), "source": "IMF WEO (via DBnomics)",
                         "rows": int(len(imf)), "countries": int(imf.iso3.nunique()), "status": "ok"})
    except Exception as ex:
        print(f"  ✗ IMF WEO unavailable: {ex}")
        imf = pd.DataFrame(columns=["iso3", "year", "key", "value"])
        manifest.append({"key": "imf_weo", "code": "IMF WEO", "status": f"failed: {ex}"})

    print("[2/7] Building panel")
    hist = imf[imf.year <= ref_year]
    imf_debt = hist[hist.key == "gov_debt_imf"].assign(key="gov_debt")      # IMF gross debt preferred
    imf_fiscal = hist[hist.key.isin(["primary_balance", "fiscal_balance"])]
    combined = (pd.concat([imf_debt, imf_fiscal, long], ignore_index=True)
                  .drop_duplicates(["iso3", "year", "key"], keep="first"))
    panel = build_panel(combined)
    panel.to_csv(PROCESSED / "panel.csv")
    imf_growth = imf[imf.key == "imf_gdp_growth"].pivot_table(index="iso3", columns="year", values="value")
    imf_growth.to_csv(PROCESSED / "imf_gdp_growth.csv")
    imf_infl = imf[imf.key == "imf_inflation"].pivot_table(index="iso3", columns="year", values="value")

    print("[3/7] Rolling-origin backtests")
    bt_rows = bt.run_backtest(panel)
    fit_w = bt.ensemble_weights(bt_rows, split="fit")
    calib = bt.calibration(bt_rows)
    heldout = bt.evaluate_heldout(bt_rows, fit_w, calib)
    heldout.to_csv(PROCESSED / "backtest_heldout.csv", index=False)
    bt_sum = bt.summarize(heldout)
    bt_sum.to_csv(PROCESSED / "backtest_summary.csv", index=False)
    bt.by_horizon(heldout).to_csv(PROCESSED / "backtest_by_horizon.csv", index=False)
    growth_acc = bt.growth_accuracy(heldout).round(3)
    growth_acc.to_csv(PROCESSED / "backtest_growth_accuracy.csv", index=False)
    weights = bt.ensemble_weights(bt_rows, split=None)  # production weights use all origins
    print(f"  interval calibration: {calib}")

    print("[4/7] Forecasting to", FORECAST_END, "(5-member ensemble incl. cross-country panel model)")
    feats = build_features(panel)
    panel_paths = {}  # (iso, key) -> log-level path from each economy's last observed year
    for key in bt.PANEL_SERIES:
        last = panel[key].dropna().reset_index().groupby("iso3").year.max()
        for T, isos in last.groupby(last):
            for iso, path in predict_paths(panel, key, int(T), FORECAST_END - int(T), feats, isos=list(isos.index)).items():
                panel_paths[(iso, key)] = path
    fc_rows = []
    for key in SERIES:
        pool = pooled_sigma(panel, key)
        for iso, g in panel[key].groupby(level="iso3"):
            extra = {"panel": panel_paths[(iso, key)]} if (iso, key) in panel_paths else None
            fc = forecast_series(g.droplevel("iso3"), key, FORECAST_END, weights.get((iso, key)),
                                 calib=calib[key]["factor"], sigma_pool=pool, extra=extra)
            if fc is None:
                continue
            fc.insert(0, "series", key)
            fc.insert(0, "iso3", iso)
            fc_rows.append(fc)
    forecasts = pd.concat(fc_rows, ignore_index=True)
    params = {"series": {k: {"calib": calib[k]["factor"], "sigma_pool": pooled_sigma(panel, k)} for k in SERIES},
              "weights": {f"{i}|{k}": w for (i, k), w in weights.items()},
              "panel_paths": {f"{i}|{k}": [float(x) for x in p] for (i, k), p in panel_paths.items()}}
    (PROCESSED / "model_params.json").write_text(json.dumps(params), encoding="utf-8")
    forecasts.to_csv(PROCESSED / "forecasts.csv", index=False)

    print("[5/7] Snapshot & derived features")
    snap, years = latest_snapshot(panel, ref_year)
    snap = derived_features(panel, snap)
    for iso in snap.index:
        s = panel.loc[iso, "gdp_real"].dropna() if iso in panel.index.get_level_values(0) else pd.Series(dtype=float)
        f = forecasts[(forecasts.iso3 == iso) & (forecasts.series == "gdp_real")]
        if len(s) and len(f):
            snap.loc[iso, "gdp_cagr_fc"] = cagr(float(s.iloc[-1]), float(f.value.iloc[-1]), int(f.year.iloc[-1] - s.index.max()))
            # External benchmark: our average growth 2026-30 vs the IMF WEO projection.
            lvl = pd.concat([s, f.set_index("year").value])
            g = (lvl.pct_change() * 100).loc[2026:2030]
            snap.loc[iso, "fc_growth_2026_30"] = g.mean() if len(g) else float("nan")
            if iso in imf_growth.index:
                ig = imf_growth.loc[iso, [y for y in range(2026, 2031) if y in imf_growth.columns]].dropna()
                snap.loc[iso, "imf_growth_2026_30"] = ig.mean() if len(ig) else float("nan")
            if iso in imf_infl.index:
                ii = imf_infl.loc[iso, [y for y in range(2026, 2031) if y in imf_infl.columns]].dropna()
                snap.loc[iso, "imf_inflation_2026_30"] = ii.mean() if len(ii) else float("nan")
    # Implied effective interest rate on public debt = interest bill / previous-year debt,
    # where interest bill (% GDP) = primary balance − overall balance (IMF WEO identities).
    for iso in snap.index:
        try:
            g = panel.loc[iso][["primary_balance", "fiscal_balance", "gov_debt"]].dropna()
        except KeyError:
            continue
        if len(g) >= 2:
            rate = ((g.primary_balance - g.fiscal_balance) / g.gov_debt.shift(1) * 100).dropna().tail(3)
            if len(rate):
                snap.loc[iso, "implied_interest_rate"] = float(min(max(rate.mean(), 0.0), 25.0))
    snap.to_csv(PROCESSED / "snapshot.csv")
    years.to_csv(PROCESSED / "snapshot_years.csv")

    print("[6/7] Clustering & risk")
    clusters, Z, cmeta = fit_clusters(snap)
    clusters.to_csv(PROCESSED / "clusters.csv")
    Z.to_csv(PROCESSED / "cluster_features_z.csv")
    scores, flags = score_all(snap)
    scores.to_csv(PROCESSED / "risk_scores.csv")
    flags.to_csv(PROCESSED / "risk_flags.csv", index=False)
    okun = estimate_okun(panel)
    okun.to_csv(PROCESSED / "okun.csv")
    print(f"  k={cmeta['k']} silhouette={cmeta['silhouette']}  clusters={cmeta['names']}")
    print(f"  risk labels: {scores.label.value_counts().to_dict()}")

    print("[7/7] Metadata")
    overall = (bt_sum.groupby("series")
               .agg(median_error=("error", "median"), median_skill=("skill_vs_naive", "median"),
                    share_beating_naive=("skill_vs_naive", lambda s: float((s > 0).mean())),
                    coverage80=("coverage80", "mean"))
               .round(3).reset_index().to_dict("records"))
    meta = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "reference_year": ref_year, "forecast_end": FORECAST_END,
        "economies_total": len(ALL_ISO), "economies_covered": int(snap.shape[0]),
        "excluded": {ISO_TO_NAME[k]: v for k, v in NO_WDI_COVERAGE.items()},
        "indicators": manifest, "cluster": cmeta, "backtest_overall": overall, "interval_calibration": calib,
        "growth_accuracy": growth_acc.to_dict("records"),
        "gdp_accuracy_by_h": {int(h): round(float(v), 2) for h, v in heldout[heldout.series == "gdp_real"].groupby("h").err.median().items()},
        "backtest_design": {"fit_origins": f"{min(bt.FIT_ORIGINS)}-{max(bt.FIT_ORIGINS)}",
                            "heldout_origins": f"{min(bt.HELDOUT_ORIGINS)}-{max(bt.HELDOUT_ORIGINS)}",
                            "max_horizon": bt.MAX_H},
        "okun_pooled_beta": round(okun.attrs["pooled"], 3),
        "runtime_sec": round(time.time() - t0, 1),
    }
    (PROCESSED / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Done in {meta['runtime_sec']}s → {PROCESSED}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download raw data")
    main(ap.parse_args().refresh)
