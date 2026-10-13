"""Turn raw long-format observations into an analysis panel and a latest-value snapshot."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .countries import ISO_TO_NAME, ISO_TO_REGION
from .indicators import INDICATORS

# How far back a "latest" value may come from before we treat it as missing.
MAX_STALENESS = {"poverty": 12, "gini": 12, "gov_debt": 8, "ext_debt": 6, "tax_rev": 8,
                 "edu_exp": 8, "neet_youth": 8, "oil_rents": 6, "resource_rents": 6, "renewables": 6,
                 "logistics": 6, "account_ownership": 6, "rnd": 8, "researchers": 8, "hightech_exports": 6,
                 "patents_resident": 6, "tertiary_enrol": 6, "secondary_enrol": 6, "npl": 6, "pm25": 5}
DEFAULT_STALENESS = 4


def build_panel(long: pd.DataFrame) -> pd.DataFrame:
    """Wide panel indexed by (iso3, year), one column per indicator key."""
    panel = long.pivot_table(index=["iso3", "year"], columns="key", values="value", aggfunc="first")
    panel = panel.reindex(columns=[i.key for i in INDICATORS if i.key in panel.columns]).sort_index()
    return panel


def latest_snapshot(panel: pd.DataFrame, ref_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Latest non-missing value per country & indicator, respecting a staleness limit.

    Returns (values, years) — two frames indexed by iso3.
    """
    values, years = {}, {}
    for iso, g in panel.groupby(level="iso3"):
        g = g.droplevel("iso3")
        v, y = {}, {}
        for col in panel.columns:
            s = g[col].dropna()
            if s.empty:
                continue
            yr = int(s.index.max())
            if ref_year - yr > MAX_STALENESS.get(col, DEFAULT_STALENESS):
                continue
            v[col], y[col] = float(s.loc[yr]), yr
        values[iso], years[iso] = v, y
    vals = pd.DataFrame.from_dict(values, orient="index")
    yrs = pd.DataFrame.from_dict(years, orient="index")
    return vals, yrs


def derived_features(panel: pd.DataFrame, snap: pd.DataFrame) -> pd.DataFrame:
    """Add multi-year features that are more robust than a single year."""
    out = snap.copy()
    for iso, g in panel.groupby(level="iso3"):
        g = g.droplevel("iso3")
        gr = g.get("gdp_growth", pd.Series(dtype=float)).dropna()
        out.loc[iso, "growth_5y_avg"] = gr.tail(5).mean() if len(gr) else np.nan
        out.loc[iso, "growth_volatility"] = gr.tail(15).std() if len(gr) > 4 else np.nan
        inf = g.get("inflation", pd.Series(dtype=float)).dropna()
        out.loc[iso, "inflation_5y_median"] = inf.tail(5).median() if len(inf) else np.nan
        er = g.get("emp_ratio", pd.Series(dtype=float)).dropna()
        out.loc[iso, "emp_ratio_change_5y"] = er.iloc[-1] - er.iloc[-6] if len(er) >= 6 else np.nan
        flfp = g.get("female_lfp", pd.Series(dtype=float)).dropna()
        out.loc[iso, "female_lfp"] = flfp.iloc[-1] if len(flfp) else out.loc[iso].get("female_lfp", np.nan)
    if {"patents_resident", "population"} <= set(out.columns):
        out["patents_per_m"] = out["patents_resident"] / out["population"] * 1e6
    out.insert(0, "country", [ISO_TO_NAME.get(i, i) for i in out.index])
    out.insert(1, "region", [ISO_TO_REGION.get(i, "") for i in out.index])
    out.index.name = "iso3"
    return out
