"""Downloadable policy brief (Markdown and PDF)."""
from __future__ import annotations

import re
from datetime import date

from fpdf import FPDF

_REPL = {"—": "-", "–": "-", "·": "-", "≈": "~", "…": "...", "→": "->", "“": '"', "”": '"', "’": "'",
         "‘": "'", "µ": "u", "³": "3", "🚩": "[!]", "✓": "v", "•": "-", "≥": ">=", "≤": "<="}


def _latin(s: str) -> str:
    for k, v in _REPL.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


def markdown_brief(country: str, analysis_md: str, risk: dict, policies: list[dict], meta: dict) -> str:
    lines = [f"# AsiaPulse AI — Policy Brief: {country}", f"_Generated {date.today():%d %B %Y} · data reference year "
             f"{meta.get('reference_year')} · World Bank WDI/WGI, IMF WEO_", "",
             f"**Vulnerability:** {risk['label']} ({risk['composite_vulnerability']}/100, rank "
             f"{risk['rank_most_vulnerable']} of {risk['of']})", "", "## Assessment", analysis_md, "",
             "## Policy package"]
    for i, p in enumerate(policies, 1):
        lines += [f"### {i}. {p['title']} ({p['horizon']})", f"*Why:* {p['trigger']}", f"*Objective:* {p['objective']}"]
        lines += [f"- {a}" for a in p["actions"]]
        lines += [f"*KPI:* {p['kpi_label']} — now {p['kpi_now']}, peer target {p['kpi_peer_target']} · "
                  f"*SDGs:* {', '.join(p['sdgs'])} · *Lead:* {p['lead']}", ""]
    lines += ["---", "Forecasts are statistical projections with stated uncertainty; this brief is decision support, "
              "not financial advice."]
    return "\n".join(lines)


def pdf_brief(md: str) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_margins(16, 16, 16)
    for raw in md.splitlines():
        line = _latin(raw.rstrip())
        text = re.sub(r"[*_`]", "", line)
        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 16); pdf.set_text_color(15, 40, 80)
            pdf.multi_cell(0, 8, text[2:], new_x="LMARGIN", new_y="NEXT"); pdf.ln(1)
        elif line.startswith("## "):
            pdf.ln(2); pdf.set_font("Helvetica", "B", 13); pdf.set_text_color(15, 40, 80)
            pdf.multi_cell(0, 7, text[3:], new_x="LMARGIN", new_y="NEXT")
        elif line.startswith("### "):
            pdf.set_font("Helvetica", "B", 11); pdf.set_text_color(30, 30, 30)
            pdf.multi_cell(0, 6, text[4:], new_x="LMARGIN", new_y="NEXT")
        elif line.strip() == "---":
            pdf.ln(2); pdf.line(16, pdf.get_y(), 194, pdf.get_y()); pdf.ln(2)
        elif line.startswith("- ") or re.match(r"^\d+\. ", line):
            pdf.set_font("Helvetica", "", 9.5); pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 5, "  " + text, new_x="LMARGIN", new_y="NEXT")
        elif not line.strip():
            pdf.ln(2)
        else:
            pdf.set_font("Helvetica", "", 9.5); pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
