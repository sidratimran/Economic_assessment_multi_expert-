/* AsiaPulse AI — single-page dashboard (vanilla JS + ECharts). */
"use strict";

// ------------------------------------------------------------------ utilities
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const API = (p) => fetch(p).then((r) => { if (!r.ok) throw new Error(`${r.status} ${p}`); return r.json(); });
const POST = (p, b) => fetch(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) })
  .then((r) => { if (!r.ok) throw new Error(`${r.status} ${p}`); return r; });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNum = (v) => typeof v === "number" && isFinite(v);
const f = (v, d = 1, suf = "", pre = "") => (isNum(v) ? `${pre}${v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}${suf}` : "—");
const sgn = (v, d = 1, suf = "") => (isNum(v) ? `${v > 0 ? "+" : ""}${f(v, d, suf)}` : "—");
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const chip = (l) => `<span class="chip ${esc(l)}">${{ Low: "●", Moderate: "▲", Elevated: "◆", High: "■" }[l] || "○"} ${esc(l)}</span>`;

const state = {
  meta: null, iso: localStorage.getItem("ap-iso") || "PAK", view: "overview", charts: [], timers: [], cache: {},
  levers: {}, chat: {}, compare: null, mapMetric: "score", rankMode: "vuln", heatSort: "score", fanKey: "gdp_real",
  liveTab: "fx", scenTab: "growth", geoReady: false,
};

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast"; t.innerHTML = msg; $("#toasts").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = ".4s"; setTimeout(() => t.remove(), 400); }, 3800);
}
async function cached(url) { if (!state.cache[url]) state.cache[url] = await API(url); return state.cache[url]; }
function countUp(el, to, d = 0, pre = "", suf = "") {
  if (!el) return;
  if (!isNum(to)) { el.textContent = "—"; return; }
  const t0 = performance.now(), dur = 900;
  const step = (t) => {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = f(to * e, d, suf, pre);
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
const name = (iso) => (state.meta.countries.find((c) => c.iso3 === iso) || {}).name || iso;

// ------------------------------------------------------------------ theme & charts
const PAL = {
  dark: ["#4f8cff", "#f97316", "#22d3ee", "#f5b301", "#e879a6", "#22c55e", "#a78bfa", "#ef4444"],
  light: ["#2563eb", "#ea580c", "#0891b2", "#ca8a04", "#db2777", "#16a34a", "#7c3aed", "#dc2626"],
};
const RAMP = {
  dark: { score: ["#16223a", "#1e3a6e", "#2d5fb3", "#4f8cff", "#a5c4ff"], cagr: ["#10302e", "#0f5d57", "#14918a", "#22d3ee", "#a5f3fc"], flags: ["#2a2416", "#5c4710", "#a37a07", "#f5b301", "#fde68a"] },
  light: { score: ["#e6eefc", "#b9cff7", "#6f9cea", "#2f6fd6", "#173f8a"], cagr: ["#e3f6f8", "#a7e3ea", "#4fc0cf", "#0e8fa3", "#0b5563"], flags: ["#fdf5e2", "#f6dc9c", "#e3ad3c", "#b7791f", "#7a4f10"] },
};
const theme = () => document.documentElement.dataset.theme || "dark";
const C = () => PAL[theme()];
function setThemeIcon() {
  $("#themeBtn").innerHTML = theme() === "dark"
    ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
    : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/></svg>';
}
function toggleTheme() {
  document.documentElement.dataset.theme = theme() === "dark" ? "light" : "dark";
  try { localStorage.setItem("ap-theme", theme()); } catch (e) {}
  setThemeIcon(); render();
}
function base() {
  return {
    color: C(), backgroundColor: "transparent", animationDuration: 900, animationEasing: "cubicOut",
    textStyle: { fontFamily: "Inter, system-ui, sans-serif", color: css("--chart-text") },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      backgroundColor: css("--surface"), borderColor: css("--border-strong"), borderWidth: 1, padding: [8, 12],
      textStyle: { color: css("--text"), fontSize: 12 }, extraCssText: "box-shadow:0 10px 30px rgba(0,0,0,.25);border-radius:10px;",
    },
    legend: { top: 0, left: 0, icon: "roundRect", itemWidth: 12, itemHeight: 4, textStyle: { color: css("--text-2") } },
  };
}
const axis = (o = {}) => ({
  axisLine: { lineStyle: { color: css("--border-strong") } }, axisTick: { show: false },
  splitLine: { lineStyle: { color: css("--grid") } }, axisLabel: { color: css("--muted") }, ...o,
});
function chart(el, opt) {
  if (!el) return null;
  const c = echarts.init(el, null, { renderer: "canvas" });
  c.setOption(Object.assign(base(), opt));
  state.charts.push(c);
  return c;
}
window.addEventListener("resize", debounce(() => state.charts.forEach((c) => c.resize()), 120));
function disposeAll() { state.charts.forEach((c) => c.dispose()); state.charts = []; state.timers.forEach(clearInterval); state.timers = []; }
function fan(hist, fc, color) {
  const last = hist.length ? hist[hist.length - 1] : null;
  const lower = fc.map((r) => [r[0], r[2]]), width = fc.map((r) => [r[0], r[3] - r[2]]);
  const fline = last ? [[last[0], last[1]], ...fc.map((r) => [r[0], r[1]])] : fc.map((r) => [r[0], r[1]]);
  return [
    { name: "lower", type: "line", data: lower, stack: "band", symbol: "none", lineStyle: { opacity: 0 }, tooltip: { show: false }, silent: true },
    { name: "80% interval", type: "line", data: width, stack: "band", symbol: "none", lineStyle: { opacity: 0 },
      areaStyle: { color: color, opacity: 0.16 }, tooltip: { show: false }, silent: true },
    { name: "Forecast", type: "line", data: fline, symbol: "circle", symbolSize: 5, showSymbol: false, lineStyle: { width: 2.5, type: "dashed", color }, itemStyle: { color } },
    { name: "Actual", type: "line", data: hist, symbol: "circle", symbolSize: 5, showSymbol: false, lineStyle: { width: 2.5, color: css("--text") }, itemStyle: { color: css("--text") } },
  ];
}
function fanTooltip(unit) {
  return {
    trigger: "axis", formatter: (ps) => {
      const yr = ps[0].axisValue;
      const get = (n) => ps.find((p) => p.seriesName === n);
      const a = get("Actual"), fc = get("Forecast"), lo = get("lower"), w = get("80% interval");
      let s = `<b>${yr}</b>`;
      if (a && isNum(a.value[1])) s += `<br>Actual: <b>${f(a.value[1], 2)}</b> ${unit}`;
      if (fc && isNum(fc.value[1]) && !(a && isNum(a.value[1]))) s += `<br>Forecast: <b>${f(fc.value[1], 2)}</b> ${unit}`;
      if (lo && w && isNum(lo.value[1])) s += `<br><span style="opacity:.7">80% range ${f(lo.value[1], 2)} – ${f(lo.value[1] + w.value[1], 2)}</span>`;
      return s;
    },
  };
}

// ------------------------------------------------------------------ shell: nav, ticker, palette
const ICONS = {
  outlook: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/></svg>',
  overview: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="9" rx="2"/><rect x="14" y="3" width="7" height="5" rx="2"/><rect x="14" y="12" width="7" height="9" rx="2"/><rect x="3" y="16" width="7" height="5" rx="2"/></svg>',
  live: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg>',
  country: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
  policy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>',
  ai: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>',
  compare: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 3v18M16 3v18M3 8h5M16 16h5M3 16h5M16 8h5"/></svg>',
  method: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2zM4 5v16M8 7h7M8 11h7"/></svg>',
};
const VIEWS = [["outlook", "Growth outlook 2035"], ["overview", "Risk overview"], ["live", "Live monitor"], ["country", "Country profile"], ["policy", "Policy lab"],
  ["ai", "AI analyst"], ["compare", "Compare"], ["method", "Methodology"]];
function buildRail() {
  $("#rail").innerHTML = VIEWS.map(([k, l]) => `<div class="nav" data-v="${k}" onclick="go('${k}')">${ICONS[k]}<span>${l}</span></div>`).join("")
    + `<div class="spacer"></div><div class="nav" onclick="openPalette()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg><span>Search (Ctrl K)</span></div>`;
}
function go(v, iso) {
  if (iso) setIso(iso, false);
  location.hash = `#/${v}`;
}
function setIso(iso, rerender = true) {
  state.iso = iso; try { localStorage.setItem("ap-iso", iso); } catch (e) {}
  $("#curName").textContent = name(iso);
  if (rerender) render();
}
window.addEventListener("hashchange", () => render());

async function refreshTicker() {
  try {
    const g = await API("/api/live/global");
    state.global = g;
    const items = g.items.map((i) => `<span class="tk">${esc(i.label)}<b class="num">${f(i.price, i.price > 1000 ? 0 : 2)}</b><span class="${(i.chg_1m || 0) >= 0 ? "up" : "down"}">${(i.chg_1m || 0) >= 0 ? "▲" : "▼"} ${sgn(i.chg_1m, 1, "%")} 1m</span></span>`).join("");
    $("#ticker").innerHTML = items + items;
    const stale = g.items.some((i) => i.stale);
    $("#livePill").innerHTML = `<span class="dot"></span>${stale ? "CACHED" : "LIVE"}`;
  } catch (e) { $("#livePill").innerHTML = '<span class="dot"></span>OFFLINE'; }
}

let palSel = 0;
function openPalette() { $("#overlay").classList.add("show"); $("#palInput").value = ""; palSel = 0; drawPalette(); setTimeout(() => $("#palInput").focus(), 30); }
function closePalette() { $("#overlay").classList.remove("show"); }
function palItems() {
  const q = $("#palInput").value.toLowerCase();
  return state.meta.countries.filter((c) => !q || c.name.toLowerCase().includes(q) || c.iso3.toLowerCase().includes(q) || c.region.toLowerCase().includes(q));
}
function drawPalette() {
  const items = palItems(); palSel = Math.min(palSel, Math.max(items.length - 1, 0));
  $("#palList").innerHTML = items.map((c, i) => `<div class="pal-item ${i === palSel ? "sel" : ""}" data-iso="${c.iso3}">
    <div><b>${esc(c.name)}</b> <small>· ${esc(c.region)} · ${esc(c.profile)}</small></div><span class="num">${f(c.score, 1)}</span>${chip(c.label)}</div>`).join("")
    || '<div class="pal-item"><small>No match</small></div>';
  $$(".pal-item[data-iso]").forEach((el) => el.onclick = () => pickPalette(el.dataset.iso));
  const sel = $(".pal-item.sel"); if (sel) sel.scrollIntoView({ block: "nearest" });
}
function pickPalette(iso) {
  closePalette();
  const v = location.hash.replace("#/", "") || "outlook";
  setIso(iso, false);
  if (["outlook", "overview", "method", "compare"].includes(v)) go("country"); else render();
}
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); }
  if (!$("#overlay").classList.contains("show")) return;
  if (e.key === "Escape") closePalette();
  if (e.key === "ArrowDown") { palSel++; drawPalette(); e.preventDefault(); }
  if (e.key === "ArrowUp") { palSel = Math.max(0, palSel - 1); drawPalette(); e.preventDefault(); }
  if (e.key === "Enter") { const it = palItems()[palSel]; if (it) pickPalette(it.iso3); }
});
$("#palInput").addEventListener("input", () => { palSel = 0; drawPalette(); });

// ------------------------------------------------------------------ render loop
async function render() {
  const v = (location.hash.replace("#/", "") || "outlook").split("/")[0];
  state.view = v;
  $$(".nav[data-v]").forEach((n) => n.classList.toggle("active", n.dataset.v === v));
  disposeAll();
  const main = $("#main");
  main.innerHTML = `<div class="view"><div class="skel" style="height:90px;margin-bottom:16px"></div><div class="grid"><div class="skel c8" style="height:420px"></div><div class="skel c4" style="height:420px"></div></div></div>`;
  try {
    await ({ outlook: vOutlook, overview: vOverview, live: vLive, country: vCountry, policy: vPolicy, ai: vAI, compare: vCompare, method: vMethod }[v] || vOutlook)(main);
  } catch (e) {
    console.error(e);
    main.innerHTML = `<div class="card"><h2>Something went wrong</h2><p class="sub">${esc(e.message)}</p><button class="btn" onclick="render()">Retry</button></div>`;
  }
}
const head = (eyebrow, title, sub, right = "") =>
  `<div class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><div class="sub">${sub}</div></div><div class="meta">${right}</div></div>`;
const kpi = (id, lab, icon, note = "") => `<div class="kpi"><div class="lab"><span class="ico">${icon}</span>${esc(lab)}</div><div class="val num" id="${id}">—</div><div class="knote">${note}</div></div>`;

// ================================================================== GROWTH OUTLOOK 2035 (core agenda)
async function vOutlook(main) {
  const d = await cached("/api/outlook");
  const s = d.summary, rows = d.rows.filter((r) => isNum(r.cagr));
  state.olRegion = state.olRegion || "All";
  main.innerHTML = `<div class="view">
    ${head(`Mission · 10-year economic growth forecast ${d.base_year} → ${d.end_year}`, `Where will Asia's economies be in ${d.end_year}?`,
      `AsiaPulse AI predicts real GDP growth over the next 10 years for ${s.n} Asian economies — with validated accuracy, 80% uncertainty ranges and the IMF as an external benchmark.`,
      `Forecast horizon ${d.base_year}–${d.end_year}<br>Real GDP, constant 2015 US$`)}
    <div class="kpis">
      ${kpi("o1", `Asia growth ${d.base_year}–${d.end_year}`, "↗", "average real GDP growth per year")}
      ${kpi("o2", `Asia GDP in ${d.end_year}`, "$", `from $${f(s.asia_base_tn, 1)} tn in ${d.base_year}`)}
      ${kpi("o3", "Fastest-growing economy", "🚀", "")}
      ${kpi("o4", "Economies growing ≥ 5% / yr", "⚡", `${s.contracting} projected to contract`)}
      ${kpi("o5", "Largest GDP gain", "▲", "")}
    </div>
    <div class="grid">
      <div class="card c8"><div class="card-head"><h2>Predicted average annual growth, ${d.base_year}–${d.end_year}</h2>
        <div class="seg" id="olSeg">${["All", "East Asia", "Southeast Asia", "South Asia", "Central Asia", "West Asia"].map((r) => `<button data-r="${r}">${r.replace(" Asia", "")}</button>`).join("")}</div></div>
        <div class="hint" style="margin-bottom:6px">Bar = AsiaPulse forecast · whisker = 80% range · ◆ = IMF WEO 2026-30 · click a bar to open the country</div>
        <div id="olBars" class="chart"></div></div>
      <div class="c4">
        <div class="card"><div class="card-head"><h2>Asia's real GDP (US$ tn)</h2></div><div id="olAgg" class="chart short"></div></div>
        <div class="card"><div class="card-head"><h2>Accelerating vs slowing</h2><span class="hint">vs last 10 years</span></div><div id="olQuad" class="chart"></div></div>
      </div>
      <div class="card c12"><div class="card-head"><h2>Full 10-year forecast table</h2><input class="input" id="olQ" placeholder="Filter…" style="width:240px"></div><div class="tbl-wrap" id="olTbl"></div></div>
    </div><div class="foot">Forecasts are statistical projections with stated uncertainty — decision support, not financial advice.</div></div>`;
  countUp($("#o1"), s.asia_cagr, 1, "", "%"); countUp($("#o2"), s.asia_end_tn, 1, "$", " tn");
  $("#o3").textContent = s.fastest.name; $("#o3").nextElementSibling.textContent = `${f(s.fastest.cagr, 1)}% a year`;
  countUp($("#o4"), s.above_5); $("#o5").textContent = s.biggest_gain.name; $("#o5").nextElementSibling.textContent = `+$${f(s.biggest_gain.add_bn / 1000, 1)} tn by ${d.end_year}`;

  const barsC = chart($("#olBars"), {});
  const drawBars = () => {
    const R = state.olRegion;
    $$("#olSeg button").forEach((b) => b.classList.toggle("on", b.dataset.r === R));
    const list = rows.filter((r) => R === "All" || r.region === R).sort((a, b) => a.cagr - b.cagr);
    $("#olBars").style.height = `${Math.max(320, list.length * 22 + 60)}px`; barsC.resize();
    barsC.setOption({
      grid: { left: 8, right: 40, top: 26, bottom: 8, containLabel: true }, legend: { top: 0, data: ["AsiaPulse forecast", "IMF WEO 2026-30"] },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (p) => { const r = list[p[0].dataIndex];
        return `<b>${esc(r.name)}</b> · ${esc(r.region)}<br>Forecast <b>${f(r.cagr, 2)}%</b>/yr (80%: ${f(r.cagr_lo, 1)}–${f(r.cagr_hi, 1)}%)<br>GDP $${f(r.gdp_base_bn, 0)} bn → <b>$${f(r.gdp_end_bn, 0)} bn</b> (×${f(r.multiple, 2)})<br>IMF 2026-30: ${f(r.imf_2026_30, 1, "%")} · last 10 yrs: ${f(r.hist_10y, 1, "%")}<br>Confidence: <b>${esc(r.confidence)}</b>`; } },
      xAxis: axis({ type: "value", axisLabel: { formatter: "{value}%", color: css("--muted") } }),
      yAxis: axis({ type: "category", data: list.map((r) => r.name), axisLabel: { color: css("--text-2"), fontSize: 11 }, splitLine: { show: false } }),
      series: [
        { name: "AsiaPulse forecast", type: "bar", barWidth: 12, data: list.map((r) => ({ value: +r.cagr.toFixed(2), itemStyle: { color: r.cagr < 0 ? css("--critical") : C()[0], borderRadius: 6 } })),
          label: { show: true, position: "right", distance: 26, color: css("--text-2"), fontSize: 10, formatter: (p) => `${f(p.value, 1)}%` } },
        { name: "80% range", type: "custom", data: list.map((r, i) => [i, r.cagr_lo, r.cagr_hi]), z: 5, tooltip: { show: false },
          renderItem: (params, api) => { const y = api.coord([0, api.value(0)])[1], lo = api.coord([api.value(1), 0])[0], hi = api.coord([api.value(2), 0])[0];
            const st = { stroke: css("--text"), lineWidth: 1.4, opacity: 0.7 };
            return { type: "group", children: [{ type: "line", shape: { x1: lo, y1: y, x2: hi, y2: y }, style: st }, { type: "line", shape: { x1: lo, y1: y - 4, x2: lo, y2: y + 4 }, style: st }, { type: "line", shape: { x1: hi, y1: y - 4, x2: hi, y2: y + 4 }, style: st }] }; } },
        { name: "IMF WEO 2026-30", type: "scatter", symbol: "diamond", symbolSize: 9, z: 6, data: list.map((r) => (isNum(r.imf_2026_30) ? +r.imf_2026_30.toFixed(2) : null)), itemStyle: { color: C()[1] } },
      ],
    }, true);
    barsC.off("click"); barsC.on("click", (p) => go("country", list[p.dataIndex].iso3));
  };
  drawBars();
  $$("#olSeg button").forEach((b) => b.onclick = () => { state.olRegion = b.dataset.r; drawBars(); });

  const agg = d.aggregate, by = d.base_year;
  chart($("#olAgg"), {
    grid: { left: 8, right: 12, top: 16, bottom: 8, containLabel: true }, tooltip: { trigger: "axis", valueFormatter: (v) => `$${f(v, 1)} tn` },
    xAxis: axis({ type: "category", data: agg.map((a) => a[0]), boundaryGap: false, splitLine: { show: false } }), yAxis: axis({ type: "value", scale: true }),
    series: [{ name: "Actual", type: "line", data: agg.map((a) => (a[0] <= by ? a[1] : null)), symbol: "none", lineStyle: { width: 2.5, color: css("--text") } },
      { name: "Forecast", type: "line", data: agg.map((a) => (a[0] >= by ? a[1] : null)), symbol: "none", lineStyle: { width: 2.5, type: "dashed", color: C()[0] },
        areaStyle: { color: C()[0], opacity: 0.12 } }],
  });
  const q = rows.filter((r) => isNum(r.hist_10y));
  chart($("#olQuad"), {
    grid: { left: 8, right: 16, top: 16, bottom: 26, containLabel: true },
    tooltip: { formatter: (p) => `<b>${esc(p.data[2])}</b><br>Last 10 yrs ${f(p.data[0], 1)}% → next 10 yrs ${f(p.data[1], 1)}%` },
    xAxis: axis({ type: "value", name: "past 10y %", nameLocation: "middle", nameGap: 22, nameTextStyle: { color: css("--muted") } }),
    yAxis: axis({ type: "value", name: "next 10y %", nameTextStyle: { color: css("--muted") } }),
    series: [{ type: "scatter", data: q.map((r) => [r.hist_10y, r.cagr, r.name, r.iso3]), symbolSize: 9,
      itemStyle: { color: (p) => (p.data[1] >= p.data[0] ? css("--good") : C()[1]), opacity: 0.85 },
      markLine: { silent: true, symbol: "none", lineStyle: { type: "dashed", color: css("--muted") }, label: { show: false },
        data: [[{ coord: [-3, -3] }, { coord: [10, 10] }]] } }],
  }).on("click", (p) => go("country", p.data[3]));

  let sortK = "cagr", asc = false;
  const cols = [["name", "Economy"], ["region", "Region"], ["gdp_base_bn", `GDP ${by} ($bn)`], ["gdp_end_bn", `GDP ${d.end_year} ($bn)`], ["cagr", "Growth / yr"],
    ["cagr_lo", "80% low"], ["cagr_hi", "80% high"], ["pc_cagr", "Per-capita growth"], ["hist_10y", "Last 10 yrs"], ["imf_2026_30", "IMF 2026-30"], ["confidence", "Confidence"], ["risk_label", "Risk"]];
  const drawTbl = () => {
    const qq = ($("#olQ").value || "").toLowerCase();
    const list = rows.filter((r) => !qq || `${r.name} ${r.region}`.toLowerCase().includes(qq))
      .sort((a, b) => { const x = a[sortK], y = b[sortK]; const c = typeof x === "string" ? x.localeCompare(y) : (x ?? -1e9) - (y ?? -1e9); return asc ? c : -c; });
    $("#olTbl").innerHTML = `<table><thead><tr>${cols.map(([k, l]) => `<th data-k="${k}">${l}${sortK === k ? (asc ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead><tbody>${list.map((r) => `<tr class="click" data-iso="${r.iso3}">
      <td><b>${esc(r.name)}</b></td><td>${esc(r.region)}</td><td class="num">${f(r.gdp_base_bn, 0)}</td><td class="num"><b>${f(r.gdp_end_bn, 0)}</b></td>
      <td class="num"><b class="${r.cagr >= 0 ? "up" : "down"}">${f(r.cagr, 2, "%")}</b></td><td class="num">${f(r.cagr_lo, 1, "%")}</td><td class="num">${f(r.cagr_hi, 1, "%")}</td>
      <td class="num">${f(r.pc_cagr, 1, "%")}</td><td class="num">${f(r.hist_10y, 1, "%")}</td><td class="num">${f(r.imf_2026_30, 1, "%")}</td><td>${esc(r.confidence)}</td><td>${chip(r.risk_label)}</td></tr>`).join("")}</tbody></table>`;
    $$("#olTbl th").forEach((th) => th.onclick = () => { if (sortK === th.dataset.k) asc = !asc; else { sortK = th.dataset.k; asc = false; } drawTbl(); });
    $$("#olTbl tr.click").forEach((tr) => tr.onclick = () => go("country", tr.dataset.iso));
  };
  drawTbl(); $("#olQ").oninput = drawTbl;
}

// ================================================================== OVERVIEW
async function vOverview(main) {
  const [d] = await Promise.all([cached("/api/overview"), ensureGeo()]);
  const k = d.kpis, m = state.meta;
  main.innerHTML = `<div class="view">
    ${head("Risk overview", "Where are Asia's economies vulnerable?",
      `${m.economies} economies · ${m.variables} official variables · 13 policy areas including technology & innovation. Click any country to drill in.`,
      `Official data ${esc(m.generated_utc)} UTC<br>Reference year ${m.reference_year} · horizon ${m.forecast_end}`)}
    <div class="kpis">
      ${kpi("k1", "Economies assessed", "🌏", "Taiwan & DPRK lack World Bank data")}
      ${kpi("k2", "Variables tracked", "▦", "World Bank WDI/WGI · IMF WEO")}
      ${kpi("k3", "High vulnerability", "■", `<span id="k3n"></span>`)}
      ${kpi("k4", "Median growth outlook", "↗", "real GDP CAGR to 2035")}
      ${kpi("k5", "Red flags raised", "⚑", "evidence-based thresholds")}
    </div>
    <div class="grid">
      <div class="card c8"><div class="card-head"><h2>Interactive map</h2>
        <div class="seg" id="mapSeg"><button data-m="score">Vulnerability</button><button data-m="cagr">Growth outlook</button><button data-m="flags">Red flags</button></div></div>
        <div id="map" class="chart tall"></div><div class="card-head" style="margin:6px 0 0"><span class="hint">Scroll to zoom · drag to pan · click a country to open its profile</span></div></div>
      <div class="card c4"><div class="card-head"><h2>Leaderboard</h2>
        <div class="seg" id="rankSeg"><button data-r="vuln">Vulnerable</button><button data-r="res">Resilient</button><button data-r="grow">Growth</button></div></div>
        <div id="rankList"></div></div>
      <div class="card c12"><div class="card-head"><h2>Vulnerability by policy area</h2>
        <div style="display:flex;gap:10px;align-items:center"><span class="hint">Sort by</span><select class="input" id="heatSort"></select></div></div>
        <div id="heat" class="chart tall"></div></div>
      <div class="card c7"><div class="card-head"><h2>Economic profiles</h2><span class="hint">K-Means · bubble size = population</span></div><div id="clus" class="chart tall"></div></div>
      <div class="card c5"><div class="card-head"><h2>Profile groups</h2><span class="hint">silhouette ${f(d.clusters.silhouette, 3)} · k=${d.clusters.k}</span></div><div id="clusList"></div></div>
      <div class="card c12"><div class="card-head"><h2>Full ranking</h2><input class="input" id="rankSearch" placeholder="Filter economies, regions, profiles…" style="width:280px"></div><div class="tbl-wrap" id="rankTbl"></div></div>
    </div><div class="foot">Decision support, not financial advice · Sources: World Bank, IMF, Yahoo Finance</div></div>`;
  countUp($("#k1"), k.economies); countUp($("#k2"), k.variables); countUp($("#k3"), k.high);
  $("#k3n").textContent = `${f(k.high_pop_m, 0)} million people`; countUp($("#k4"), k.median_cagr, 1, "", "%"); countUp($("#k5"), k.flags);

  const rows = d.rows, byIso = Object.fromEntries(rows.map((r) => [r.iso3, r]));
  // map
  const mapC = chart($("#map"), {});
  const drawMap = () => {
    const met = state.mapMetric, R = RAMP[theme()][met];
    const val = (r) => (met === "score" ? r.score : met === "cagr" ? r.cagr : r.flags);
    const vals = rows.map(val).filter(isNum);
    const lab = { score: "Vulnerability (0–100)", cagr: "Growth outlook (% / yr)", flags: "Red flags" }[met];
    mapC.setOption({
      tooltip: {
        trigger: "item", formatter: (p) => {
          const r = byIso[p.name]; if (!r) return "";
          return `<b>${esc(r.name)}</b> ${chip(r.label)}<br><span style="opacity:.75">${esc(r.profile)}</span><br>
            Vulnerability <b>${f(r.score, 1)}</b> · rank ${r.rank}/${rows.length}<br>Growth outlook <b>${f(r.cagr, 1, "%")}</b> · red flags <b>${r.flags}</b>`;
        },
      },
      visualMap: { min: Math.min(...vals), max: Math.max(...vals), calculable: true, orient: "horizontal", left: 10, bottom: 6, itemWidth: 12, itemHeight: 160,
        text: [met === "cagr" ? "faster" : "more", met === "cagr" ? "slower" : "less"], textStyle: { color: css("--muted") }, inRange: { color: R }, seriesIndex: [0, 1] },
      geo: { map: "world", roam: true, center: [92, 27], zoom: 2.9, scaleLimit: { min: 1.5, max: 12 }, silent: false,
        itemStyle: { areaColor: css("--surface-3"), borderColor: css("--bg"), borderWidth: 0.6 },
        emphasis: { label: { show: false }, itemStyle: { areaColor: css("--accent"), shadowBlur: 12, shadowColor: "rgba(0,0,0,.4)" } },
        select: { disabled: true } },
      series: [
        { type: "map", geoIndex: 0, data: rows.map((r) => ({ name: r.iso3, value: val(r) })) },
        { type: "effectScatter", coordinateSystem: "geo", symbolSize: 10, rippleEffect: { scale: 3, brushType: "stroke" },
          data: Object.entries(d.small_states).filter(([i]) => byIso[i]).map(([i, ll]) => ({ name: i, value: [...ll, val(byIso[i])] })) },
      ],
    }, true);
    $$("#mapSeg button").forEach((b) => b.classList.toggle("on", b.dataset.m === met));
  };
  drawMap();
  mapC.on("click", (p) => { if (byIso[p.name]) go("country", p.name); });
  $$("#mapSeg button").forEach((b) => b.onclick = () => { state.mapMetric = b.dataset.m; drawMap(); });

  // leaderboard
  const drawRank = () => {
    const mode = state.rankMode;
    let list = [...rows];
    if (mode === "vuln") list.sort((a, b) => b.score - a.score);
    if (mode === "res") list.sort((a, b) => a.score - b.score);
    if (mode === "grow") list = list.filter((r) => isNum(r.cagr)).sort((a, b) => b.cagr - a.cagr);
    const top = list.slice(0, 10), mx = mode === "grow" ? Math.max(...top.map((r) => r.cagr)) : 100;
    $("#rankList").innerHTML = top.map((r, i) => `<div class="rank-row" data-iso="${r.iso3}"><span class="pos">${i + 1}</span>
      <span><b>${esc(r.name)}</b><br><small style="color:var(--muted)">${esc(r.region)}</small></span>
      <div class="bar"><i data-w="${Math.max(4, ((mode === "grow" ? r.cagr : r.score) / mx) * 100)}"></i></div>
      <span class="num" style="text-align:right">${mode === "grow" ? f(r.cagr, 1, "%") : f(r.score, 1)}<br>${chip(r.label)}</span></div>`).join("");
    requestAnimationFrame(() => $$("#rankList .bar i").forEach((i) => i.style.width = i.dataset.w + "%"));
    $$("#rankList .rank-row").forEach((el) => el.onclick = () => go("country", el.dataset.iso));
    $$("#rankSeg button").forEach((b) => b.classList.toggle("on", b.dataset.r === mode));
  };
  drawRank();
  $$("#rankSeg button").forEach((b) => b.onclick = () => { state.rankMode = b.dataset.r; drawRank(); });

  // heatmap
  const pillars = m.pillars;
  $("#heatSort").innerHTML = `<option value="score">Overall vulnerability</option>` + pillars.map((p) => `<option value="${p.key}">${esc(p.label)}</option>`).join("");
  $("#heatSort").value = state.heatSort;
  const heatC = chart($("#heat"), {});
  const drawHeat = () => {
    const s = state.heatSort;
    const order = [...rows].sort((a, b) => (s === "score" ? b.score - a.score : (b.pillars[s] ?? -1) - (a.pillars[s] ?? -1)));
    const data = [];
    order.forEach((r, x) => pillars.forEach((p, y) => data.push([x, y, isNum(r.pillars[p.key]) ? +r.pillars[p.key].toFixed(0) : "-"])));
    heatC.setOption({
      grid: { left: 8, right: 70, top: 8, bottom: 8, containLabel: true },
      tooltip: { formatter: (p) => `<b>${esc(order[p.value[0]].name)}</b><br>${esc(pillars[p.value[1]].label)}: <b>${p.value[2]}</b>/100` },
      xAxis: { type: "category", data: order.map((r) => r.name), axisLabel: { rotate: 60, fontSize: 10, color: css("--muted") }, axisLine: { show: false }, axisTick: { show: false } },
      yAxis: { type: "category", data: pillars.map((p) => p.label), axisLabel: { color: css("--text-2") }, axisLine: { show: false }, axisTick: { show: false } },
      visualMap: { min: 0, max: 100, calculable: true, orient: "vertical", right: 0, top: "middle", itemHeight: 200, inRange: { color: RAMP[theme()].score }, textStyle: { color: css("--muted") } },
      series: [{ type: "heatmap", data, itemStyle: { borderColor: css("--surface"), borderWidth: 2, borderRadius: 3 },
        emphasis: { itemStyle: { borderColor: css("--text"), borderWidth: 1 } } }],
    }, true);
    heatC.off("click"); heatC.on("click", (p) => go("country", order[p.value[0]].iso3));
  };
  drawHeat();
  $("#heatSort").onchange = (e) => { state.heatSort = e.target.value; drawHeat(); };

  // clusters
  const groups = {};
  rows.forEach((r) => (groups[r.profile] = groups[r.profile] || []).push(r));
  const gnames = Object.keys(groups).sort();
  chart($("#clus"), {
    legend: { top: 0, type: "scroll", textStyle: { color: css("--text-2") } },
    grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
    tooltip: { formatter: (p) => `<b>${esc(p.data[3])}</b><br>${esc(p.seriesName)}<br>Vulnerability ${f(p.data[4], 1)}` },
    xAxis: axis({ type: "value", name: "Component 1", nameTextStyle: { color: css("--muted") }, splitLine: { show: false } }),
    yAxis: axis({ type: "value", name: "Component 2", nameTextStyle: { color: css("--muted") } }),
    series: gnames.map((g, i) => ({
      name: g, type: "scatter", data: groups[g].map((r) => [r.pc[0], r.pc[1], r.iso3, r.name, r.score, r.population]),
      symbolSize: (v) => Math.min(46, 8 + Math.sqrt((v[5] || 1e6) / 1e6) * 1.1),
      itemStyle: { color: C()[i % 8], opacity: 0.85, borderColor: css("--surface"), borderWidth: 1.5 },
      label: { show: true, formatter: (p) => p.data[2], fontSize: 9, color: css("--text-2"), position: "top" },
      emphasis: { focus: "series", scale: 1.25 },
    })),
  }).on("click", (p) => go("country", p.data[2]));
  $("#clusList").innerHTML = gnames.map((g, i) => `<div style="padding:10px 0;border-bottom:1px solid var(--border)">
    <div style="display:flex;align-items:center;gap:8px"><span style="width:10px;height:10px;border-radius:3px;background:${C()[i % 8]}"></span><b>${esc(g)}</b><span class="tag">${groups[g].length}</span></div>
    <div style="margin-top:6px">${groups[g].sort((a, b) => a.name.localeCompare(b.name)).map((r) => `<span class="peer" style="padding:3px 9px;font-size:12px" onclick="go('country','${r.iso3}')">${esc(r.name)}</span>`).join("")}</div></div>`).join("");

  // table
  const cols = [["rank", "#"], ["name", "Economy"], ["region", "Region"], ["profile", "Profile"], ["score", "Vulnerability"], ["label", "Level"],
    ["cagr", "Growth to 2035"], ["imf_growth", "IMF 2026-30"], ["flags", "Red flags"], ["coverage", "Data coverage"]];
  let sortK = "rank", asc = true;
  const drawTbl = () => {
    const q = ($("#rankSearch").value || "").toLowerCase();
    const list = rows.filter((r) => !q || `${r.name} ${r.region} ${r.profile}`.toLowerCase().includes(q))
      .sort((a, b) => { const x = a[sortK], y = b[sortK]; const c = typeof x === "string" ? x.localeCompare(y) : (x ?? -1e9) - (y ?? -1e9); return asc ? c : -c; });
    $("#rankTbl").innerHTML = `<table><thead><tr>${cols.map(([k, l]) => `<th data-k="${k}">${l}${sortK === k ? (asc ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead><tbody>
      ${list.map((r) => `<tr class="click" data-iso="${r.iso3}"><td class="num">${r.rank}</td><td><b>${esc(r.name)}</b></td><td>${esc(r.region)}</td><td>${esc(r.profile)}</td>
      <td><div style="display:flex;align-items:center;gap:8px"><div class="bar" style="width:90px"><i style="width:${r.score}%"></i></div><span class="num">${f(r.score, 1)}</span></div></td>
      <td>${chip(r.label)}</td><td class="num">${f(r.cagr, 1, "%")}</td><td class="num">${f(r.imf_growth, 1, "%")}</td><td class="num">${r.flags}</td><td class="num">${f(r.coverage * 100, 0, "%")}</td></tr>`).join("")}</tbody></table>`;
    $$("#rankTbl th").forEach((th) => th.onclick = () => { if (sortK === th.dataset.k) asc = !asc; else { sortK = th.dataset.k; asc = true; } drawTbl(); });
    $$("#rankTbl tr.click").forEach((tr) => tr.onclick = () => go("country", tr.dataset.iso));
  };
  drawTbl();
  $("#rankSearch").oninput = drawTbl;
}
async function ensureGeo() {
  if (state.geoReady) return;
  const g = await API("/static/world.geo.json");
  echarts.registerMap("world", g);
  state.geoReady = true;
}

// ================================================================== LIVE
async function vLive(main) {
  const iso = state.iso;
  const [g, lc] = await Promise.all([API("/api/live/global"), API(`/api/live/country/${iso}`)]);
  state.global = g;
  let secs = 60;
  main.innerHTML = `<div class="view">
    ${head("Real-time layer", "Live monitor", "Official statistics lag by months; markets move every second. Live prices feed a growth nowcast and a live risk reading.",
      `<span class="countdown"><span class="live-pill"><span class="dot"></span>LIVE</span> refresh in <b id="cd">60</b>s</span><br><span id="liveAt">${esc(g.at)}</span>`)}
    <div class="kpis" id="glob"></div>
    <div class="card-head" style="margin:22px 0 12px"><h2>${esc(name(iso))} · real-time assessment</h2>
      <div style="display:flex;gap:8px"><button class="btn ghost" onclick="openPalette()">Change economy</button><button class="btn" id="liveRefresh">↻ Refresh now</button></div></div>
    <div class="grid">
      <div class="card c4"><div class="card-head"><h2>Live risk reading</h2><span class="hint">70% structural · 30% market</span></div><div id="gauge" class="chart"></div></div>
      <div class="card c4"><div class="card-head"><h2>Growth nowcast ${lc.nowcast.year}</h2><span class="hint" id="ncAt"></span></div><div id="wf" class="chart"></div></div>
      <div class="card c4"><div class="card-head"><h2>Market stress</h2><span class="hint" id="stressScore"></span></div><div id="stress" class="chart short"></div><div id="alerts"></div></div>
      <div class="card c8"><div class="card-head"><h2>Market signals</h2><div class="seg" id="sigSeg"><button data-t="fx">Currency</button><button data-t="eq">Equity index</button><button data-t="oil">Brent crude</button></div></div><div id="sig" class="chart"></div></div>
      <div class="card c4"><div class="card-head"><h2>Nowcast history</h2><span class="hint">logged on every refresh</span></div><div id="nch" class="chart"></div></div>
      <div class="card c12"><div class="card-head"><h2>Asian currencies · 3-month move vs US$</h2><span class="hint">red = depreciation · click a bar to switch economy</span></div><div id="fxr" class="chart"><div class="skel" style="height:100%"></div></div></div>
    </div></div>`;
  const drawGlobal = (g) => {
    $("#glob").innerHTML = g.items.map((i) => `<div class="kpi"><div class="lab">${esc(i.label)}</div>
      <div class="val num">${f(i.price, i.price > 1000 ? 0 : 2)}</div>
      <div class="knote"><span class="${(i.chg_1m || 0) >= 0 ? "up" : "down"}">${sgn(i.chg_1m, 1, "%")}</span> 1m · ${sgn(i.chg_1y, 1, "%")} 1y</div>
      <div id="sp_${i.key}" class="chart mini" style="margin-top:6px"></div></div>`).join("");
    g.items.forEach((i) => {
      const col = (i.chg_1m || 0) >= 0 ? css("--good") : css("--critical");
      chart($(`#sp_${i.key}`), { grid: { left: 0, right: 0, top: 2, bottom: 0 }, tooltip: { trigger: "axis", formatter: (p) => `${p[0].value[0]}: <b>${f(p[0].value[1], 2)}</b>` },
        xAxis: { type: "category", show: false, boundaryGap: false }, yAxis: { type: "value", show: false, scale: true },
        series: [{ type: "line", data: i.series.slice(-180), symbol: "none", lineStyle: { width: 1.8, color: col },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: col + "55" }, { offset: 1, color: col + "00" }]) } }] });
    });
  };
  drawGlobal(g);

  const drawCountry = (lc) => {
    const lv = lc.live_risk;
    chart($("#gauge"), {
      series: [{ type: "gauge", min: 0, max: 100, startAngle: 210, endAngle: -30, radius: "95%", center: ["50%", "58%"],
        axisLine: { lineStyle: { width: 14, color: [[0.44, css("--good")], [0.52, css("--warn")], [0.6, css("--serious")], [1, css("--critical")]] } },
        pointer: { width: 5, length: "62%", itemStyle: { color: css("--text") } }, anchor: { show: true, size: 12, itemStyle: { color: css("--text") } },
        axisTick: { show: false }, splitLine: { length: 14, lineStyle: { color: css("--surface"), width: 2 } }, axisLabel: { color: css("--muted"), distance: 18, fontSize: 10 },
        title: { offsetCenter: [0, "62%"], color: css("--text-2"), fontSize: 13 },
        detail: { valueAnimation: true, offsetCenter: [0, "34%"], fontSize: 30, fontWeight: 750, color: css("--text"), formatter: (v) => v.toFixed(1) },
        data: [{ value: +lv.toFixed(1), name: `${lc.live_label} · structural ${f(lc.structural, 1)}` }] }],
    });
    const nc = lc.nowcast;
    $("#ncAt").textContent = nc.computed_at;
    const cons = nc.consensus, adj = nc.oil_adjustment_pp || 0;
    const cats = ["AsiaPulse model", "IMF WEO", "Consensus", "Live oil adj.", "Nowcast"];
    const baseV = [0, 0, 0, Math.min(cons, cons + adj), 0];
    const vals = [nc.asiapulse_model, nc.imf_weo, cons, Math.abs(adj), nc.nowcast];
    const cols = [C()[0], C()[1], css("--muted"), adj >= 0 ? css("--good") : css("--critical"), C()[2]];
    chart($("#wf"), {
      grid: { left: 8, right: 8, top: 24, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", formatter: (p) => { const i = p[0].dataIndex; return `<b>${cats[i]}</b><br>${i === 3 ? sgn(adj, 2, " pp") : f(vals[i], 2, "%")}`; } },
      xAxis: axis({ type: "category", data: cats, axisLabel: { color: css("--muted"), fontSize: 10, interval: 0 }, splitLine: { show: false } }),
      yAxis: axis({ type: "value", axisLabel: { formatter: "{value}%", color: css("--muted") } }),
      series: [{ type: "bar", stack: "w", data: baseV, itemStyle: { color: "transparent" }, silent: true },
        { type: "bar", stack: "w", barWidth: "52%", data: vals.map((v, i) => ({ value: isNum(v) ? v : 0, itemStyle: { color: cols[i], borderRadius: [6, 6, 0, 0] } })),
          label: { show: true, position: "top", color: css("--text"), fontWeight: 600, formatter: (p) => (p.dataIndex === 3 ? sgn(adj, 2) : f(vals[p.dataIndex], 2, "%")) } }],
    });
    const comp = Object.entries(lc.stress.components || {}).filter(([, v]) => isNum(v)).sort((a, b) => a[1] - b[1]);
    $("#stressScore").textContent = `score ${f(lc.stress.score, 0)}/100`;
    chart($("#stress"), {
      grid: { left: 8, right: 30, top: 6, bottom: 4, containLabel: true },
      tooltip: { trigger: "item", formatter: (p) => `${esc(p.name)}: <b>${f(p.value, 0)}</b>/100` },
      xAxis: axis({ type: "value", max: 100, axisLabel: { show: false } }),
      yAxis: axis({ type: "category", data: comp.map((c) => c[0]), axisLabel: { color: css("--text-2"), fontSize: 11 }, splitLine: { show: false } }),
      series: [{ type: "bar", data: comp.map((c) => ({ value: +c[1].toFixed(1), itemStyle: { color: c[1] >= 60 ? css("--critical") : c[1] >= 35 ? css("--warn") : C()[0], borderRadius: 6 } })),
        barWidth: 12, label: { show: true, position: "right", color: css("--text-2"), formatter: (p) => f(p.value, 0) }, showBackground: true, backgroundStyle: { color: css("--surface-3"), borderRadius: 6 } }],
    });
    $("#alerts").innerHTML = lc.alerts.length ? lc.alerts.map((a) => `<div class="flag"><span class="ico">⚠</span><div><b>${esc(a)}</b><small>above the 60/100 alert threshold</small></div></div>`).join("")
      : '<div class="note">No live market alerts for this economy.</div>';
    // history
    const h = lc.history || [];
    chart($("#nch"), {
      grid: { left: 8, right: 12, top: 16, bottom: 8, containLabel: true }, tooltip: { trigger: "axis" },
      xAxis: axis({ type: "category", data: h.map((r) => r.ts.slice(5)), splitLine: { show: false } }),
      yAxis: axis({ type: "value", scale: true, axisLabel: { formatter: "{value}%", color: css("--muted") } }),
      series: [{ type: "line", name: "Nowcast", data: h.map((r) => r.nowcast), smooth: true, symbolSize: 8, lineStyle: { width: 2.5 }, areaStyle: { opacity: 0.12 } }],
      graphic: h.length < 2 ? [{ type: "text", left: "center", top: "middle", style: { text: "History builds as the live layer refreshes", fill: css("--muted"), fontSize: 12 } }] : [],
    });
    drawSignal(lc);
  };
  const drawSignal = (lc) => {
    const t = state.liveTab;
    $$("#sigSeg button").forEach((b) => b.classList.toggle("on", b.dataset.t === t));
    let data = [], title = "", extra = [];
    if (t === "fx" && lc.fx) { data = lc.fx.series; title = `${lc.fx.currency} per US$ (up = weaker) · 3m ${sgn(lc.fx.depr_3m, 1, "%")}`; }
    else if (t === "eq" && lc.equity) { data = lc.equity.series; title = `${lc.equity.symbol} · drawdown from 52-wk high ${f(lc.equity.drawdown, 1, "%")}`; }
    else if (t === "oil") {
      const b = state.global.items.find((i) => i.key === "brent"); data = b.series; title = `Brent US$/bbl · 30-day avg vs prior 12 months ${sgn(state.global.oil_move, 1, "%")}`;
      const avg = data.map((p, i) => { const w = data.slice(Math.max(0, i - 250), i + 1).map((x) => x[1]); return [p[0], w.reduce((a, c) => a + c, 0) / w.length]; });
      extra = [{ name: "Trailing 12-month avg", type: "line", data: avg, symbol: "none", lineStyle: { width: 1.5, type: "dashed", color: css("--muted") } }];
    }
    const el = $("#sig");
    const old = state.charts.find((c) => c.getDom() === el); if (old) { old.dispose(); state.charts = state.charts.filter((c) => c !== old); }
    if (!data.length) { el.innerHTML = `<div class="note" style="margin-top:40px">${lc.pegged && t === "fx" ? "This currency is pegged to the US dollar — no floating-rate stress signal." : "No liquid daily series for this economy; the live reading relies on global drivers."}</div>`; return; }
    el.innerHTML = "";
    chart(el, {
      title: { text: title, left: 0, top: 0, textStyle: { fontSize: 12, color: css("--text-2"), fontWeight: 500 } },
      grid: { left: 8, right: 16, top: 44, bottom: 50, containLabel: true }, legend: { show: !!extra.length, top: 0, right: 0, left: "auto" },
      tooltip: { trigger: "axis" }, dataZoom: [{ type: "inside", start: 0, end: 100 }, { type: "slider", height: 20, bottom: 6, borderColor: css("--border"), textStyle: { color: css("--muted") } }],
      xAxis: axis({ type: "category", boundaryGap: false, data: data.map((p) => p[0]), splitLine: { show: false } }),
      yAxis: axis({ type: "value", scale: true }),
      series: [{ name: "Price", type: "line", data: data.map((p) => p[1]), symbol: "none", lineStyle: { width: 2.2, color: C()[0] },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: C()[0] + "40" }, { offset: 1, color: C()[0] + "00" }]) } },
        ...extra.map((e) => ({ ...e, data: e.data.map((p) => p[1]) }))],
    });
  };
  drawCountry(lc);
  $$("#sigSeg button").forEach((b) => b.onclick = () => { state.liveTab = b.dataset.t; drawSignal(lc); });

  // regional FX (can be slow on a cold start)
  API("/api/live/regional-fx").then((fx) => {
    const el = $("#fxr"); if (!el) return; el.innerHTML = "";
    chart(el, {
      grid: { left: 8, right: 8, top: 16, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", formatter: (p) => `<b>${esc(fx[p[0].dataIndex].name)}</b> (${fx[p[0].dataIndex].currency})<br>${sgn(p[0].value, 1, "%")} vs US$ in 3 months` },
      xAxis: axis({ type: "category", data: fx.map((r) => r.name), axisLabel: { rotate: 50, fontSize: 10, color: css("--muted") }, splitLine: { show: false } }),
      yAxis: axis({ type: "value", axisLabel: { formatter: "{value}%", color: css("--muted") } }),
      series: [{ type: "bar", data: fx.map((r) => ({ value: +(r.depr_3m || 0).toFixed(2), itemStyle: { color: r.depr_3m > 0 ? css("--critical") : C()[0], borderRadius: r.depr_3m > 0 ? [5, 5, 0, 0] : [0, 0, 5, 5], opacity: r.iso3 === iso ? 1 : 0.75 } })), barMaxWidth: 22 }],
    }).on("click", (p) => { setIso(fx[p.dataIndex].iso3); });
  }).catch(() => { const el = $("#fxr"); if (el) el.innerHTML = '<div class="note">Regional currency data unavailable right now.</div>'; });

  const refresh = async () => {
    try {
      const [g2, lc2] = await Promise.all([API("/api/live/global"), API(`/api/live/country/${iso}`)]);
      state.global = g2; $("#liveAt").textContent = g2.at;
      state.charts.forEach((c) => c.dispose()); state.charts = [];
      drawGlobal(g2); drawCountry(lc2); refreshTicker();
      toast(`⚡ Live data refreshed · nowcast <b>${f(lc2.nowcast.nowcast, 2, "%")}</b>`);
    } catch (e) { toast("Live refresh failed — showing last data"); }
    secs = 60;
  };
  $("#liveRefresh").onclick = refresh;
  state.timers.push(setInterval(() => { secs--; const el = $("#cd"); if (el) el.textContent = secs; if (secs <= 0) refresh(); }, 1000));
}

// ================================================================== COUNTRY
async function vCountry(main) {
  const iso = state.iso;
  const d = await API(`/api/country/${iso}`);
  const p = d.profile, r = d.risk, ind = p.indicators;
  const iv = (k) => (ind[k] || {}).value;
  main.innerHTML = `<div class="view">
    ${head(`${esc(p.region)} · ${esc(p.economic_profile)}`, `${esc(p.country)} ${chip(r.label)}`,
      `Vulnerability <b>${f(r.composite_vulnerability, 1)}</b>/100 · rank <b>${r.rank_most_vulnerable}</b> of ${r.of} (1 = most vulnerable) · ${r.red_flags.length} red flags · data coverage ${f(r.data_coverage * 100, 0, "%")}`,
      `<div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn primary" id="refitBtn">▶ Re-run forecast now</button><button class="btn" onclick="go('policy')">Policy lab →</button><button class="btn" onclick="go('ai')">Ask AI ✦</button></div>`)}
    <div class="kpis">
      ${kpi("c1", "GDP (current US$)", "$", (ind.gdp_usd || {}).year || "")}${kpi("c2", "Real growth, 5-yr avg", "↗", "")}
      ${kpi("c3", "GDP per capita, PPP", "👤", "")}${kpi("c4", "Unemployment", "⚒", `youth ${f(iv("youth_unemp"), 1, "%")}`)}
      ${kpi("c5", "Inflation", "%", (ind.inflation || {}).year || "")}${kpi("c6", "Public debt", "🏛", "% of GDP · IMF WEO")}
    </div>
    <div class="kpis">
      ${kpi("t1", "Internet users", "📶", "technology")}${kpi("t2", "R&D spending", "🔬", "% of GDP")}${kpi("t3", "High-tech exports", "💡", "% of manufactured exports")}
      ${kpi("t4", "Tertiary enrolment", "🎓", "human capital")}${kpi("t5", "Female labour participation", "⚥", "labour")}${kpi("t6", "Electricity access", "⚡", "infrastructure")}
    </div>
    <div class="grid">
      <div class="card c8"><div class="card-head"><h2>Real GDP growth · actual, forecasts & live nowcast</h2><span class="hint">drag the slider to zoom</span></div><div id="gro" class="chart"></div></div>
      <div class="card c4"><div class="card-head"><h2>Real-time prediction</h2><span class="hint" id="rtAt">loading…</span></div>
        <div style="font-size:12px;color:var(--text-2)">Live growth nowcast</div><div class="num" id="rtNow" style="font-size:44px;font-weight:800;letter-spacing:-.03em">—</div>
        <div id="rtParts" style="margin:6px 0 12px"></div><div id="rtGauge" class="chart short" style="height:170px"></div><div id="refitInfo" class="hint"></div></div>
      <div class="card c8"><div class="card-head"><h2>Outlook to ${state.meta.forecast_end}</h2>
        <div class="seg" id="fanSeg"><button data-k="gdp_real">Real GDP</button><button data-k="unemp">Unemployment</button><button data-k="emp_ratio">Employment</button><button data-k="gdp_pc_ppp">GDP per capita</button></div></div>
        <div id="fanC" class="chart"></div><div id="valBadges" style="margin-top:8px"></div></div>
      <div class="card c4"><div class="card-head"><h2>Vulnerability profile</h2><div class="seg" id="radSeg"><button data-r="radar" class="on">Radar</button><button data-r="bars">Bars</button></div></div><div id="rad" class="chart"></div></div>
      <div class="card c6"><div class="card-head"><h2>Red flags</h2><span class="hint">absolute thresholds with a stated basis</span></div><div id="flags"></div></div>
      <div class="card c6"><div class="card-head"><h2>Peers & top priorities</h2></div><div id="peers"></div><div id="topPol" style="margin-top:12px"></div></div>
      <div class="card c12"><div class="card-head"><h2>All indicators</h2><div style="display:flex;gap:8px"><select class="input" id="indArea"></select><input class="input" id="indQ" placeholder="Search indicators…"></div></div><div class="tbl-wrap" id="indTbl"></div></div>
    </div></div>`;
  countUp($("#c1"), (ind.gdp_usd || {}).value_bn, 0, "$", " bn"); countUp($("#c2"), iv("growth_5y_avg"), 1, "", "%");
  countUp($("#c3"), iv("gdp_pc_ppp"), 0, "$"); countUp($("#c4"), iv("unemp"), 1, "", "%"); countUp($("#c5"), iv("inflation"), 1, "", "%");
  countUp($("#c6"), iv("gov_debt"), 1, "", "%"); countUp($("#t1"), iv("internet"), 0, "", "%"); countUp($("#t2"), iv("rnd"), 2, "", "%");
  countUp($("#t3"), iv("hightech_exports"), 1, "", "%"); countUp($("#t4"), iv("tertiary_enrol"), 0, "", "%"); countUp($("#t5"), iv("female_lfp"), 1, "", "%"); countUp($("#t6"), iv("electricity"), 0, "", "%");

  // growth chart (live nowcast added when it arrives)
  const gr = d.growth;
  const groC = chart($("#gro"), {
    grid: { left: 8, right: 16, top: 34, bottom: 50, containLabel: true }, tooltip: { trigger: "axis", valueFormatter: (v) => f(v, 2, "%") },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 6, borderColor: css("--border"), textStyle: { color: css("--muted") } }],
    xAxis: axis({ type: "value", min: 2000, max: state.meta.forecast_end, splitLine: { show: false }, axisLabel: { formatter: (v) => v, color: css("--muted") } }),
    yAxis: axis({ type: "value", axisLabel: { formatter: "{value}%", color: css("--muted") } }),
    series: [
      { name: "Actual", type: "line", data: gr.actual, symbol: "circle", symbolSize: 5, lineStyle: { width: 2.5, color: css("--text") }, itemStyle: { color: css("--text") },
        markLine: { silent: true, symbol: "none", data: [{ yAxis: 0 }], lineStyle: { color: css("--border-strong") }, label: { show: false } } },
      { name: "AsiaPulse forecast", type: "line", data: gr.forecast, symbol: "none", lineStyle: { width: 2.5, type: "dashed", color: C()[0] }, itemStyle: { color: C()[0] } },
      { name: "IMF WEO", type: "line", data: gr.imf, symbol: "none", lineStyle: { width: 2, color: C()[1] }, itemStyle: { color: C()[1] } },
    ],
  });
  API(`/api/live/country/${iso}`).then((lc) => {
    const nc = lc.nowcast;
    if (!$("#rtNow")) return;
    countUp($("#rtNow"), nc.nowcast, 2, "", "%");
    $("#rtAt").textContent = nc.computed_at;
    $("#rtParts").innerHTML = `<span class="tag">model ${f(nc.asiapulse_model, 2, "%")}</span><span class="tag">IMF ${f(nc.imf_weo, 2, "%")}</span><span class="tag">live oil ${sgn(nc.oil_adjustment_pp, 2, " pp")}</span>`;
    groC.setOption({ series: [{}, {}, {}, { name: "Live nowcast", type: "effectScatter", data: [[nc.year, nc.nowcast]], symbolSize: 14,
      itemStyle: { color: C()[2] }, rippleEffect: { scale: 3 }, z: 10 }] });
    chart($("#rtGauge"), { series: [{ type: "gauge", min: 0, max: 100, startAngle: 200, endAngle: -20, radius: "100%", center: ["50%", "70%"],
      axisLine: { lineStyle: { width: 10, color: [[0.44, css("--good")], [0.52, css("--warn")], [0.6, css("--serious")], [1, css("--critical")]] } },
      pointer: { width: 4, length: "55%", itemStyle: { color: css("--text") } }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
      title: { offsetCenter: [0, "28%"], color: css("--text-2"), fontSize: 11 }, detail: { offsetCenter: [0, "-8%"], fontSize: 18, fontWeight: 700, color: css("--text"), formatter: (v) => v.toFixed(1) },
      data: [{ value: +lc.live_risk.toFixed(1), name: `Live risk · ${lc.live_label}` }] }] });
  }).catch(() => { if ($("#rtAt")) $("#rtAt").textContent = "live data unavailable"; });

  // fan chart
  const fcData = JSON.parse(JSON.stringify(d.forecast));
  const units = { gdp_real: "US$ bn", unemp: "%", emp_ratio: "%", gdp_pc_ppp: "int$" };
  const fanC = chart($("#fanC"), {});
  const drawFan = () => {
    const k = state.fanKey, s = fcData[k];
    $$("#fanSeg button").forEach((b) => b.classList.toggle("on", b.dataset.k === k));
    fanC.setOption({
      grid: { left: 8, right: 16, top: 30, bottom: 8, containLabel: true }, legend: { data: ["Actual", "Forecast", "80% interval"], top: 0 },
      tooltip: fanTooltip(units[k]),
      xAxis: axis({ type: "value", min: 2000, max: state.meta.forecast_end, splitLine: { show: false }, axisLabel: { formatter: (v) => v, color: css("--muted") } }),
      yAxis: axis({ type: "value", scale: true, name: units[k], nameTextStyle: { color: css("--muted") } }),
      series: fan(s.history, s.forecast, C()[0]),
    }, true);
    const v = d.validation.series[k];
    $("#valBadges").innerHTML = v ? `<span class="tag">Confidence: <b>${esc(v.confidence)}</b></span><span class="tag">held-out error ${f(v.error, 2)} ${v.unit}</span>
      <span class="tag">skill vs naive ${f(v.skill_vs_naive, 2)}</span><span class="tag">80% coverage ${f((v.interval_coverage80 || 0) * 100, 0, "%")}</span>` : '<span class="tag">Validation unavailable</span>';
  };
  drawFan();
  $$("#fanSeg button").forEach((b) => b.onclick = () => { state.fanKey = b.dataset.k; drawFan(); });
  $("#refitBtn").onclick = async (e) => {
    const b = e.currentTarget; b.disabled = true; b.innerHTML = '<span class="spin"></span> Re-fitting…';
    try {
      const res = await (await POST(`/api/refit/${iso}`)).json();
      Object.entries(res.forecast).forEach(([k, v]) => { if (v.length) fcData[k].forecast = v; });
      drawFan();
      $("#refitInfo").innerHTML = `Ensemble re-fitted live at <b>${res.at}</b> in <b>${f(res.ms, 0)} ms</b> · 4 models × 3 series`;
      toast(`▶ Forecast re-run live in <b>${f(res.ms, 0)} ms</b>`);
    } catch (err) { toast("Re-fit failed"); }
    b.disabled = false; b.innerHTML = "▶ Re-run forecast now";
  };

  // radar / bars
  const pil = state.meta.pillars;
  const radC = chart($("#rad"), {});
  const drawRad = (mode) => {
    $$("#radSeg button").forEach((b) => b.classList.toggle("on", b.dataset.r === mode));
    if (mode === "radar") {
      radC.setOption({
        legend: { bottom: 0, top: "auto" }, tooltip: { trigger: "item" },
        radar: { radius: "62%", center: ["50%", "48%"], indicator: pil.map((p) => ({ name: p.label.replace(" & ", " &\n"), max: 100 })),
          axisName: { color: css("--text-2"), fontSize: 10 }, splitLine: { lineStyle: { color: css("--grid") } }, splitArea: { show: false }, axisLine: { lineStyle: { color: css("--grid") } } },
        series: [{ type: "radar", symbolSize: 4, data: [
          { name: "Asia median", value: pil.map((p) => d.asia_median[p.key]), lineStyle: { color: css("--muted"), type: "dotted" }, itemStyle: { color: css("--muted") } },
          { name: "Peer median", value: pil.map((p) => d.peer_median[p.key]), lineStyle: { color: C()[1] }, itemStyle: { color: C()[1] } },
          { name: p.country, value: pil.map((x) => d.pillars[x.key]), lineStyle: { color: C()[0], width: 2.5 }, itemStyle: { color: C()[0] }, areaStyle: { color: C()[0], opacity: 0.22 } },
        ] }],
      }, true);
    } else {
      const items = pil.map((x) => [x.label, d.pillars[x.key], d.peer_median[x.key]]).filter((x) => isNum(x[1])).sort((a, b) => a[1] - b[1]);
      radC.setOption({
        grid: { left: 8, right: 16, top: 26, bottom: 8, containLabel: true }, legend: { top: 0 }, tooltip: { trigger: "axis", valueFormatter: (v) => f(v, 0) },
        xAxis: axis({ type: "value", max: 100 }), yAxis: axis({ type: "category", data: items.map((x) => x[0]), axisLabel: { fontSize: 10, color: css("--text-2") }, splitLine: { show: false } }),
        series: [{ name: p.country, type: "bar", data: items.map((x) => x[1]), barWidth: 10, itemStyle: { color: C()[0], borderRadius: 5 } },
          { name: "Peer median", type: "scatter", data: items.map((x) => x[2]), symbol: "diamond", symbolSize: 11, itemStyle: { color: C()[1] } }],
      }, true);
    }
  };
  drawRad("radar");
  $$("#radSeg button").forEach((b) => b.onclick = () => drawRad(b.dataset.r));

  $("#flags").innerHTML = r.red_flags.length ? r.red_flags.map((x) => `<div class="flag"><span class="ico">⚑</span><div><b>${esc(x.flag)}</b><small>${esc(x.basis)}</small></div><span class="v num">${f(x.value, 1)}</span></div>`).join("")
    : '<div class="note">No threshold-based red flags.</div>';
  $("#peers").innerHTML = `<div class="hint" style="margin-bottom:8px">Nearest economies in standardised feature space — click to open</div>` +
    d.peers.nearest_peers.map((x) => `<span class="peer" onclick="go('country','${(state.meta.countries.find((c) => c.name === x.country) || {}).iso3}')">${esc(x.country)} <small style="color:var(--muted)">${f(x.distance, 1)}</small></span>`).join("");
  $("#topPol").innerHTML = d.policies.slice(0, 3).map((x, i) => `<div class="rank-row" style="grid-template-columns:22px 1fr auto" onclick="go('policy')"><span class="pos">${i + 1}</span>
    <span><b>${esc(x.title)}</b><br><small style="color:var(--muted)">${esc(x.trigger)}</small></span><span class="tag">${esc(x.horizon)}</span></div>`).join("");

  // indicators table
  const areas = [...new Set(d.indicators.map((x) => x.area))].sort();
  $("#indArea").innerHTML = `<option value="">All areas</option>` + areas.map((a) => `<option>${esc(a)}</option>`).join("");
  const drawInd = () => {
    const q = $("#indQ").value.toLowerCase(), a = $("#indArea").value;
    const list = d.indicators.filter((x) => (!a || x.area === a) && (!q || x.label.toLowerCase().includes(q)));
    $("#indTbl").innerHTML = `<table><thead><tr><th>Indicator</th><th>Area</th><th>Value</th><th>Unit</th><th>Year</th></tr></thead><tbody>
      ${list.map((x) => `<tr><td>${esc(x.label)}</td><td><span class="tag">${esc(x.area)}</span></td><td class="num"><b>${f(x.value, 2)}</b></td><td>${esc(x.unit)}</td><td class="num">${x.year ?? "—"}</td></tr>`).join("")}</tbody></table>`;
  };
  drawInd(); $("#indQ").oninput = drawInd; $("#indArea").onchange = drawInd;
}

// ================================================================== POLICY LAB
const LEVERS = [
  ["demand_shock_pp", "Global demand shock", -5, 3, 0.25, "pp growth", "shock"],
  ["oil_price_pct", "Oil-price change", -60, 100, 5, "%", "shock"],
  ["remittance_pct", "Remittance inflows", -50, 30, 5, "%", "shock"],
  ["fiscal_consolidation_pp", "Fiscal consolidation", -3, 5, 0.25, "% GDP", "policy"],
  ["public_investment_pp", "Public investment boost", 0, 4, 0.25, "% GDP / yr", "policy"],
  ["flfp_increase_pp", "Female labour participation", 0, 20, 1, "pp by 2035", "policy"],
  ["digital_adoption_pp", "Digital adoption (internet)", 0, 50, 5, "pp by 2035", "policy"],
  ["interest_rate_pp", "Interest rate on public debt", -3, 5, 0.25, "pp", "policy"],
];
async function vPolicy(main) {
  const iso = state.iso;
  const d = await API(`/api/country/${iso}`);
  const L = (state.levers[iso] = state.levers[iso] || Object.fromEntries(LEVERS.map((l) => [l[0], 0])));
  main.innerHTML = `<div class="view">
    ${head("Policy lab", `${esc(d.profile.country)} ${chip(d.risk.label)}`, "Ranked policy packages for the diagnosed vulnerabilities — each with SDG targets, a measurable KPI, a peer-based target and Asian precedents. Load any package into the simulator and watch the economy respond instantly.", "")}
    <div class="grid">
      <div class="c5"><div class="card"><div class="card-head"><h2>Recommended packages</h2><span class="hint">ranked by severity</span></div><div id="pols"></div></div></div>
      <div class="c7"><div class="card sticky">
        <div class="card-head"><h2>Scenario simulator</h2><div style="display:flex;gap:8px"><button class="btn" id="oilBtn">⚡ Today's oil move</button><button class="btn ghost" id="resetBtn">Reset</button></div></div>
        <div class="kpis" id="scK" style="grid-template-columns:repeat(5,1fr);margin-bottom:10px"></div>
        <div class="seg" id="scSeg" style="margin-bottom:6px"><button data-t="growth">Growth</button><button data-t="unemp">Unemployment</button><button data-t="debt">Public debt</button><button data-t="gdp">GDP level</button></div>
        <div id="scC" class="chart" style="height:270px"></div>
        <div class="grid" style="gap:8px 24px;margin-top:6px"><div class="c6"><div class="eyebrow" style="margin-top:6px">External shocks</div><div id="lvS"></div></div>
          <div class="c6"><div class="eyebrow" style="margin-top:6px">Policy levers</div><div id="lvP"></div></div></div>
        <div class="hint" id="scAssume"></div></div></div>
    </div></div>`;
  // policy cards
  $("#pols").innerHTML = d.policies.map((p, i) => `<div class="policy ${i === 0 ? "open" : ""}" data-i="${i}">
    <div class="policy-head"><div class="ring" style="--p:${Math.min(100, p.priority)}"><span>${f(p.priority, 0)}</span></div>
      <div><b>${esc(p.title)}</b><div style="font-size:12px;color:var(--muted)">${esc(p.pillar)} · ${esc(p.horizon)}</div></div><span style="color:var(--muted)">▾</span></div>
    <div class="policy-body"><div><b style="color:var(--text)">Why now:</b> ${esc(p.trigger)}</div><div style="margin-top:4px"><b style="color:var(--text)">Objective:</b> ${esc(p.objective)}</div>
      <ul>${p.actions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
      <div style="display:flex;justify-content:space-between;font-size:12.5px;margin-top:8px"><span>${esc(p.kpi_label)}</span><span>now <b class="num" style="color:var(--text)">${f(p.kpi_now, 1)}</b> → target <b class="num" style="color:var(--good)">${f(p.kpi_peer_target, 1)}</b></span></div>
      ${p.precedents.length ? `<div class="eyebrow" style="margin-top:12px">Asian precedents · biggest 10-year improvement</div>${p.precedents.map((x) => `<div class="prec"><span>${esc(x.country)}</span><span class="num">${f(x.from, 1)} (${x.from_year}) → <b>${f(x.to, 1)}</b> (${x.to_year})</span></div>`).join("")}` : ""}
      <div style="margin-top:10px">${p.sdgs.map((s) => `<span class="tag">${esc(s)}</span>`).join("")}<span class="tag">Lead: ${esc(p.lead)}</span></div>
      ${Object.keys(p.lever || {}).length ? `<button class="btn primary" style="margin-top:12px" data-sim="${i}">Simulate this package →</button>` : ""}</div></div>`).join("");
  $$(".policy-head").forEach((h) => h.onclick = () => h.parentElement.classList.toggle("open"));
  $$("[data-sim]").forEach((b) => b.onclick = () => { const lv = d.policies[+b.dataset.sim].lever; LEVERS.forEach((l) => (L[l[0]] = lv[l[0]] || 0)); syncSliders(); run(); toast(`Loaded <b>${esc(d.policies[+b.dataset.sim].title)}</b>`); });

  // sliders
  const slider = (l) => `<div class="lever"><div class="lever-top"><span>${l[1]}</span><b id="v_${l[0]}"></b></div>
    <input type="range" id="r_${l[0]}" min="${l[2]}" max="${l[3]}" step="${l[4]}" value="${L[l[0]]}"></div>`;
  $("#lvS").innerHTML = LEVERS.filter((l) => l[6] === "shock").map(slider).join("");
  $("#lvP").innerHTML = LEVERS.filter((l) => l[6] === "policy").map(slider).join("");
  const paint = (l) => {
    const el = $(`#r_${l[0]}`), v = +el.value;
    el.style.setProperty("--fill", `${((v - l[2]) / (l[3] - l[2])) * 100}%`);
    $(`#v_${l[0]}`).textContent = `${v > 0 && l[2] < 0 ? "+" : ""}${v} ${l[5]}`;
  };
  const syncSliders = () => LEVERS.forEach((l) => { $(`#r_${l[0]}`).value = L[l[0]]; paint(l); });
  syncSliders();
  const run = debounce(async () => {
    try {
      const res = await (await POST(`/api/scenario/${iso}`, { levers: L })).json();
      drawScenario(res);
    } catch (e) { toast("Scenario failed"); }
  }, 120);
  LEVERS.forEach((l) => $(`#r_${l[0]}`).addEventListener("input", (e) => { L[l[0]] = +e.target.value; paint(l); run(); }));
  $("#resetBtn").onclick = () => { LEVERS.forEach((l) => (L[l[0]] = 0)); syncSliders(); run(); };
  $("#oilBtn").onclick = async () => {
    const o = await API("/api/live-oil");
    L.oil_price_pct = Math.max(-60, Math.min(100, Math.round((o.oil_move || 0) / 5) * 5)); syncSliders(); run();
    toast(`⚡ Oil shock set from live Brent: <b>${sgn(o.oil_move, 1, "%")}</b>`);
  };
  const scC = chart($("#scC"), {});
  let lastRes = null;
  const drawScenario = (res) => {
    lastRes = res;
    const s = res.summary, P = res.path, t = state.scenTab;
    $$("#scSeg button").forEach((b) => b.classList.toggle("on", b.dataset.t === t));
    const dR = s.risk_scenario.score - s.risk_baseline.score;
    const k = (lab, val, note, tone) => `<div class="kpi" style="padding:12px 14px"><div class="lab" style="font-size:11.5px">${lab}</div><div class="val num" style="font-size:20px">${val}</div><div class="knote ${tone || ""}">${note}</div></div>`;
    $("#scK").innerHTML = k("GDP 2035 vs base", sgn(s.gdp_end_diff_pct, 2, "%"), "level effect", s.gdp_end_diff_pct > 0.005 ? "up" : s.gdp_end_diff_pct < -0.005 ? "down" : "")
      + k("Avg growth", f(s.cagr_scen, 2, "%"), `base ${f(s.cagr_base, 2, "%")}`)
      + k("Unemployment 2035", f(s.unemp_end_scen, 1, "%"), `peak ${sgn(s.peak_unemp_diff_pp, 2, " pp")}`, s.peak_unemp_diff_pp > 0.01 ? "down" : s.peak_unemp_diff_pp < -0.01 ? "up" : "")
      + k("Public debt 2035", f(s.debt_end_scen, 1, "%"), `base ${f(s.debt_end_base, 1, "%")}`, s.debt_end_scen < s.debt_end_base - 0.05 ? "up" : s.debt_end_scen > s.debt_end_base + 0.05 ? "down" : "")
      + k("Vulnerability", `${f(s.risk_scenario.score, 1)}`, `${sgn(dR, 1)} · ${s.risk_scenario.label}`, dR < -0.05 ? "up" : dR > 0.05 ? "down" : "");
    const map = { growth: ["growth_base", "growth_scen", "%"], unemp: ["unemp_base", "unemp_scen", "%"], debt: ["debt_base", "debt_scen", "% GDP"], gdp: ["gdp_base", "gdp_scen", "US$ bn"] };
    const [b, sc, u] = map[t], sc1 = t === "gdp" ? 1e9 : 1;
    scC.setOption({
      grid: { left: 8, right: 16, top: 30, bottom: 8, containLabel: true }, legend: { top: 0 },
      tooltip: { trigger: "axis", valueFormatter: (v) => `${f(v, 2)} ${u}` },
      xAxis: axis({ type: "category", data: P.year, boundaryGap: false, splitLine: { show: false } }),
      yAxis: axis({ type: "value", scale: true, name: u, nameTextStyle: { color: css("--muted") } }),
      series: [{ name: "Baseline", type: "line", data: P[b].map((v) => v / sc1), symbol: "none", lineStyle: { width: 2.5, color: C()[0] }, itemStyle: { color: C()[0] } },
        { name: "Scenario", type: "line", data: P[sc].map((v) => v / sc1), symbol: "circle", symbolSize: 6, lineStyle: { width: 2.5, color: C()[1] }, itemStyle: { color: C()[1] },
          areaStyle: { color: C()[1], opacity: 0.08 } }],
    });
    $("#scAssume").innerHTML = `Assumptions · Okun coefficient ${f(s.okun_beta, 2)} · inflation ${f(s.inflation_assumed, 1)}% · interest on debt ${f(s.nominal_rate_assumed, 1)}% (${s.rate_from_data ? "IMF-implied" : "assumed"}) · baseline primary balance ${f(s.primary_balance_assumed, 1)}% GDP${s.debt_assumed ? " · ⚠ debt not reported, 50% assumed" : ""}. Simulations, not forecasts.`;
  };
  $$("#scSeg button").forEach((b) => b.onclick = () => { state.scenTab = b.dataset.t; if (lastRes) drawScenario(lastRes); });
  run();
}

// ================================================================== AI ANALYST
async function vAI(main) {
  const iso = state.iso, cname = name(iso);
  const hist = (state.chat[iso] = state.chat[iso] || []);
  const ai = state.meta.ai;
  main.innerHTML = `<div class="view">
    ${head("Grounded AI", `AI policy analyst · ${esc(cname)}`, "A Qwen agent plans which experts to consult, calls them as tools, and writes a brief from their outputs only. Every number is then verified against the tool outputs.",
      `<span class="tag">${ai.live ? "● " + esc(ai.model) : "offline analyst"}</span>`)}
    <div class="grid">
      <div class="card c8 chat"><div class="msgs" id="msgs"></div>
        <div class="suggest" id="sugg"></div>
        <div class="composer"><textarea class="input" id="q" placeholder="Ask about ${esc(cname)}… (Enter to send, Shift+Enter for a new line)"></textarea><button class="btn primary" id="send">Send ✦</button></div></div>
      <div class="c4">
        <div class="card"><div class="card-head"><h2>How the agent works</h2></div>
          <div class="steps">${["Reads your question & plans", "Calls Pattern · Forecast · Validation · Risk · Policy · Scenario tools", "Writes a brief from tool outputs only", "Grounding check verifies every number"].map((s, i) => `<div class="step" style="animation-delay:${i * 0.08}s"><span class="dot"></span>${s}</div>`).join("")}</div></div>
        <div class="card"><div class="card-head"><h2>Last run</h2></div><div id="trace"><div class="hint">Ask a question to see the agent's tool calls.</div></div></div>
        <div class="card"><div class="card-head"><h2>Policy brief</h2></div><div class="hint" style="margin-bottom:10px">Exports the latest assessment plus the ranked policy package as a PDF.</div><button class="btn" id="pdf">⬇ Download PDF brief</button></div>
      </div></div></div>`;
  const sugg = [`Give me a full policy assessment of ${cname}.`, `What are the three most urgent reforms?`, `What if oil rises 50% and remittances fall 20%?`,
    `How can technology and digital adoption lift growth?`, `How trustworthy are these forecasts?`, `Compare ${cname} with its nearest peers.`];
  $("#sugg").innerHTML = sugg.map((s) => `<button>${esc(s)}</button>`).join("");
  $$("#sugg button").forEach((b, i) => b.onclick = () => send(sugg[i]));
  const msgEl = (role, html) => `<div class="msg ${role}"><div class="avatar">${role === "ai" ? "✦" : "You".slice(0, 1)}</div><div class="bubble">${html}</div></div>`;
  const ground = (g, mode, secs) => `<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
    <span class="${(g.ratio ?? 1) >= 0.95 ? "badge-ok" : "badge-warn"}">${(g.ratio ?? 1) >= 0.95 ? "✓ Grounded" : "⚠ Check"} · ${g.verified}/${g.checked} numbers verified</span>
    <span class="tag">${esc(mode)}${secs ? ` · ${f(secs, 1)}s` : ""}</span>${g.unverified && g.unverified.length ? `<span class="hint">unverified: ${esc(g.unverified.join(", "))}</span>` : ""}</div>`;
  const drawHist = () => {
    $("#msgs").innerHTML = hist.length ? hist.map((m) => m.role === "user" ? msgEl("user", esc(m.content)) : msgEl("ai", marked.parse(m.content) + ground(m.grounding, m.mode, m.seconds))).join("")
      : msgEl("ai", `<b>Hello.</b> I'm the AsiaPulse policy analyst for <b>${esc(cname)}</b>. I answer only from the platform's validated data, forecasts, risk diagnosis and policy engine — and every number I give you is checked. Try a suggestion below.`);
    $("#msgs").scrollTop = 1e9;
  };
  const drawTrace = (t) => {
    $("#trace").innerHTML = `<div class="steps">${t.map((s, i) => `<div class="step" style="animation-delay:${i * 0.12}s"><span class="dot"></span><b style="color:var(--text)">${esc(s.expert)}</b>
      <span class="hint" style="margin-left:auto">${esc(Object.entries(s.args || {}).filter(([k]) => k !== "country").map(([k, v]) => `${k}=${v}`).join(", ") || s.tool)} · ${s.ms} ms</span></div>`).join("")}</div>`;
  };
  drawHist();
  const last = [...hist].reverse().find((m) => m.trace); if (last) drawTrace(last.trace);
  async function send(q) {
    q = (q || $("#q").value).trim(); if (!q) return;
    $("#q").value = ""; hist.push({ role: "user", content: q }); drawHist();
    const pending = document.createElement("div");
    pending.innerHTML = msgEl("ai", `<div class="steps"><div class="step run"><span class="dot"></span>Planning which experts to consult…</div></div>`);
    $("#msgs").appendChild(pending); $("#msgs").scrollTop = 1e9;
    const stepsMsgs = ["Calling Risk expert…", "Calling Forecast expert…", "Calling Validation expert…", "Calling Policy expert…", "Writing the brief…", "Verifying every number…"];
    let si = 0;
    const tick = setInterval(() => { if (si < stepsMsgs.length) { pending.querySelector(".steps").insertAdjacentHTML("beforeend", `<div class="step run"><span class="dot"></span>${stepsMsgs[si++]}</div>`); $("#msgs").scrollTop = 1e9; } }, 1400);
    $("#send").disabled = true;
    try {
      const res = await (await POST(`/api/ask/${iso}`, { question: q, history: hist.slice(0, -1).map((m) => ({ role: m.role === "ai" ? "assistant" : "user", content: m.content })) })).json();
      clearInterval(tick); pending.remove();
      // typewriter reveal
      const wrap = document.createElement("div"); wrap.innerHTML = msgEl("ai", ""); $("#msgs").appendChild(wrap);
      const bub = wrap.querySelector(".bubble"); let n = 0; const txt = res.answer;
      await new Promise((done) => { const t = setInterval(() => { n = Math.min(txt.length, n + 28); bub.innerHTML = marked.parse(txt.slice(0, n)); $("#msgs").scrollTop = 1e9; if (n >= txt.length) { clearInterval(t); done(); } }, 16); });
      hist.push({ role: "ai", content: res.answer, grounding: res.grounding, mode: res.mode, seconds: res.seconds, trace: res.trace });
      drawHist(); drawTrace(res.trace);
      if (res.error) toast(esc(res.error).slice(0, 200));
    } catch (e) { clearInterval(tick); pending.remove(); toast("The analyst could not answer — please retry."); hist.pop(); drawHist(); }
    $("#send").disabled = false;
  }
  $("#send").onclick = () => send();
  $("#q").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  $("#pdf").onclick = async () => {
    const lastAi = [...hist].reverse().find((m) => m.role === "ai");
    const r = await POST(`/api/brief/${iso}`, { answer: lastAi ? lastAi.content : "" });
    const blob = await r.blob(); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `AsiaPulse_${iso}_policy_brief.pdf`; a.click();
    toast("⬇ Policy brief downloaded");
  };
}

// ================================================================== COMPARE
async function vCompare(main) {
  if (!state.compare) {
    const d = await API(`/api/country/${state.iso}`);
    state.compare = [state.iso, ...d.peers.nearest_peers.slice(0, 2).map((x) => (state.meta.countries.find((c) => c.name === x.country) || {}).iso3).filter(Boolean)];
  }
  const inds = await cached("/api/indicators");
  state.cmpInd = state.cmpInd || "internet";
  main.innerHTML = `<div class="view">
    ${head("Benchmarking", "Compare economies", "Pick up to six economies to compare vulnerability by policy area, key indicators and long-run trends.", "")}
    <div class="card" style="margin-bottom:16px"><div id="chips" style="display:flex;flex-wrap:wrap;align-items:center;gap:6px"></div></div>
    <div class="grid">
      <div class="card c5"><div class="card-head"><h2>Vulnerability by policy area</h2></div><div id="cmpRad" class="chart tall"></div></div>
      <div class="card c7"><div class="card-head"><h2 id="cmpTitle">Trend</h2><select class="input" id="cmpInd" style="max-width:340px"></select></div><div id="cmpLine" class="chart tall"></div></div>
      <div class="card c12"><div class="card-head"><h2>Key indicators</h2></div><div class="tbl-wrap" id="cmpTbl"></div></div>
    </div></div>`;
  $("#cmpInd").innerHTML = inds.map((i) => `<option value="${i.key}">${esc(i.label)} · ${esc(i.area)}</option>`).join("");
  $("#cmpInd").value = state.cmpInd;
  const draw = async () => {
    const isos = state.compare;
    $("#chips").innerHTML = isos.map((i, j) => `<span class="peer" style="border-color:${C()[j]}"><span style="width:8px;height:8px;border-radius:50%;background:${C()[j]}"></span>${esc(name(i))} <b data-rm="${i}" style="margin-left:4px">×</b></span>`).join("")
      + (isos.length < 6 ? `<select class="input" id="addC"><option value="">+ Add economy</option>${state.meta.countries.filter((c) => !isos.includes(c.iso3)).map((c) => `<option value="${c.iso3}">${esc(c.name)}</option>`).join("")}</select>` : "");
    $$("[data-rm]").forEach((b) => b.onclick = (e) => { e.stopPropagation(); if (state.compare.length > 1) { state.compare = state.compare.filter((x) => x !== b.dataset.rm); draw(); } });
    if ($("#addC")) $("#addC").onchange = (e) => { if (e.target.value) { state.compare.push(e.target.value); draw(); } };
    const d = await API(`/api/compare?isos=${isos.join(",")}&indicator=${state.cmpInd}`);
    state.charts.forEach((c) => c.dispose()); state.charts = [];
    const pil = state.meta.pillars;
    chart($("#cmpRad"), {
      legend: { bottom: 0, top: "auto" }, tooltip: { trigger: "item" },
      radar: { radius: "64%", center: ["50%", "46%"], indicator: pil.map((p) => ({ name: p.label.replace(" & ", " &\n"), max: 100 })), axisName: { color: css("--text-2"), fontSize: 10 },
        splitLine: { lineStyle: { color: css("--grid") } }, splitArea: { show: false }, axisLine: { lineStyle: { color: css("--grid") } } },
      series: [{ type: "radar", symbolSize: 4, data: isos.map((i, j) => ({ name: d.names[i], value: pil.map((p) => d.pillars[i][p.key]), lineStyle: { color: C()[j], width: 2 }, itemStyle: { color: C()[j] }, areaStyle: { color: C()[j], opacity: 0.08 } })) }],
    });
    $("#cmpTitle").textContent = d.indicator.label;
    chart($("#cmpLine"), {
      grid: { left: 8, right: 70, top: 30, bottom: 8, containLabel: true }, legend: { top: 0 }, tooltip: { trigger: "axis", valueFormatter: (v) => f(v, 2) },
      xAxis: axis({ type: "value", min: 2000, splitLine: { show: false }, axisLabel: { formatter: (v) => v, color: css("--muted") } }), yAxis: axis({ type: "value", scale: true }),
      series: isos.map((i, j) => ({ name: d.names[i], type: "line", data: d.indicator.series[i], symbol: "none", smooth: 0.2, lineStyle: { width: 2.5, color: C()[j] }, itemStyle: { color: C()[j] },
        endLabel: { show: true, formatter: (p) => d.names[i], color: C()[j], fontSize: 11 } })),
    });
    const cols = [["profile", "Profile"], ["vulnerability", "Vulnerability"], ["risk_label", "Level"], ["gdp_growth_5y_avg", "Growth 5y %"], ["gdp_cagr_fc", "Outlook %"],
      ["gdp_pc_ppp", "GDP pc PPP"], ["unemp", "Unemp %"], ["youth_unemp", "Youth unemp %"], ["female_lfp", "Female LFP %"], ["inflation", "Inflation %"], ["gov_debt", "Debt % GDP"]];
    $("#cmpTbl").innerHTML = `<table><thead><tr><th>Economy</th>${cols.map((c) => `<th>${c[1]}</th>`).join("")}</tr></thead><tbody>${d.rows.map((r) => `<tr><td><b>${esc(r.country)}</b></td>${cols.map(([k]) =>
      `<td class="num">${k === "risk_label" ? chip(r[k]) : typeof r[k] === "number" ? f(r[k], k === "gdp_pc_ppp" ? 0 : 1) : esc(r[k] ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  };
  $("#cmpInd").onchange = (e) => { state.cmpInd = e.target.value; draw(); };
  await draw();
}

// ================================================================== METHODOLOGY
async function vMethod(main) {
  const d = await cached("/api/methodology");
  const m = state.meta;
  const flow = [["Data", `${m.variables} variables · World Bank WDI & WGI · IMF WEO`], ["Real-time", "Oil, VIX, yields, dollar, gold, 36 currencies, 9 equity indices"],
    ["Pattern", `K-Means, k=${d.cluster.k} by silhouette (${f(d.cluster.silhouette, 3)})`], ["Forecast", "5-model ensemble: naive · drift · damped Holt · trend + cross-country gradient-boosting model; conformal intervals"],
    ["Validate", `Learn on ${d.design.fit_origins}, test on held-out ${d.design.heldout_origins}`], ["Risk · Policy · AI", "12 areas, 31 red flags, playbook, scenario model, grounded Qwen agent"]];
  main.innerHTML = `<div class="view">
    ${head("Transparency", "Methodology & data", "How every number is produced, validated and explained — so a minister, a judge or an auditor can trust it.", `Pipeline run ${esc(m.generated_utc)} UTC`)}
    <div class="flow">${flow.map(([t, s], i) => `<div class="card" style="animation:viewIn .4s ${i * 0.07}s both"><div class="n">${i + 1}</div><b>${t}</b><div class="hint" style="margin-top:4px">${esc(s)}</div></div>`).join("")}</div>
    <div class="grid" style="margin-top:16px">
      <div class="card c7"><div class="card-head"><h2>Forecast validation · held-out</h2></div><div class="tbl-wrap" id="bt"></div>
        <div class="note" style="margin-top:10px">Skill = 1 − error ÷ naive error. GDP forecasts beat the "no change" benchmark; labour-market ratios mostly don't, so the ensemble learns to lean on it. We report this openly.</div></div>
      <div class="card c5"><div class="card-head"><h2>80% interval coverage by horizon</h2></div><div id="cov" class="chart"></div></div>
      <div class="card c12"><div class="card-head"><h2>Real-time layer</h2></div><div class="grid">
        <div class="c4 note"><b>Nowcast</b><br>Mean of the AsiaPulse ensemble and IMF WEO for the current year + live oil adjustment (Policy-Lab elasticity × Brent 30-day vs prior-12-month move × share of year left).</div>
        <div class="c4 note"><b>Market stress (0–100)</b><br>Currency depreciation & volatility, equity drawdown, oil exposure (importer vs exporter) and VIX. Pegged currencies excluded.</div>
        <div class="c4 note"><b>Live risk</b><br>70% structural vulnerability + 30% market stress. Market data refresh every 15 minutes; the monitor auto-refreshes every 60 s.</div></div></div>
      <div class="card c12"><div class="card-head"><h2>Red-flag rules</h2><span class="hint">${d.flags.length} rules · absolute thresholds with a stated basis</span></div><div class="tbl-wrap" id="fl"></div></div>
      <div class="card c6"><div class="card-head"><h2>Risk areas</h2></div><div class="tbl-wrap" id="pl"></div></div>
      <div class="card c6"><div class="card-head"><h2>Data sources</h2><input class="input" id="srcQ" placeholder="Search…"></div><div class="tbl-wrap" id="src"></div></div>
      <div class="card c12"><div class="card-head"><h2>Responsible AI & limitations</h2></div><div class="grid">
        ${[["Coverage", Object.entries(d.excluded).map(([k, v]) => `${k}: ${v}`).join(" ")], ["Relative index", "Vulnerability ranks economies within Asia; “Low” is not an absolute all-clear."],
          ["No imputation for scoring", "Every value keeps its year; stale values are treated as missing."], ["Scenario model", "Small structural model with editable assumptions — explores direction & magnitude, not a forecast."],
          ["Grounded AI", "The LLM never computes numbers; every number it writes is verified against tool outputs."], ["Market data", "Public endpoint without an SLA; cached values are flagged when stale."]]
          .map(([t, s]) => `<div class="c4"><b>${t}</b><div class="hint">${esc(s)}</div></div>`).join("")}</div></div>
    </div></div>`;
  $("#bt").innerHTML = `<table><thead><tr><th>Series</th><th>Median error</th><th>Median skill vs naive</th><th>Share beating naive</th><th>80% coverage</th><th>Before calibration</th></tr></thead><tbody>
    ${d.backtest_overall.map((r) => `<tr><td><b>${esc(r.series)}</b></td><td class="num">${f(r.median_error, 2)} ${r.series.startsWith("gdp") ? "%" : "pp"}</td>
    <td class="num ${r.median_skill > 0 ? "up" : "down"}">${sgn(r.median_skill, 2)}</td><td class="num">${f(r.share_beating_naive * 100, 0, "%")}</td>
    <td class="num">${f(r.coverage80 * 100, 0, "%")}</td><td class="num">${f(d.calibration[r.series].coverage_raw_heldout * 100, 0, "%")}</td></tr>`).join("")}</tbody></table>`;
  const ser = [...new Set(d.by_horizon.map((r) => r.series))];
  chart($("#cov"), {
    grid: { left: 8, right: 16, top: 30, bottom: 8, containLabel: true }, legend: { top: 0 }, tooltip: { trigger: "axis", valueFormatter: (v) => f(v * 100, 0, "%") },
    xAxis: axis({ type: "category", data: [1, 2, 3, 4, 5].map((h) => `${h}y`), splitLine: { show: false } }),
    yAxis: axis({ type: "value", min: 0.4, max: 1, axisLabel: { formatter: (v) => `${Math.round(v * 100)}%`, color: css("--muted") } }),
    series: ser.map((s, j) => ({ name: s, type: "line", data: d.by_horizon.filter((r) => r.series === s).map((r) => r.coverage80), symbolSize: 7, lineStyle: { width: 2.5 },
      ...(j === 0 ? { markLine: { symbol: "none", data: [{ yAxis: 0.8 }], lineStyle: { type: "dashed", color: css("--muted") }, label: { formatter: "target 80%", color: css("--muted") } } } : {}) })),
  });
  $("#fl").innerHTML = `<table><thead><tr><th>Flag</th><th>Area</th><th>Rule</th><th>Basis</th></tr></thead><tbody>${d.flags.map((x) => `<tr><td><b>${esc(x.text)}</b></td><td><span class="tag">${esc(x.area)}</span></td><td><code>${esc(x.rule)}</code></td><td style="white-space:normal">${esc(x.basis)}</td></tr>`).join("")}</tbody></table>`;
  $("#pl").innerHTML = `<table><thead><tr><th>Area</th><th>Indicators (+ higher is better / − higher is worse)</th></tr></thead><tbody>${d.pillars.map((p) => `<tr><td><b>${esc(p.area)}</b></td><td style="white-space:normal">${p.indicators.map((i) => `<span class="tag">${i.dir > 0 ? "+" : "−"} ${esc(i.label)}</span>`).join("")}</td></tr>`).join("")}</tbody></table>`;
  const drawSrc = () => {
    const q = ($("#srcQ").value || "").toLowerCase();
    $("#src").innerHTML = `<table><thead><tr><th>Variable</th><th>Area</th><th>Code</th><th>Source</th><th>Economies</th><th>Latest</th></tr></thead><tbody>${d.sources.filter((s) => !q || `${s.label} ${s.code} ${s.area}`.toLowerCase().includes(q)).map((s) => `<tr><td>${esc(s.label || s.key)}</td><td>${esc(s.area || "")}</td><td><code>${esc(s.code)}</code></td><td>${esc(s.source || "")}</td><td class="num">${s.countries ?? ""}</td><td class="num">${s.latest_year ?? ""}</td></tr>`).join("")}</tbody></table>`;
  };
  drawSrc(); $("#srcQ").oninput = drawSrc;
}

// ------------------------------------------------------------------ boot
(async function boot() {
  setThemeIcon(); buildRail();
  state.meta = await API("/api/meta");
  if (!state.meta.countries.find((c) => c.iso3 === state.iso)) state.iso = "PAK";
  $("#curName").textContent = name(state.iso);
  refreshTicker(); setInterval(refreshTicker, 60000);
  render();
})();
