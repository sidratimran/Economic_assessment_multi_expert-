---
title: AsiaPulse AI
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# AsiaPulse AI — Real-time economic assessment & policy intelligence for Asia

AsiaPulse AI turns official statistics and live market data into **validated forecasts, a transparent risk diagnosis, ranked
policy packages and a grounded AI policy analyst** for 47 Asian economies.

| | |
|---|---|
| **Coverage** | 47 economies (Taiwan & DPRK excluded: no World Bank coverage) |
| **Variables** | 66 official variables across 13 policy areas, incl. *Technology & innovation* |
| **Real-time layer** | Brent, VIX, US 10-yr yield, US dollar, gold, 36 Asian currencies, 9 equity indices (refreshed every 15 min) |
| **Forecasts** | Real GDP, GDP per capita, employment, unemployment to 2035 with calibrated 80% intervals |
| **Validation** | Held-out rolling-origin backtests vs a naive benchmark and vs IMF WEO |
| **Policy** | 31 evidence-based red flags → ranked, SDG-tagged policy packages with peer targets and Asian precedents |
| **AI** | Qwen agent with tool calling; every number in its answers is verified against expert outputs |

## The problem

Economic decisions are made on lagging, fragmented data. GDP can grow while jobs, debt or human capital deteriorate; a
forecast without a reliability measure misleads; and dashboards show numbers without saying *what to do*.

## The solution — six experts, one assessment

| Expert | What it does | How |
|---|---|---|
| **Pattern** | Economic profile & peers | K-Means on 12 standardised features, k chosen by silhouette, names generated from centroids |
| **Forecast** | 10-year growth outlook to 2035 | 5-model ensemble: naive, drift, damped Holt, trend **+ a cross-country gradient-boosting model** that learns from all 47 economies (convergence, momentum, demography, structure, institutions). Weights blend each economy's and Asia's backtest record; split-conformal intervals |
| **Validation** | How much to trust it | Weights learned on 2008-13 origins, scored on held-out 2014-20 origins up to a **10-year horizon** (incl. COVID); skill vs naive; IMF benchmark |
| **Risk** | Where it is vulnerable | 12-area percentile index + 31 absolute red flags (IMF, SDG, WHO thresholds) |
| **Policy** | What to do | Curated playbook → ranked packages, SDG targets, KPI peer targets, positive-deviance precedents; scenario simulator |
| **Live** | What is happening *now* | Market signals → live growth nowcast, market-stress index, alerts |
| **Qwen analyst** | Explains it | Plans, calls the experts as tools, writes a brief; grounding check on every number; PDF export |

### Policy areas and variables

Growth · Labour · Macro stability · External resilience · Fiscal space · Social inclusion · **Technology & innovation**
(internet, broadband, mobile, R&D, researchers, patents, high-tech & ICT exports) · Human capital & health · Infrastructure &
access · Financial development · Institutions (WGI) · Climate & environment · Structure & demography.
The full list with codes is in [`src/asiapulse/indicators.py`](src/asiapulse/indicators.py) and on the Methodology page.

### Forecast accuracy (held-out, never seen in training)

| Horizon | Real GDP error (median) | Accuracy | Growth-direction hit rate |
|---|---|---|---|
| 1 year | 2.0% | ≈ 98% | 80% |
| 5 years | 6.9% | ≈ 93% | 86% |
| 10 years | 10.1% | ≈ 90% | 93% |

Adding the cross-country model cut the 10-year GDP error from 11.6% to 10.1% and the 5-year error from 8.0% to 6.9%
(`python pipeline/compare_models.py` reproduces the before/after comparison).

### Real-time prediction

* **Nowcast** for the current year = mean(AsiaPulse ensemble, IMF WEO) + live oil adjustment (Policy-Lab elasticities × Brent's
  30-day average vs its prior 12 months × share of year remaining).
* **Market stress (0–100)** from currency depreciation and volatility, equity drawdown, oil exposure and VIX.
* **Live risk** = 70% structural vulnerability + 30% market stress.
* **Re-run forecast now** re-fits the ensemble live in the app (~1 s) with the learned weights.

### Scenario simulator

Shocks (global demand, oil, remittances) and levers (fiscal consolidation, public investment, female labour participation,
digital adoption, interest rates) flow through: growth multipliers → **Okun's law estimated per country** (partially pooled)
→ **IMF debt-dynamics identity** with each country's IMF-implied interest rate → re-scored risk. All assumptions are editable.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python pipeline/run_pipeline.py   # ~90 s; add --refresh to re-download all source data
python run.py                     # web dashboard → http://localhost:8000
python -m pytest tests -q         # unit tests
```

The main UI is a custom web dashboard (`web/` + FastAPI in `api/server.py`): dark/light theme, Ctrl+K country search,
clickable interactive map, live market ticker, auto-refreshing live monitor, instant scenario sliders and a streaming AI
analyst with a visible tool-call trace. A simpler Streamlit version remains available via `streamlit run app.py`.

Processed outputs are committed in `data/processed/`, so the app also runs without re-running the pipeline.

### AI configuration (`.env`)

```
DASHSCOPE_API_KEY=your-key
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1   # Alibaba Cloud Model Studio
QWEN_MODEL=qwen-plus
QWEN_MAX_TOKENS=900
```

Any OpenAI-compatible endpoint serving Qwen works (e.g. Groq: `https://api.groq.com/openai/v1`, `qwen/qwen3.8-27b`).
Without a key, a deterministic analyst calls the same tools so the product always works. Never commit `.env`.

## Project layout

```
app.py                       Streamlit app (7 pages)
pipeline/run_pipeline.py     fetch → panel → backtest → forecast → cluster → risk → artefacts
src/asiapulse/
  indicators.py              variable registry (single source of truth)
  sources/                   World Bank API, IMF WEO via DBnomics
  live.py                    real-time market layer, nowcast, stress index
  models/                    forecast, backtest, cluster, risk, scenario
  policy/engine.py           policy playbook & recommendation engine
  agents/                    Qwen tool-calling orchestrator, tools, grounding check
  report/brief.py            PDF / Markdown policy brief
  ui/theme.py                visual system (validated colour-blind-safe palette)
tests/                       unit tests
data/processed/              pipeline outputs used by the app
data/legacy/                 original prototype data (not used)
```

## Responsible AI & limitations

* The LLM never computes numbers; it explains tool outputs and every number is verified.
* Vulnerability is **relative within Asia**; "Low" is not an absolute all-clear.
* Each value keeps its year; stale values are treated as missing, never imputed for scoring.
* Labour-market ratios are hard to forecast better than "no change"; we report this openly.
* Market data comes from a public endpoint without an SLA; cached values are flagged as stale.
* Scenario outputs are simulations with editable assumptions, not forecasts. Decision support, not financial advice.
