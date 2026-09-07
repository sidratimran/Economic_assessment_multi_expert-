# Economic_assessment_multi_expert-
Built a K-Means clustering and multi-model forecasting pipeline covering 50+ Aisian countries, projecting economic indicators through 2030
# Economic Assessment Multi-Expert — AsiaPulse AI

Hackathon-ready economic intelligence prototype for Asian economies.

## What it does

The application turns prepared multi-country economic data into five cooperating expert views:

1. **Pattern Expert** — K-Means economic profile and similar economies.
2. **Forecast Expert** — GDP and employment projections.
3. **Validation Expert** — historical backtesting and forecast-confidence labels.
4. **Risk Expert** — transparent risk labels and risk flags.
5. **Qwen Economic Analyst** — Alibaba Cloud Model Studio explanation grounded only in the structured outputs of the first four experts.

The UI includes Executive Assessment, Country Intelligence, country comparison, methodology/validation evidence, and a clearly labelled Scenario Lab prototype.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The deterministic app works without an LLM key. In that mode, the AI section shows a grounded fallback summary.

## Enable Alibaba Cloud Qwen

Set these environment variables before starting Streamlit:

```bash
DASHSCOPE_API_KEY=YOUR_KEY
QWEN_BASE_URL=YOUR_MODEL_STUDIO_OPENAI_COMPATIBLE_BASE_URL
QWEN_MODEL=qwen-plus
```

The API key and base URL must belong to compatible Alibaba Cloud Model Studio regions. Do **not** hard-code or commit the key.

## Competition demo flow

1. Open **Executive Assessment** with a showcase country.
2. Explain the five experts in 20–30 seconds.
3. Generate a grounded Qwen assessment.
4. Open **Country Intelligence** and show forecast + historical employment + confidence.
5. Open **Compare Economies** and compare 2–3 countries.
6. Open **Model & Methodology** only if judges ask about validation or Alibaba Cloud architecture.
7. Use **Scenario Lab** as an optional wow feature; explicitly say it is hypothetical.

## Important data note

The supplied prepared dataset has GDP forecasts for fewer economies than employment forecasts. The app intentionally displays `N/A` rather than fabricating missing GDP values. Before final submission, fill missing GDP histories/forecasts only from a verified source and rerun the forecasting pipeline.

## Responsible AI

- Qwen receives structured model outputs rather than being asked to invent economic facts.
- Forecasts are labelled as forecasts.
- Missing values remain missing.
- Confidence labels are based on historical MAPE.
- CDI is described as a project-defined composite indicator.
- Scenario Lab is labelled hypothetical.
