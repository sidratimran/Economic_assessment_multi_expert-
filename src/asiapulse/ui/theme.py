"""Visual system: CSS, Plotly template and small HTML components.

Colours follow a validated, colour-blind-checked palette: one categorical order (never
cycled), a single-hue blue ramp for magnitude, a blue↔red diverging pair with a grey
midpoint, and a reserved status palette that always ships with an icon + label.
"""
from __future__ import annotations

import html

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781",
       "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#ffffff", "page": "#f9f9f7"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIVERGING = [[0, "#2a78d6"], [0.5, "#f0efec"], [1, "#e34948"]]
BAND = "rgba(42,120,214,0.14)"

STATUS = {  # level: (icon, solid, text-on-tint, tint)
    "Low": ("●", "#0ca30c", "#006300", "#e7f6e7"),
    "Moderate": ("▲", "#fab219", "#7a5200", "#fff4dc"),
    "Elevated": ("◆", "#ec835a", "#9a3b12", "#fdebe3"),
    "High": ("■", "#d03b3b", "#a32626", "#fbe6e6"),
    "Unrated": ("○", "#898781", "#52514e", "#f0efec"),
}

CSS = """
<style>
:root { --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --line:rgba(11,11,11,.10); --grid:#e1e0d9;
        --surface:#ffffff; --page:#f9f9f7; --accent:#2a78d6; }
html, body, [class*="css"], .stApp { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.stApp { background: var(--page); }
.block-container { max-width: 1440px; padding: 1.4rem 2.2rem 3rem; }
section[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--line); }
section[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
h1, h2, h3, h4 { color: var(--ink); letter-spacing: -.01em; font-weight: 650; }
.page-head { display:flex; justify-content:space-between; align-items:flex-end; gap:16px;
             border-bottom:1px solid var(--line); padding-bottom:14px; margin-bottom:18px; }
.page-head h1 { font-size:1.65rem; margin:0; padding:0; }
.page-head .sub { color: var(--ink2); font-size:.92rem; margin-top:4px; max-width: 880px; }
.page-head .meta { color: var(--muted); font-size:.78rem; text-align:right; white-space:nowrap; }
.section { font-size:.8rem; font-weight:650; color: var(--ink2); text-transform: uppercase; letter-spacing:.06em;
           margin: 22px 0 10px; }
.card { background: var(--surface); border:1px solid var(--line); border-radius:12px; padding:16px 18px; margin-bottom:12px; }
.card h4 { margin:0 0 6px; font-size:1rem; }
.kpi { background: var(--surface); border:1px solid var(--line); border-radius:12px; padding:14px 16px; height:100%; }
.kpi .lab { color: var(--ink2); font-size:.78rem; }
.kpi .val { color: var(--ink); font-size:1.45rem; font-weight:650; margin-top:4px; line-height:1.15; }
.kpi .note { color: var(--muted); font-size:.74rem; margin-top:4px; }
.kpi .up { color:#006300; } .kpi .down { color:#a32626; }
.chip { display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px;
        font-size:.78rem; font-weight:600; border:1px solid rgba(11,11,11,.06); }
.flag { display:flex; gap:10px; padding:10px 12px; border:1px solid var(--line); border-left:3px solid #d03b3b;
        border-radius:8px; background:#fff; margin-bottom:8px; font-size:.88rem; color:var(--ink); }
.flag small { color: var(--muted); display:block; margin-top:2px; }
.note-box { background:#f2f6fc; border:1px solid #d6e4f7; border-radius:10px; padding:11px 14px; color:#1d3b63; font-size:.86rem; }
.warn-box { background:#fff7e6; border:1px solid #f3dfb2; border-radius:10px; padding:11px 14px; color:#5c4100; font-size:.86rem; }
.live-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:#0ca30c; margin-right:6px;
            box-shadow:0 0 0 3px rgba(12,163,12,.18); }
.stale-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:#fab219; margin-right:6px; }
.brand { font-weight:700; font-size:1.15rem; color:var(--ink); }
.brand-sub { color:var(--muted); font-size:.78rem; margin-bottom:8px; }
.muted { color: var(--muted); font-size:.8rem; }
.rowlist div { display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid #efeee9; font-size:.88rem; }
.rowlist div:last-child { border-bottom:none; }
div[data-testid="stExpander"] { background: var(--surface); border-radius:12px; }
footer { visibility:hidden; }
</style>
"""


def _template():
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', color=INK["secondary"], size=12),
        colorway=SERIES, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor=INK["grid"], linecolor=INK["axis"], zeroline=False, ticks="", showgrid=False),
        yaxis=dict(gridcolor=INK["grid"], linecolor=INK["axis"], zeroline=False, ticks=""),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=INK["axis"], font=dict(color=INK["primary"], size=12)),
        legend=dict(orientation="h", yanchor="top", y=-0.14, xanchor="left", x=0, title=None,
                    font=dict(color=INK["secondary"])),
        margin=dict(l=8, r=8, t=36, b=8), hovermode="x unified",
        title=dict(font=dict(size=14, color=INK["primary"]), x=0, xanchor="left"),
    )
    return t


pio.templates["asiapulse"] = _template()
pio.templates.default = "asiapulse"


def esc(x) -> str:
    return html.escape(str(x))


def fmt(v, d=1, suf="", pre="", na="—"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return na
    return f"{pre}{v:,.{d}f}{suf}"


def chip(level: str) -> str:
    icon, _, txt, tint = STATUS.get(level, STATUS["Unrated"])
    return f'<span class="chip" style="background:{tint};color:{txt}">{icon} {esc(level)}</span>'


def kpi(label: str, value: str, note: str = "", tone: str | None = None) -> str:
    cls = {"up": "up", "down": "down"}.get(tone or "", "")
    return (f'<div class="kpi"><div class="lab">{esc(label)}</div><div class="val">{value}</div>'
            f'<div class="note {cls}">{note}</div></div>')


def page_head(title: str, sub: str, meta: str = "") -> str:
    return (f'<div class="page-head"><div><h1>{esc(title)}</h1><div class="sub">{sub}</div></div>'
            f'<div class="meta">{meta}</div></div>')


def section(t: str) -> str:
    return f'<div class="section">{esc(t)}</div>'


def fig_layout(fig, h=320, title=None, legend=True):
    fig.update_layout(height=h, showlegend=legend, margin=dict(l=8, r=8, t=48 if title else 16, b=48 if legend else 8))
    if title:
        fig.update_layout(title=dict(text=title))
    return fig


def spark(series, color="#2a78d6", h=56):
    fig = go.Figure(go.Scatter(x=series.index, y=series.values, mode="lines", line=dict(color=color, width=2),
                               hovertemplate="%{x|%d %b %Y}: %{y:,.2f}<extra></extra>"))
    fig.update_layout(height=h, margin=dict(l=0, r=0, t=0, b=0), showlegend=False, hovermode="closest",
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig
