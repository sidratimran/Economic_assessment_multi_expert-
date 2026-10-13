"""Risk Expert: a transparent, pillar-based vulnerability index plus rule-based red flags.

Scoring
-------
Each indicator is converted to a 0-100 *vulnerability percentile* within the Asian panel
(100 = most vulnerable). Indicators are averaged into pillars, pillars into a composite.
Everything is recomputable by hand from the published inputs.

Flags
-----
Flags fire on absolute, externally recognisable thresholds (e.g. reserves < 3 months of
imports, the IMF's traditional adequacy rule of thumb), so a country is never flagged just
for being at the bottom of a ranking. Every flag carries the value that triggered it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..indicators import PILLAR_LABELS

# pillar -> [(feature, direction)] ; direction -1 = higher value is more vulnerable
PILLARS: dict[str, list[tuple[str, int]]] = {
    "growth": [("growth_5y_avg", +1), ("gdp_cagr_fc", +1), ("growth_volatility", -1)],
    "labour": [("unemp", -1), ("youth_unemp", -1), ("emp_ratio_change_5y", +1), ("vuln_emp", -1), ("female_lfp", +1)],
    "macro": [("inflation_gap", -1), ("reserves_months", +1)],
    "external": [("current_account", +1), ("ext_debt", -1), ("resource_rents", -1), ("remittances", -1)],
    "fiscal": [("gov_debt", -1), ("tax_rev", +1)],
    "social": [("poverty", -1), ("gini", -1), ("neet_youth", -1), ("undernourishment", -1)],
    "governance": [("gov_effectiveness", +1), ("political_stability", +1), ("rule_of_law", +1), ("control_corruption", +1)],
    "climate": [("renewables", +1), ("co2_pc", -1), ("pm25", -1)],
    "technology": [("internet", +1), ("broadband", +1), ("hightech_exports", +1), ("ict_services_exports", +1),
                   ("rnd", +1), ("patents_per_m", +1), ("researchers", +1)],
    "human_capital": [("tertiary_enrol", +1), ("secondary_enrol", +1), ("life_exp", +1), ("u5_mortality", -1)],
    "infrastructure": [("electricity", +1), ("clean_cooking", +1), ("logistics", +1), ("water", +1)],
    "finance": [("private_credit", +1), ("account_ownership", +1), ("npl", -1)],
}
PILLAR_WEIGHTS = {p: (0.5 if p == "climate" else 1.0) for p in PILLARS}

LEVELS = [(60, "High"), (52, "Elevated"), (44, "Moderate"), (0, "Low")]


def risk_label(score: float) -> str:
    """Single source of truth for score → label (used by the index, Scenario Lab and AI tools)."""
    if score is None or pd.isna(score):
        return "Unrated"
    for cut, lab in LEVELS:
        if score >= cut:
            return lab
    return "Low"


@dataclass(frozen=True)
class Flag:
    key: str
    feature: str
    op: str
    threshold: float
    text: str
    pillar: str
    basis: str


FLAGS: list[Flag] = [
    Flag("high_inflation", "inflation", ">", 10, "Inflation above 10%", "macro", "Double-digit inflation erodes real incomes and signals loss of nominal anchor."),
    Flag("low_reserves", "reserves_months", "<", 3, "Reserves below 3 months of imports", "macro", "IMF traditional reserve-adequacy rule of thumb."),
    Flag("ca_deficit", "current_account", "<", -5, "Current-account deficit wider than 5% of GDP", "external", "Common early-warning threshold for external financing stress."),
    Flag("ext_debt", "ext_debt", ">", 60, "External debt above 60% of GNI", "external", "High external debt raises rollover and exchange-rate risk."),
    Flag("oil_dependence", "oil_rents", ">", 10, "Oil dependence: oil rents above 10% of GDP", "external", "Exposure to oil-price cycles and energy-transition risk."),
    Flag("remit_dependence", "remittances", ">", 10, "Remittance dependence: inflows above 10% of GDP", "external", "Household incomes exposed to host-country labour markets."),
    Flag("public_debt", "gov_debt", ">", 70, "Public debt above 70% of GDP", "fiscal", "IMF market-access-country debt-burden benchmark for emerging markets."),
    Flag("low_tax", "tax_rev", "<", 10, "Tax revenue below 10% of GDP", "fiscal", "Below the level generally associated with sustainable state capacity."),
    Flag("unemployment", "unemp", ">", 10, "Unemployment above 10%", "labour", "Double-digit unemployment."),
    Flag("youth_unemp", "youth_unemp", ">", 20, "Youth unemployment above 20%", "labour", "Risk of scarring effects and social unrest."),
    Flag("emp_decline", "emp_ratio_change_5y", "<", -2, "Employment ratio fell >2 pp in 5 years", "labour", "Weakening job creation relative to working-age population."),
    Flag("low_flfp", "female_lfp", "<", 30, "Female labour-force participation below 30%", "labour", "Large untapped labour supply; growth and inclusion gap."),
    Flag("neet", "neet_youth", ">", 25, "Over 25% of youth not in education, employment or training", "social", "SDG 8.6 indicator."),
    Flag("poverty", "poverty", ">", 10, "Extreme poverty above 10% of population", "social", "SDG 1.1 indicator."),
    Flag("inequality", "gini", ">", 40, "High inequality (Gini > 40)", "social", "Widely used high-inequality marker."),
    Flag("instability", "political_stability", "<", -1, "Severe political instability / conflict risk (WGI < -1)", "governance", "Bottom tail of the Worldwide Governance Indicators."),
    Flag("weak_gov", "gov_effectiveness", "<", -0.5, "Weak government effectiveness (WGI < -0.5)", "governance", "Constrains policy implementation capacity."),
    Flag("digital_divide", "internet", "<", 50, "Digital divide: under half the population online", "technology", "SDG 9.c universal internet access."),
    Flag("low_rnd", "rnd", "<", 0.3, "Very low R&D investment (< 0.3% of GDP)", "technology", "Limits technology absorption and innovation (SDG 9.5)."),
    Flag("child_mortality", "u5_mortality", ">", 25, "Under-5 mortality above the SDG 3.2 target (25 per 1,000)", "human_capital", "SDG 3.2 target."),
    Flag("low_tertiary", "tertiary_enrol", "<", 20, "Tertiary enrolment below 20%", "human_capital", "Thin pipeline of advanced skills for a knowledge economy."),
    Flag("undernourishment", "undernourishment", ">", 10, "Undernourishment above 10% of population", "social", "SDG 2.1 indicator."),
    Flag("electricity_gap", "electricity", "<", 95, "Electricity access below 95%", "infrastructure", "SDG 7.1.1 universal access."),
    Flag("clean_cooking", "clean_cooking", "<", 50, "Most households lack clean cooking fuels", "infrastructure", "SDG 7.1.2; major health burden from household air pollution."),
    Flag("water_gap", "water", "<", 90, "Basic drinking-water access below 90%", "infrastructure", "SDG 6.1."),
    Flag("bank_stress", "npl", ">", 8, "Banking stress: non-performing loans above 8%", "finance", "Elevated NPLs constrain credit and can become fiscal liabilities."),
    Flag("shallow_finance", "private_credit", "<", 25, "Shallow financial system: private credit below 25% of GDP", "finance", "Firms, especially SMEs, are credit-constrained."),
    Flag("unbanked", "account_ownership", "<", 50, "Majority of adults lack a financial account", "finance", "SDG 8.10 financial inclusion."),
    Flag("air_pollution", "pm25", ">", 35, "Hazardous air pollution (PM2.5 > 35 µg/m³, WHO interim target 1)", "climate", "Large health and productivity costs."),
    Flag("weak_growth", "gdp_cagr_fc", "<", 1.5, "Weak growth outlook (forecast real GDP CAGR < 1.5%)", "growth", "Below the pace needed to raise living standards meaningfully."),
    Flag("contraction", "gdp_cagr_fc", "<", 0, "Forecast real GDP contraction", "growth", "Model projects shrinking real output."),
]


def _features(snap: pd.DataFrame) -> pd.DataFrame:
    f = snap.copy()
    if "inflation_5y_median" in f:
        f["inflation_gap"] = (f["inflation_5y_median"] - 3).abs()
    return f


def _pct_vuln(value: float, ref: pd.Series, direction: int) -> float:
    ref = ref.dropna()
    if pd.isna(value) or ref.empty:
        return np.nan
    pct = ((ref < value).mean() + 0.5 * (ref == value).mean()) * 100
    return 100 - pct if direction > 0 else pct


def score_row(row: pd.Series | dict, reference: pd.DataFrame) -> dict:
    """Score one economy (possibly a hypothetical scenario) against the reference panel."""
    row = pd.Series(row)
    ref = _features(reference)
    if "inflation_5y_median" in row and "inflation_gap" not in row:
        row["inflation_gap"] = abs(row["inflation_5y_median"] - 3)
    pillars, n_used, n_total = {}, 0, 0
    for p, feats in PILLARS.items():
        vals = []
        for feat, d in feats:
            n_total += 1
            if feat in ref and feat in row and pd.notna(row[feat]):
                vals.append(_pct_vuln(float(row[feat]), ref[feat], d))
                n_used += 1
        pillars[p] = float(np.nanmean(vals)) if vals else np.nan
    w = {p: PILLAR_WEIGHTS[p] for p, v in pillars.items() if pd.notna(v)}
    comp = sum(pillars[p] * w[p] for p in w) / sum(w.values()) if w else np.nan
    return {"composite": comp, "label": risk_label(comp), "coverage": n_used / n_total, **{f"pillar_{p}": v for p, v in pillars.items()}}


def evaluate_flags(row: pd.Series | dict) -> list[dict]:
    row = pd.Series(row)
    out = []
    for fl in FLAGS:
        v = row.get(fl.feature, np.nan)
        if pd.isna(v):
            continue
        hit = v > fl.threshold if fl.op == ">" else v < fl.threshold
        if hit:
            out.append({"key": fl.key, "text": fl.text, "pillar": fl.pillar, "value": round(float(v), 2),
                        "threshold": fl.threshold, "basis": fl.basis})
    # contraction supersedes weak growth
    keys = {f["key"] for f in out}
    if "contraction" in keys:
        out = [f for f in out if f["key"] != "weak_growth"]
    return out


def score_all(snap: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, flags = {}, []
    feats = _features(snap)
    for iso, r in feats.iterrows():
        rows[iso] = score_row(r, snap)
        for f in evaluate_flags(r):
            flags.append({"iso3": iso, **f})
    scores = pd.DataFrame.from_dict(rows, orient="index")
    scores.index.name = "iso3"
    scores["rank"] = scores.composite.rank(ascending=False, method="min").astype("Int64")
    return scores, pd.DataFrame(flags)


def pillar_label(p: str) -> str:
    return PILLAR_LABELS.get(p, p)
