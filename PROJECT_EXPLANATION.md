# Presenter guide & demo script

## One-line pitch
**AsiaPulse AI turns official statistics and live market data into validated forecasts, a transparent risk diagnosis and
ranked, SDG-aligned policy packages for 47 Asian economies — explained by a Qwen agent that can only speak from the evidence.**

## 3-minute demo

**0:00–0:20 · Problem.** "Policy decisions run on data that is months old and scattered across institutions. GDP can grow while
jobs, debt or human capital deteriorate, and a forecast is dangerous if you don't know how reliable it is."

**0:20–0:45 · Overview page.** Show the map and heatmap. "47 economies, 66 official variables, 13 policy areas, including
technology and innovation. Darker means more vulnerable relative to Asian peers."

**0:45–1:15 · Live monitor.** "Official data lags; markets don't. Brent is up sharply this month. That feeds a live nowcast for
this year's growth and a live risk reading. Here are the currency moves across Asia over the last 3 months."

**1:15–1:45 · Country profile.** Pick a showcase economy. Click **Re-run forecast now**. "The ensemble re-fits live. Its confidence
comes from held-out backtests, and here is the IMF projection for comparison. The 12-area diagnosis shows exactly where it
is weak, and the red flags use published thresholds."

**1:45–2:20 · Policy lab.** Open the top package. "Each recommendation has SDG targets, a KPI with a peer target, and Asian
countries that actually achieved it." Click **Simulate this package**, then **Use today's live oil move**. "Growth,
unemployment, debt and risk respond through Okun's law and the IMF debt identity."

**2:20–2:50 · AI analyst.** Ask a suggested question. "Qwen chose which experts to call — here's the trace — and every number in
its answer was verified against the tool outputs. One click exports a policy brief."

**2:50–3:00 · Close.** "From data to decision: what is happening, what will happen, how sure we are, and what to do about it."

## Likely judge questions

**How is this real-time?** Markets (oil, VIX, US yields, dollar, 36 Asian currencies, 9 equity indices) refresh every 15 minutes
and drive a current-year nowcast and a market-stress index. Forecasts can be re-fitted live in about a second.

**Can the forecasts be trusted?** Weights and intervals are learned on 2010-16 forecast origins and evaluated only on held-out
2017-20 origins, including COVID. GDP forecasts beat a naive benchmark; labour ratios mostly don't, and we say so. Each
forecast also shows the IMF projection.

**How do you stop hallucination?** Qwen never computes numbers. It calls tools, and a grounding check matches every number in
its answer to the tool outputs, shown as "x/y numbers verified".

**Why these policy recommendations?** Each one is triggered by a measured vulnerability crossing a published threshold, ranked
by severity, and paired with a KPI target from the peer group and real Asian precedents.

**Why K-Means?** For unsupervised, interpretable profiling. k is chosen by silhouette, and cluster names are generated from
the centroids, so a name always matches its members.

## Limitations to disclose
* Taiwan and DPRK are not covered by the World Bank.
* Vulnerability is relative within Asia.
* The scenario model is a small structural model with editable assumptions, not a forecast.
* Market data uses a public endpoint; cached values are flagged when stale.
