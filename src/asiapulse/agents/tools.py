"""The five quantitative experts, exposed as function-calling tools for Qwen."""
from __future__ import annotations

import json
from dataclasses import fields

from ..models.scenario import Levers
from ..store import Store

_COUNTRY = {"type": "string", "description": "Economy name, e.g. 'Pakistan', 'Viet Nam' → use 'Vietnam'"}

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "get_forecast",
        "description": "GDP/employment forecasts with 80% intervals to 2035.",
        "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "get_risk",
        "description": "Vulnerability index (0-100), pillar scores, rank and red flags.",
        "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "get_validation",
        "description": "Backtest accuracy, skill vs naive, confidence label.",
        "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "get_policy_options",
        "description": "Top policy packages with SDG targets and peer benchmarks.",
        "parameters": {"type": "object", "properties": {"country": _COUNTRY}, "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "run_policy_scenario",
        "description": "Simulate shocks to 2035. Levers: demand_shock_pp, oil_price_pct, remittance_pct, fiscal_consolidation_pp, public_investment_pp, flfp_increase_pp, interest_rate_pp, digital_adoption_pp.",
        "parameters": {"type": "object", "properties": {
            "country": _COUNTRY,
            "demand_shock_pp": {"type": "number"},
            "oil_price_pct": {"type": "number"},
            "remittance_pct": {"type": "number"},
            "fiscal_consolidation_pp": {"type": "number"},
            "public_investment_pp": {"type": "number"},
            "flfp_increase_pp": {"type": "number"},
            "interest_rate_pp": {"type": "number"},
            "digital_adoption_pp": {"type": "number"}},
            "required": ["country"]}}},
    {"type": "function", "function": {
        "name": "compare_countries",
        "description": "Side-by-side indicators for 2-6 economies.",
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
            pol = store.policies(iso)[:4]
            for p in pol:
                p["precedents"] = [{"country": d.get("country", ""), "change": round(d.get("change", 0), 1)}
                                   for d in p.get("precedents", [])[:2]]
                for k in list(p.keys()):
                    if k not in ("title", "trigger", "kpi_label", "kpi_now", "kpi_peer_target", "sdgs", "precedents", "horizon"):
                        del p[k]
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
