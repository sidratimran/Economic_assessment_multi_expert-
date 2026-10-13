"""Qwen policy analyst: an agent that plans, calls the expert tools, then writes a grounded brief.

Flow: question → Qwen decides which experts to consult (function calling) → tools run
locally on the pipeline outputs → Qwen synthesises → grounding check on every number.
If no API key is configured (or the call fails) a deterministic analyst calls the same tools
and writes a template brief, so the product always works in a demo.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from ..config import qwen_settings
from ..store import Store
from .grounding import verify
from .tools import TOOL_SPECS, execute, to_json

SYSTEM = """You are the AsiaPulse Policy Analyst, advising ministries of finance, planning and labour in Asia.
You work with five quantitative experts, available as tools. Rules:
1. ALWAYS call tools before answering. For a country assessment call at least get_risk, get_forecast,
   get_validation and get_policy_options. Use run_policy_scenario when the user asks "what if".
2. Use ONLY numbers returned by tools. Never invent figures, causes, events or citations. Copy numbers
   exactly as returned (you may round to one decimal). Do not compute new numbers yourself.
3. Distinguish data (with its year) from forecasts (with their 80% range and confidence label).
4. If the validation expert shows the model did not beat the naive benchmark, say so.
5. Write for a policymaker: decision-oriented, specific, concise. Use markdown with these sections:
   **Bottom line** · **Diagnosis** · **Outlook & confidence** · **Policy priorities** (each with SDG
   targets and a KPI) · **What could change the picture** · **Caveats**.
6. Tag each key claim with its source expert in brackets, e.g. [Risk], [Forecast], [Validation], [Policy], [Scenario].
7. This is decision support, not financial or investment advice."""

PRETTY = {"get_country_profile": "Pattern · profile", "get_forecast": "Forecast", "get_validation": "Validation",
          "get_risk": "Risk", "get_peers": "Pattern · peers", "get_policy_options": "Policy",
          "run_policy_scenario": "Scenario", "compare_countries": "Compare"}


@dataclass
class AgentResult:
    answer: str
    trace: list[dict] = field(default_factory=list)
    grounding: dict = field(default_factory=dict)
    mode: str = "qwen"
    error: str | None = None
    tool_outputs: list = field(default_factory=list)


def ask(store: Store, question: str, country: str, history: list[dict] | None = None,
        max_steps: int = 8) -> AgentResult:
    cfg = qwen_settings()
    if not cfg["api_key"]:
        return offline_brief(store, country, question, reason="Qwen not configured — deterministic analyst used.")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=60)
        msgs = [{"role": "system", "content": SYSTEM}]
        msgs += (history or [])[-6:]
        msgs.append({"role": "user", "content": f"Focus economy: {country}.\nQuestion: {question}"})
        trace, outputs = [], []
        for _ in range(max_steps):
            res = client.chat.completions.create(model=cfg["model"], messages=msgs, tools=TOOL_SPECS,
                                                 tool_choice="auto", temperature=0.2, max_tokens=cfg["max_tokens"])
            msg = res.choices[0].message
            if not msg.tool_calls:
                answer = re.sub(r"<think>.*?</think>", "", msg.content or "", flags=re.S).strip()  # Qwen3 reasoning traces
                if not outputs:  # model skipped the tools: refuse to show an ungrounded answer
                    return offline_brief(store, country, question, reason="Model answered without consulting the experts; deterministic brief shown instead.")
                return AgentResult(answer, trace, verify(answer, outputs, question), "qwen", None, outputs)
            msgs.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": tc.id, "type": "function",
                                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                        for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                t0 = time.time()
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                out = execute(store, tc.function.name, args)
                outputs.append(out)
                trace.append({"tool": tc.function.name, "expert": PRETTY.get(tc.function.name, tc.function.name),
                              "args": args, "ms": int((time.time() - t0) * 1000),
                              "ok": not (isinstance(out, dict) and "error" in out)})
                msgs.append({"role": "tool", "tool_call_id": tc.id, "content": to_json(out)})
        return offline_brief(store, country, question, reason="Agent step limit reached.")
    except Exception as ex:  # network, auth, quota…
        return offline_brief(store, country, question, reason=f"Qwen call failed ({type(ex).__name__}: {ex}).")


def _fmt(v, d=1, suf=""):
    return "n/a" if v is None else f"{v:,.{d}f}{suf}"


def offline_brief(store: Store, country: str, question: str = "", reason: str = "") -> AgentResult:
    iso = store.iso(country)
    calls = [("get_risk", {}), ("get_forecast", {}), ("get_validation", {}), ("get_policy_options", {}), ("get_peers", {})]
    outs, trace = {}, []
    for name, extra in calls:
        t0 = time.time()
        outs[name] = execute(store, name, {"country": country, **extra})
        trace.append({"tool": name, "expert": PRETTY[name], "args": {"country": country}, "ms": int((time.time() - t0) * 1000), "ok": True})
    risk, fc, val, pol, peers = (outs[k] for k, _ in calls)
    g = fc.get("gdp_real") or {}
    g35 = (g.get("forecast") or {}).get(2035, {})
    u = fc.get("unemp") or {}
    u35 = (u.get("forecast") or {}).get(2035, {})
    gv = val["series"].get("gdp_real", {})
    pillars = sorted(((k, v) for k, v in risk["pillars"].items() if v is not None), key=lambda x: -x[1])

    lines = [f"**Bottom line** — {risk['country']} is rated **{risk['label']}** vulnerability "
             f"({_fmt(risk['composite_vulnerability'])}/100, rank {risk['rank_most_vulnerable']} of {risk['of']} in Asia) [Risk]. "
             f"Real GDP is projected to grow {_fmt(fc.get('gdp_real_cagr_to_2035_pct'), 1, '% a year')} to 2035 [Forecast].",
             "", "**Diagnosis**"]
    lines += [f"- {k}: {_fmt(v, 0)}/100" for k, v in pillars[:3]]
    lines += [f"- 🚩 {f['flag']} (value {_fmt(f['value'], 1)}) [Risk]" for f in risk["red_flags"][:5]] or ["- No threshold-based red flags."]
    lines += ["", "**Outlook & confidence**",
              f"- Real GDP 2035: US$ {_fmt(g35.get('value'))} bn (80% range {_fmt(g35.get('low80'))}–{_fmt(g35.get('high80'))}) [Forecast]",
              f"- Unemployment 2035: {_fmt(u35.get('value'), 1, '%')} (80% range {_fmt(u35.get('low80'), 1)}–{_fmt(u35.get('high80'), 1)}) [Forecast]",
              f"- GDP forecast confidence: **{gv.get('confidence', 'n/a')}** — held-out MAPE {_fmt(gv.get('error'), 1, '%')}, "
              f"skill vs naive {_fmt(gv.get('skill_vs_naive'), 2)} [Validation]", "", "**Policy priorities**"]
    for i, p in enumerate(pol[:4], 1):
        prec = ", ".join(d["country"] for d in p["precedents"][:2]) or "—"
        lines.append(f"{i}. **{p['title']}** ({p['horizon']}) — {p['trigger']}. KPI: {p['kpi_label']} "
                     f"now {_fmt(p['kpi_now'])}, peer target {_fmt(p['kpi_peer_target'])}. {', '.join(p['sdgs'])}. "
                     f"Precedents: {prec} [Policy]")
    lines += ["", "**Peers** — " + ", ".join(d["country"] for d in peers["nearest_peers"]) + " [Pattern]",
              "", "**Caveats** — Forecasts are statistical projections, not guarantees; risk scores are relative to "
              "the Asian panel. Decision support, not financial advice."]
    answer = "\n".join(lines)
    return AgentResult(answer, trace, verify(answer, list(outs.values()), question), "offline", reason, list(outs.values()))
