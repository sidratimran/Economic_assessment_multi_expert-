"""Policy Lab: a transparent macro scenario simulator.

This is deliberately a *small structural model*, not a black box:

* Growth: baseline = the ensemble forecast. Shocks and policy levers add/subtract growth
  through documented elasticities and multipliers (all editable in the UI).
* Unemployment: Okun's law, with the coefficient **estimated per country** from WDI data and
  shrunk towards the Asian pooled estimate (partial pooling) for robustness. Deviations fade
  30% a year (labour markets partially self-correct).
* Public debt: standard debt-dynamics identity
  ``d_t = d_{t-1}·(1+i)/(1+g_nominal) − primary_balance_t``, starting from IMF WEO debt and
  primary balance; ``i`` is the effective rate implied by each country's IMF interest bill.
* Gender participation: raising female LFP adds workers; output responds with a labour
  elasticity of 0.65 (a standard Cobb-Douglas labour share).
* Digital adoption: each pp rise in internet users lifts the GDP level by a conservative,
  editable 0.05% (the empirical literature on broadband/internet and growth finds larger effects).

Baseline and scenario use identical assumptions, so differences isolate the policy effect.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class Levers:
    # external shocks (temporary, decay 50% per year)
    demand_shock_pp: float = 0.0       # global demand shock to growth, pp
    oil_price_pct: float = 0.0         # oil price change, %
    remittance_pct: float = 0.0        # change in remittance inflows, %
    # domestic policy
    fiscal_consolidation_pp: float = 0.0   # primary-balance improvement, % GDP (phased over 3 years)
    public_investment_pp: float = 0.0      # extra public investment, % GDP per year (sustained)
    flfp_increase_pp: float = 0.0          # rise in female LFP by 2035, pp (phased linearly)
    interest_rate_pp: float = 0.0          # change in effective interest rate on public debt, pp
    digital_adoption_pp: float = 0.0       # rise in internet-user share by 2035, pp (phased linearly)
    # assumptions
    fiscal_multiplier: float = 0.5
    investment_multiplier: float = 0.8
    investment_supply_effect: float = 0.1  # long-run growth pp per 1% GDP of sustained investment, from year 3
    digital_elasticity: float = 0.05       # % rise in GDP level per pp increase in internet users (conservative)
    real_interest_rate: float = 2.0        # fallback only: real rate on debt when the IMF-implied rate is unavailable
    baseline_primary_balance: float | None = None  # % GDP; None = latest IMF WEO value (or -1)


def estimate_okun(panel: pd.DataFrame, shrink_k: float = 15.0) -> pd.DataFrame:
    """Δunemployment = a + β·growth, per country, partially pooled towards the panel β."""
    df = panel[["unemp", "gdp_growth"]].copy()
    df["d_unemp"] = df.groupby(level="iso3")["unemp"].diff()
    df = df.dropna()
    x, y = df.gdp_growth.values, df.d_unemp.values
    pooled = float(np.polyfit(x, y, 1)[0])
    rows = []
    for iso, g in df.groupby(level="iso3"):
        n = len(g)
        b = float(np.polyfit(g.gdp_growth, g.d_unemp, 1)[0]) if n >= 8 and g.gdp_growth.std() > 0 else pooled
        w = n / (n + shrink_k)
        beta = float(np.clip(w * b + (1 - w) * pooled, -0.6, 0.0))
        rows.append({"iso3": iso, "okun_beta": beta, "okun_raw": b, "n": n})
    out = pd.DataFrame(rows).set_index("iso3")
    out.attrs["pooled"] = pooled
    return out


def simulate(base_gdp: pd.Series, base_unemp: pd.Series, ctx: dict, lv: Levers) -> tuple[pd.DataFrame, dict]:
    """Run baseline vs scenario.

    base_gdp / base_unemp: forecast paths indexed by year (first index = first forecast year).
    ctx: latest values — gdp_last (level at year before path), oil_rents, remittances, gov_debt,
         inflation_5y_median, female_lfp, emp_ratio, unemp, okun_beta.
    """
    years = base_gdp.index.to_numpy()
    H = len(years)
    k = np.arange(H)
    level = np.concatenate([[ctx["gdp_last"]], base_gdp.to_numpy()])
    g_base = (level[1:] / level[:-1] - 1) * 100

    decay = 0.5 ** k
    oil_rents = ctx.get("oil_rents") or 0.0
    if oil_rents >= 2:
        oil_eff = lv.oil_price_pct * (oil_rents / 100) * 0.15
    else:
        oil_eff = -0.015 * lv.oil_price_pct
    remit_eff = (ctx.get("remittances") or 0.0) / 100 * lv.remittance_pct * 0.6
    temp = (lv.demand_shock_pp + oil_eff + remit_eff) * decay

    d_pb = np.minimum(k + 1, 3) / 3 * lv.fiscal_consolidation_pp            # cumulative primary-balance change
    fiscal_eff = -lv.fiscal_multiplier * np.diff(np.concatenate([[0], d_pb]))  # growth hit when tightening happens
    inv_eff = np.where(k == 0, lv.investment_multiplier * lv.public_investment_pp, 0.0) \
        + np.where(k >= 2, lv.investment_supply_effect * lv.public_investment_pp, 0.0)

    emp = ctx.get("emp_ratio") or 60.0
    u = ctx.get("unemp") or 5.0
    d_flfp = lv.flfp_increase_pp * (k + 1) / H
    d_emp = 0.5 * d_flfp * (1 - u / 100)               # women ≈ half of the 15+ population
    lvl_gain = 0.65 * d_emp / emp                        # proportional output gain
    flfp_eff = np.diff(np.concatenate([[0], lvl_gain])) * 100

    internet = ctx.get("internet") or 50.0
    dig_total = min(lv.digital_adoption_pp, max(100.0 - internet, 0.0))   # cannot exceed 100% online
    d_dig = dig_total * (k + 1) / H
    dig_eff = np.diff(np.concatenate([[0], lv.digital_elasticity * d_dig]))

    g_scen = g_base + temp + fiscal_eff + inv_eff + flfp_eff + dig_eff
    gdp_scen = ctx["gdp_last"] * np.cumprod(1 + g_scen / 100)

    beta = ctx.get("okun_beta", -0.2)
    u_dev = np.zeros(H)
    for i in range(H):
        u_dev[i] = (0.7 * u_dev[i - 1] if i else 0.0) + beta * (g_scen[i] - g_base[i])
    unemp_base = base_unemp.reindex(years).to_numpy(dtype=float)
    unemp_scen = np.clip(unemp_base + u_dev, 0, 100)

    infl_src = ctx.get("imf_inflation_2026_30")
    if infl_src is None or pd.isna(infl_src):
        infl_src = ctx.get("inflation_5y_median") or 3.0
    infl = float(np.clip(infl_src, 0, 15))
    implied = ctx.get("implied_interest_rate")
    rate_from_data = implied is not None and not pd.isna(implied)
    nominal_rate = float(implied) if rate_from_data else infl + lv.real_interest_rate
    debt0 = ctx.get("gov_debt")
    debt_assumed = debt0 is None or pd.isna(debt0)
    debt0 = 50.0 if debt_assumed else float(debt0)

    def debt_path(g, pb, rate):
        d, out = debt0, []
        for gi, pbi in zip(g, pb):
            gn = (1 + gi / 100) * (1 + infl / 100) - 1
            d = max(d * (1 + rate / 100) / (1 + gn) - pbi, 0.0)
            out.append(d)
        return np.array(out)

    pb0 = lv.baseline_primary_balance
    if pb0 is None:
        pb0 = ctx.get("primary_balance")
        pb0 = -1.0 if pb0 is None or pd.isna(pb0) else float(pb0)
    pb_base = np.full(H, pb0)
    pb_scen = pb_base + d_pb - lv.public_investment_pp
    debt_base = debt_path(g_base, pb_base, nominal_rate)
    debt_scen = debt_path(g_scen, pb_scen, nominal_rate + lv.interest_rate_pp)

    out = pd.DataFrame({
        "year": years, "growth_base": g_base, "growth_scen": g_scen,
        "gdp_base": base_gdp.to_numpy(), "gdp_scen": gdp_scen,
        "unemp_base": unemp_base, "unemp_scen": unemp_scen,
        "debt_base": debt_base, "debt_scen": debt_scen,
        "flfp_gain": d_flfp, "internet_gain": d_dig,
    })
    summary = {
        "gdp_end_diff_pct": float((gdp_scen[-1] / base_gdp.iloc[-1] - 1) * 100),
        "avg_growth_diff_pp": float(np.mean(g_scen - g_base)),
        "peak_unemp_diff_pp": float(u_dev[np.argmax(np.abs(u_dev))]) if H else 0.0,
        "unemp_end_scen": float(unemp_scen[-1]),
        "debt_end_base": float(debt_base[-1]), "debt_end_scen": float(debt_scen[-1]),
        "debt_assumed": debt_assumed, "debt_start": debt0, "primary_balance_assumed": pb0, "inflation_assumed": infl, "nominal_rate_assumed": nominal_rate, "rate_from_data": rate_from_data,
        "cagr_scen": float((np.prod(1 + g_scen / 100) ** (1 / H) - 1) * 100),
        "cagr_base": float((np.prod(1 + g_base / 100) ** (1 / H) - 1) * 100),
        "levers": asdict(lv),
    }
    return out, summary
