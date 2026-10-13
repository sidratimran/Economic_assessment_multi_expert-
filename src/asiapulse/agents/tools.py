"""The five quantitative experts, exposed as function-calling tools for Qwen."""
from __future__ import annotations

import json
from dataclasses import fields

from ..models.scenario import Levers
from ..store import Store

_COUNTRY = {"type": "string", "description": "Economy name, e.g. 'Pakistan', 'Viet Nam' → use 'Vietnam'"}

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "get_country_profile",
        "description": "Pattern Expert: latest official indicators (World Bank WDI/WGI) with the year of each value, and the data-driven economic profile.",
        "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "get_forecast",
        "description": "Forecast Expert: ensemble forecasts with 80% intervals for real GDP, GDP per capita, employment ratio and unemployment for 2030 and 2035.",
        "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "get_validation",
        "description": "Validation Expert: held-out backtest error, skill versus a naive forecast, interval coverage and a confidence label for each forecast series.",
        "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "get_risk",
        "description": "Risk Expert: composite vulnerability index (0-100, higher = more vulnerable), eight pillar scores, rank in Asia and threshold-based red flags.",
        "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "get_peers",
        "description": "Pattern Expert: economic cluster members and nearest peer economies in standardised feature space.",
        "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "get_policy_options",
        "description": "Policy Expert: ranked policy packages addressing diagnosed vulnerabilities, with SDG targets, KPIs, peer targets and Asian precedents that improved the KPI most.",
        "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "run_policy_scenario",
        "description": "Policy Lab: simulate shocks and policy levers to 2035; returns growth, unemployment (Okun's law), public-debt paths and re-scored risk versus baseline.",
        "parameters": {"type": "object", "properties": {
            "country": _COUNTRY,
            "demand_shock_pp": {"type": "number", "description": "Global demand shock to growth, percentage points (temporary)"},
            "oil_price_pct": {"type": "number", "description": "Oil price change, % (temporary)"},
            "remittance_pct": {"type": "number", "description": "Change in remittance inflows, % (temporary)"},
            "fiscal_consolidation_pp": {"type": "number", "description": "Primary-balance improvement, % of GDP, phased over 3 years"},
            "public_investment_pp": {"type": "number", "description": "Extra public investment, % of GDP per year"},
            "flfp_increase_pp": {"type": "number", "description": "Increase in female labour-force participation by 2035, pp"},
            "interest_rate_pp": {"type": "number", "description": "Change in effective interest rate on public debt, pp"},
            "digital_adoption_pp": {"type": "number", "description": "Increase in internet-user share of population by 2035, pp"}},
            "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "compare_countries",
        "description": "Side-by-side key indicators and vulnerability for 2-6 economies.",
        "parameters": {"type": "object", "properties": {"countries": {"type": "array", "items": _COUNTRY}},
                       "required": ["countries"]}}},
]


def execute(store: Store, name: str, args: dict) -> dict | list:
    """Run a tool; always returns JSON-serialisable data (errors are returned, not raised)."""
    try:
        if name == "compare_countries":
            return store.compare([store.iso(c) for c in args.get("countries", [])][:6])
        iso = store.iso(args["country"])
        if name == "get_country_profile":
            return store.profile(iso)
        if name == "get_forecast":
            return store.forecast(iso)
        if name == "get_validation":
            return store.validation(iso)
        if name == "get_risk":
            return store.risk(iso)
        if name == "get_peers":
            return store.peers(iso)
        if name == "get_policy_options":
            pol = store.policies(iso)
            for p in pol:  # keep the payload compact for the LLM
                p["precedents"] = [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in d.items() if k != "iso3"}
                                   for d in p["precedents"]]
            return pol
        if name == "run_policy_scenario":
            valid = {f.name for f in fields(Levers)}
            lv = Levers(**{k: float(v) for k, v in args.items() if k in valid})
            path, summ = store.scenario(iso, lv)
            summ["path_2030"] = {k: round(float(v), 2) for k, v in path[path.year == 2030].iloc[0].items() if k != "year"} \
                if (path.year == 2030).any() else None
            summ["levers"] = {k: v for k, v in summ["levers"].items() if v}
            return summ
        return {"error": f"unknown tool {name}"}
    except Exception as ex:
        return {"error": str(ex)}


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
