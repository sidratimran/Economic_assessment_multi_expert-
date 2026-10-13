"""Read-only access to pipeline artefacts. Shared by the UI and the AI agent tools."""
from __future__ import annotations

import json
from functools import cached_property

import numpy as np
import pandas as pd

from .config import PROCESSED
from .countries import ISO_TO_NAME, NAME_TO_ISO
from .indicators import BY_KEY, PILLAR_LABELS
from .models import scenario as sc
from .models.cluster import nearest_peers
from .models.forecast import SERIES
from .models.risk import evaluate_flags, score_row
from .policy.engine import recommend


def _clean(v):
    if isinstance(v, (np.floating, float)):
        return None if pd.isna(v) else round(float(v), 2)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


class Store:
    def __init__(self, root=PROCESSED):
        self.root = root

    # ---------- raw artefacts
    def _csv(self, name, **kw):
        return pd.read_csv(self.root / name, **kw)

    @cached_property
    def meta(self) -> dict:
        return json.loads((self.root / "metadata.json").read_text(encoding="utf-8"))

    @cached_property
    def panel(self) -> pd.DataFrame:
        return self._csv("panel.csv").set_index(["iso3", "year"])

    @cached_property
    def snap(self) -> pd.DataFrame:
        return self._csv("snapshot.csv", index_col=0)

    @cached_property
    def snap_years(self) -> pd.DataFrame:
        return self._csv("snapshot_years.csv", index_col=0)

    @cached_property
    def forecasts(self) -> pd.DataFrame:
        return self._csv("forecasts.csv")

    @cached_property
    def backtest(self) -> pd.DataFrame:
        return self._csv("backtest_summary.csv")

    @cached_property
    def backtest_h(self) -> pd.DataFrame:
        return self._csv("backtest_by_horizon.csv")

    @cached_property
    def clusters(self) -> pd.DataFrame:
        return self._csv("clusters.csv", index_col=0)

    @cached_property
    def Z(self) -> pd.DataFrame:
        return self._csv("cluster_features_z.csv", index_col=0)

    @cached_property
    def scores(self) -> pd.DataFrame:
        return self._csv("risk_scores.csv", index_col=0)

    @cached_property
    def flags(self) -> pd.DataFrame:
        return self._csv("risk_flags.csv")

    @cached_property
    def okun(self) -> pd.DataFrame:
        return self._csv("okun.csv", index_col=0)

    # ---------- helpers
    def iso(self, country: str) -> str:
        if country in self.snap.index:
            return country
        if country in NAME_TO_ISO:
            return NAME_TO_ISO[country]
        low = {k.lower(): v for k, v in NAME_TO_ISO.items()}
        if country.lower() in low:
            return low[country.lower()]
        raise KeyError(f"Unknown or uncovered economy: {country}")

    def countries(self) -> list[str]:
        return sorted(self.snap.country.tolist())

    def value(self, iso, key):
        return _clean(self.snap.loc[iso].get(key, np.nan))

    def history(self, iso, key, start=2000) -> pd.Series:
        if key not in self.panel.columns or iso not in self.panel.index.get_level_values(0):
            return pd.Series(dtype=float)
        s = self.panel.loc[iso, key].dropna()
        return s[s.index >= start]

    def fc(self, iso, series) -> pd.DataFrame:
        return self.forecasts[(self.forecasts.iso3 == iso) & (self.forecasts.series == series)]

    # ---------- expert outputs (JSON-ready)
    def profile(self, iso: str) -> dict:
        r = self.snap.loc[iso]
        keys = ["gdp_usd", "gdp_growth", "growth_5y_avg", "gdp_pc_ppp", "population", "inflation",
                "unemp", "youth_unemp", "emp_ratio", "female_lfp", "current_account", "reserves_months",
                "gov_debt", "primary_balance", "ext_debt", "tax_rev", "poverty", "gini", "remittances", "oil_rents",
                "manufacturing", "internet", "broadband", "rnd", "hightech_exports", "patents_per_m",
                "tertiary_enrol", "life_exp", "u5_mortality", "electricity", "clean_cooking", "logistics",
                "private_credit", "account_ownership", "npl", "renewables", "pm25",
                "gov_effectiveness", "political_stability"]
        ind = {}
        for k in keys:
            v = r.get(k, np.nan)
            if pd.notna(v):
                yr = self.snap_years.loc[iso].get(k, np.nan) if k in self.snap_years.columns else np.nan
                ind[k] = {"label": BY_KEY[k].label if k in BY_KEY else k, "value": _clean(v),
                          "unit": BY_KEY[k].unit if k in BY_KEY else "", "year": None if pd.isna(yr) else int(yr)}
        if "gdp_usd" in ind:
            ind["gdp_usd"]["value_bn"] = round(ind["gdp_usd"]["value"] / 1e9, 1)
        c = self.clusters.loc[iso]
        return {"country": r.country, "iso3": iso, "region": r.region,
                "economic_profile": c.cluster_name, "indicators": ind}

    def forecast(self, iso: str, years=(2030, 2035)) -> dict:
        out = {"country": ISO_TO_NAME.get(iso, iso)}
        for key in SERIES:
            f = self.fc(iso, key)
            if f.empty:
                out[key] = None
                continue
            hist = self.history(iso, key)
            pts = {int(y): {"value": _clean(f[f.year == y].value.iloc[0]), "low80": _clean(f[f.year == y].lo.iloc[0]),
                            "high80": _clean(f[f.year == y].hi.iloc[0])} for y in years if (f.year == y).any()}
            d = {"label": SERIES[key][3], "last_actual_year": int(hist.index.max()) if len(hist) else None,
                 "last_actual": _clean(hist.iloc[-1]) if len(hist) else None, "forecast": pts}
            if SERIES[key][0]:
                d["unit"] = "US$ bn" if key == "gdp_real" else "int$"
                if key == "gdp_real":
                    d["last_actual"] = _clean(hist.iloc[-1] / 1e9) if len(hist) else None
                    for p in pts.values():
                        for kk in ("value", "low80", "high80"):
                            p[kk] = _clean(p[kk] / 1e9)
            else:
                d["unit"] = "%"
            out[key] = d
        out["gdp_real_cagr_to_2035_pct"] = self.value(iso, "gdp_cagr_fc")
        out["benchmark_avg_growth_2026_2030"] = {"asiapulse_pct": self.value(iso, "fc_growth_2026_30"),
                                                  "imf_weo_pct": self.value(iso, "imf_growth_2026_30")}
        return out

    def validation(self, iso: str) -> dict:
        b = self.backtest[self.backtest.iso3 == iso]
        return {"country": ISO_TO_NAME.get(iso, iso),
                "method": "Rolling-origin backtest, held-out origins 2017-2020 (incl. COVID), horizons 1-5y",
                "series": {r.series: {"error": _clean(r.error), "unit": r.unit, "confidence": r.confidence,
                                      "skill_vs_naive": _clean(r.skill_vs_naive), "interval_coverage80": _clean(r.coverage80)}
                           for r in b.itertuples()}}

    def risk(self, iso: str) -> dict:
        s = self.scores.loc[iso]
        f = self.flags[self.flags.iso3 == iso]
        return {"country": ISO_TO_NAME.get(iso, iso), "composite_vulnerability": _clean(s.composite),
                "label": s.label, "rank_most_vulnerable": int(s["rank"]), "of": int(len(self.scores)),
                "data_coverage": _clean(s.coverage),
                "pillars": {PILLAR_LABELS[c.replace("pillar_", "")]: _clean(s[c]) for c in self.scores.columns
                            if c.startswith("pillar_")},
                "red_flags": [{"flag": r.text, "value": _clean(r.value), "threshold": _clean(r.threshold), "basis": r.basis}
                              for r in f.itertuples()]}

    def peers(self, iso: str, n: int = 5) -> dict:
        c = self.clusters
        same = c.index[(c.cluster == c.loc[iso, "cluster"]) & (c.index != iso)].tolist()
        return {"country": ISO_TO_NAME.get(iso, iso), "economic_profile": c.loc[iso, "cluster_name"],
                "cluster_members": [ISO_TO_NAME.get(i, i) for i in same],
                "nearest_peers": [{"country": ISO_TO_NAME.get(i, i), "distance": round(d, 2)} for i, d in nearest_peers(iso, self.Z, n)]}

    def policies(self, iso: str, top_n: int = 5) -> list[dict]:
        return recommend(iso, self.snap, self.scores, self.flags, self.panel, self.clusters, top_n=top_n)

    def scenario(self, iso: str, levers: sc.Levers) -> tuple[pd.DataFrame, dict]:
        g = self.fc(iso, "gdp_real").set_index("year").value
        u = self.fc(iso, "unemp").set_index("year").value
        hist = self.history(iso, "gdp_real")
        r = self.snap.loc[iso]
        ctx = {"gdp_last": float(hist.iloc[-1]), "okun_beta": float(self.okun.loc[iso, "okun_beta"]) if iso in self.okun.index else -0.2}
        for k in ("oil_rents", "remittances", "gov_debt", "inflation_5y_median", "female_lfp", "emp_ratio", "unemp", "primary_balance", "imf_inflation_2026_30", "implied_interest_rate", "internet"):
            v = r.get(k, np.nan)
            ctx[k] = None if pd.isna(v) else float(v)
        path, summ = sc.simulate(g, u, ctx, levers)
        # Re-score risk under the scenario using the same index as the baseline.
        row = r.copy()
        row["gdp_cagr_fc"] = summ["cagr_scen"]
        row["unemp"] = summ["unemp_end_scen"]
        if not summ["debt_assumed"]:
            row["gov_debt"] = summ["debt_end_scen"]
        if levers.digital_adoption_pp and pd.notna(row.get("internet")):
            row["internet"] = min(100.0, row["internet"] + levers.digital_adoption_pp)
        if levers.flfp_increase_pp and pd.notna(row.get("female_lfp")):
            row["female_lfp"] = row["female_lfp"] + levers.flfp_increase_pp
        new = score_row(row, self.snap)
        summ["risk_baseline"] = {"score": _clean(self.scores.loc[iso, "composite"]), "label": self.scores.loc[iso, "label"]}
        summ["risk_scenario"] = {"score": _clean(new["composite"]), "label": new["label"]}
        summ["flags_scenario"] = [f["text"] for f in evaluate_flags(row)]
        summ["okun_beta"] = round(ctx["okun_beta"], 3)
        return path, summ

    @cached_property
    def model_params(self) -> dict:
        p = self.root / "model_params.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"series": {}, "weights": {}}

    def refit(self, iso: str, key: str) -> pd.DataFrame | None:
        """Re-run the forecast ensemble live for one economy/series with the learned weights & calibration."""
        from .config import FORECAST_END
        from .models.forecast import forecast_series

        sp = self.model_params["series"].get(key, {})
        pp = self.model_params.get("panel_paths", {}).get(f"{iso}|{key}")
        return forecast_series(self.history(iso, key), key, FORECAST_END,
                               self.model_params["weights"].get(f"{iso}|{key}"),
                               calib=sp.get("calib", 1.0), sigma_pool=sp.get("sigma_pool"),
                               extra={"panel": np.array(pp)} if pp else None)

    def compare(self, isos: list[str]) -> list[dict]:
        out = []
        for i in isos:
            out.append({"country": ISO_TO_NAME.get(i, i), "profile": self.clusters.loc[i, "cluster_name"],
                        "gdp_growth_5y_avg": self.value(i, "growth_5y_avg"), "gdp_cagr_fc": self.value(i, "gdp_cagr_fc"),
                        "gdp_pc_ppp": self.value(i, "gdp_pc_ppp"), "unemp": self.value(i, "unemp"),
                        "youth_unemp": self.value(i, "youth_unemp"), "female_lfp": self.value(i, "female_lfp"),
                        "inflation": self.value(i, "inflation"), "gov_debt": self.value(i, "gov_debt"),
                        "vulnerability": _clean(self.scores.loc[i, "composite"]), "risk_label": self.scores.loc[i, "label"]})
        return out
