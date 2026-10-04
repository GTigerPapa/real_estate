/* 관심 단지 실거래 — 모바일 웹앱. 데이터: data/app.json (scripts/export_web.py 가 생성).
   금액 단위: 만원. 화면에는 억으로 표시. 외부 라이브러리 없음(SVG 차트 직접 그림). */
"use strict";

// ───── 유틸 ─────
const $ = (sel, el = document) => el.querySelector(sel);
const SLOT = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)", "var(--s7)", "var(--s8)"];  // 8색 검증 (dataviz validate_palette, 라이트·다크)
const WIDE = window.matchMedia("(min-width: 1024px)");  // app.css 의 PC 레이아웃 기준과 같게 유지
const store = {
  get(k, d) { try { const v = localStorage.getItem("re." + k); return v === null ? d : v; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("re." + k, v); } catch (e) { /* 저장 불가 환경 무시 */ } },
};
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") el.setAttribute("style", v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const NS = "http://www.w3.org/2000/svg";
function s(tag, attrs) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, v);
  return el;
}
const eok = (manwon, digits = 2) => {
  if (manwon === null || manwon === undefined) return "–";
  const v = manwon / 10000;
  let txt = Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(digits);
  if (txt.includes(".")) txt = txt.replace(/0+$/, "").replace(/\.$/, "");  // 소수 끝 0만 제거 (20 → 20, 20.50 → 20.5)
  return txt + "억";
};
const signed = (txt, v) => (v > 0 ? "+" : v < 0 ? "−" : "") + txt;
const eokSigned = (manwon) => (manwon === null || manwon === undefined) ? "–" : signed(eok(Math.abs(manwon)), manwon);
const pct = (v, d = 1) => (v === null || v === undefined) ? "–" : v.toFixed(d) + "%";
const pctSigned = (v) => (v === null || v === undefined) ? "–" : signed(Math.abs(v).toFixed(1) + "%", v);
const ymDate = (ym) => { const [y, m] = ym.split("-").map(Number); return Date.UTC(y, m - 1, 15); };
const dDate = (d) => { const [y, m, dd] = d.split("-").map(Number); return Date.UTC(y, m - 1, dd); };
const fmtYM = (t) => { const d = new Date(t); return `${String(d.getUTCFullYear()).slice(2)}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`; };
const fmtMD = (t) => { const d = new Date(t); return `${String(d.getUTCMonth() + 1).padStart(2, "0")}.${String(d.getUTCDate()).padStart(2, "0")}`; };
const fmtYMD = (t) => { const d = new Date(t); return `${d.getUTCFullYear()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}.${String(d.getUTCDate()).padStart(2, "0")}`; };
const dotted = (s) => (s || "").replaceAll("-", ".");

// ───── 차트 (SVG) ─────
// series: {name, color, kind: line|dots|bar, pts: [{t, v, n?, tip?}], shape?, width?, dash?, group?}
// dash: 점선. group: 같은 group 의 선들은 툴팁에서 한 줄로 묶는다 (예: 단지별 매매 / 전월세).
// opts.legendItems: [{name, color, kind, dash?}] 로 범례를 직접 지정 (단지 색 + 선 모양 설명 따로 보여줄 때)
// 선은 값이 없는 달을 건너뛰어 앞뒤를 직선으로 잇는다. 막대는 같은 t 끼리 누적.
function niceTicks(lo, hi, count = 4) {
  if (!(hi > lo)) { hi = lo + 1; }
  const raw = (hi - lo) / count, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => st >= raw) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}
function Chart(opts) {
  const wrap = h("div", { class: "chart" });
  const series = opts.series.filter((se) => se.pts.some((p) => p.v !== null && p.v !== undefined));
  if (!series.length) { wrap.append(h("div", { class: "empty" }, opts.emptyText || "표시할 데이터가 없습니다")); return wrap; }
  const legendIcon = (se) => se.dash ? h("i", { class: "dl", style: `border-color:${se.color}` })
    : h("i", { class: se.kind === "line" ? "l" : se.kind === "bar" ? "b" : "d", style: `background:${se.color}` });
  if (opts.legendItems) {
    wrap.append(h("div", { class: "legend" }, opts.legendItems.map((it) => it.sep ? h("span", { class: "sep" })
      : h("span", {}, legendIcon(it), it.name))));
  } else if (series.length > 1 || opts.legend) {
    wrap.append(h("div", { class: "legend" }, series.filter((se) => !se.noLegend).map((se) =>
      h("span", {}, legendIcon(se), se.name))));
  }
  const holder = h("div", { style: "position:relative" });
  wrap.append(holder);
  const tip = h("div", { class: "tip", hidden: true });
  holder.append(tip);
  const M = { l: 40, r: 10, t: 10, b: 24 };
  let H = opts.height || 190;

  function draw() {
    const W = Math.max(260, holder.clientWidth || 320);
    H = Math.round((opts.height || 190) * (WIDE.matches ? 1.3 : 1));  // PC에선 그래프를 조금 더 높게
    holder.querySelectorAll("svg").forEach((x) => x.remove());
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": opts.label || "" });
    const [t0, t1] = opts.xDomain;
    const X = (t) => M.l + ((t - t0) / (t1 - t0)) * (W - M.l - M.r);

    // y 범위
    const stackTot = {};
    let lo = Infinity, hi = -Infinity;
    for (const se of series) for (const p of se.pts) {
      if (p.v === null || p.v === undefined || p.t < t0 || p.t > t1) continue;
      if (se.kind === "bar") { stackTot[p.t] = (stackTot[p.t] || 0) + p.v; hi = Math.max(hi, stackTot[p.t]); lo = Math.min(lo, 0); }
      else { lo = Math.min(lo, p.v); hi = Math.max(hi, p.v); }
    }
    for (const r of opts.refs || []) { lo = Math.min(lo, r.v); hi = Math.max(hi, r.v); }
    if (opts.yMin !== undefined) lo = Math.min(lo, opts.yMin);
    if (opts.yMax !== undefined) hi = Math.max(hi, opts.yMax);
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.1 || 1;
    let y0 = opts.yMin !== undefined ? opts.yMin : lo - pad, y1 = hi + pad;
    const ticks = niceTicks(y0, y1, opts.yTicks || 4);
    y0 = Math.min(y0, ticks[0]); y1 = Math.max(y1, ticks[ticks.length - 1]);
    const Y = (v) => M.t + (1 - (v - y0) / (y1 - y0)) * (H - M.t - M.b);
    const yf = opts.yFmt || ((v) => String(v));

    // 격자·축
    for (const tv of ticks) {
      svg.append(s("line", { class: "gl", x1: M.l, x2: W - M.r, y1: Y(tv), y2: Y(tv) }));
      const tx = s("text", { x: M.l - 6, y: Y(tv) + 3.5, "text-anchor": "end" }); tx.textContent = yf(tv); svg.append(tx);
    }
    const xt = opts.xTicks ? opts.xTicks(t0, t1) : monthTicks(t0, t1);
    for (const t of xt) {
      svg.append(s("line", { class: "gl", x1: X(t), x2: X(t), y1: M.t, y2: H - M.b }));
      const tx = s("text", { x: X(t), y: H - 6, "text-anchor": "middle" }); tx.textContent = (opts.xFmt || fmtYM)(t); svg.append(tx);
    }
    svg.append(s("line", { class: "ax", x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b }));

    // 막대
    const barSeries = series.filter((se) => se.kind === "bar");
    if (barSeries.length) {
      const allT = [...new Set(barSeries.flatMap((se) => se.pts.map((p) => p.t)))].filter((t) => t >= t0 && t <= t1).sort((a, b) => a - b);
      const step = allT.length > 1 ? X(allT[1]) - X(allT[0]) : 20;
      const bw = Math.max(2, Math.min(18, step * 0.7));
      const acc = {};
      for (const se of barSeries) for (const p of se.pts) {
        if (!p.v || p.t < t0 || p.t > t1) continue;
        const base = acc[p.t] || 0, top = base + p.v; acc[p.t] = top;
        const yTop = Y(top), yBase = Y(base);
        svg.append(s("rect", { x: X(p.t) - bw / 2, y: yTop, width: bw, height: Math.max(0, yBase - yTop - (base ? 1 : 0)),
          style: `fill:${se.color}`, rx: 1.5 }));
      }
    }
    // 기준선
    for (const r of opts.refs || []) {
      svg.append(s("line", { class: "ref", x1: M.l, x2: W - M.r, y1: Y(r.v), y2: Y(r.v) }));
      const tx = s("text", { class: "reft", x: r.left ? M.l + 2 : W - M.r - 2, y: Y(r.v) - 4, "text-anchor": r.left ? "start" : "end" });
      tx.textContent = r.label; svg.append(tx);
    }
    // 점 → 선 (선이 위)
    for (const se of series.filter((x) => x.kind === "dots")) for (const p of se.pts) {
      if (p.v === null || p.t < t0 || p.t > t1) continue;
      const cx = X(p.t), cy = Y(p.v), r = 3.6;
      if (se.shape === "x") {
        svg.append(s("path", { d: `M${cx - r} ${cy - r}L${cx + r} ${cy + r}M${cx - r} ${cy + r}L${cx + r} ${cy - r}`, style: `stroke:${se.color};stroke-width:1.5` }));
      } else if (se.shape === "diamond") {
        svg.append(s("path", { d: `M${cx} ${cy - r - 1}L${cx + r + 1} ${cy}L${cx} ${cy + r + 1}L${cx - r - 1} ${cy}Z`, style: `fill:${se.color};stroke:var(--card);stroke-width:1.2` }));
      } else {
        svg.append(s("circle", { cx, cy, r, style: `fill:${se.color};stroke:var(--card);stroke-width:1.2` }));
      }
    }
    for (const se of series.filter((x) => x.kind === "line")) {
      const pts = se.pts.filter((p) => p.v !== null && p.v !== undefined && p.t >= t0 && p.t <= t1);
      if (!pts.length) continue;
      const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)} ${Y(p.v).toFixed(1)}`).join("");
      svg.append(s("path", { d, style: `fill:none;stroke:${se.color};stroke-width:${se.width || 2};stroke-linejoin:round;stroke-linecap:${se.dash ? "butt" : "round"}` +
        (se.dash ? `;stroke-dasharray:${se.dash === true ? "5 4" : se.dash}` : "") }));
      if (se.endDot !== false) {
        const last = pts[pts.length - 1];
        svg.append(s("circle", { cx: X(last.t), cy: Y(last.v), r: 3.5, style: `fill:${se.color};stroke:var(--card);stroke-width:2` }));
      }
      if (pts.length === 1 && se.endDot === false) svg.append(s("circle", { cx: X(pts[0].t), cy: Y(pts[0].v), r: 3, style: `fill:${se.color}` }));
    }

    // 호버/터치: 점 차트는 가장 가까운 점, 그 외는 가장 가까운 x
    const xh = s("line", { class: "xh", y1: M.t, y2: H - M.b, visibility: "hidden" });
    svg.append(xh);
    const hit = s("rect", { x: M.l, y: 0, width: W - M.l - M.r, height: H, fill: "transparent" });
    svg.append(hit);
    const dotPts = series.filter((x) => x.kind === "dots").flatMap((se) => se.pts.filter((p) => p.v !== null && p.t >= t0 && p.t <= t1).map((p) => ({ ...p, se })));
    const keyT = [...new Set(series.filter((x) => x.kind !== "dots").flatMap((se) => se.pts.filter((p) => p.v !== null && p.v !== undefined && p.t >= t0 && p.t <= t1).map((p) => p.t)))].sort((a, b) => a - b);
    function show(evt) {
      const rect = svg.getBoundingClientRect();
      const px = (evt.clientX - rect.left) * (W / rect.width), py = (evt.clientY - rect.top) * (H / rect.height);
      tip.replaceChildren();
      let anchorX;
      let best = null, bd = Infinity;
      for (const p of dotPts) { const dd = Math.hypot(X(p.t) - px, (Y(p.v) - py) * 0.6); if (dd < bd) { bd = dd; best = p; } }
      if (best && (bd < 28 || !keyT.length)) {
        anchorX = X(best.t);
        tip.append(h("div", { class: "t" }, fmtYMD(best.t)));
        tip.append(h("div", { class: "row" }, h("i", { style: `background:${best.se.color};height:8px;width:8px;border-radius:4px` }),
          h("b", {}, (opts.tipFmt || yf)(best.v)), h("span", {}, best.tip || best.se.name)));
      } else if (keyT.length) {
        let t = keyT[0];
        for (const k of keyT) if (Math.abs(X(k) - px) < Math.abs(X(t) - px)) t = k;
        anchorX = X(t);
        tip.append(h("div", { class: "t" }, (opts.tipDate || fmtYM)(t)));
        const groups = new Map();   // group 이 있는 선은 한 줄에 "값1 / 값2 이름"
        for (const se of series.filter((x) => x.kind !== "dots")) {
          const p = se.pts.find((q) => q.t === t);
          if (!p || p.v === null || p.v === undefined) continue;
          const txt = (se.fmt || opts.tipFmt || yf)(p.v);
          if (se.group) {
            const g = groups.get(se.group);
            if (g) { g.b.textContent += " / " + txt; continue; }
            const b = h("b", {}, txt);
            groups.set(se.group, { b });
            tip.append(h("div", { class: "row" }, h("i", { style: `background:${se.color}` }), b, h("span", {}, se.group)));
            continue;
          }
          tip.append(h("div", { class: "row" }, h("i", { style: `background:${se.color}` }),
            h("b", {}, txt), h("span", {}, se.name + (p.n !== undefined ? ` (n=${p.n})` : ""))));
        }
        if (opts.tipNote) tip.append(h("div", { class: "t" }, opts.tipNote));
      } else return;
      xh.setAttribute("x1", anchorX); xh.setAttribute("x2", anchorX); xh.setAttribute("visibility", "visible");
      tip.hidden = false;
      const tw = tip.offsetWidth, sx = anchorX * (rect.width / W);
      tip.style.left = Math.min(Math.max(0, sx + 12 + tw > rect.width ? sx - tw - 12 : sx + 12), Math.max(0, rect.width - tw)) + "px";
    }
    const hide = () => { tip.hidden = true; xh.setAttribute("visibility", "hidden"); };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerdown", show);
    hit.addEventListener("pointerleave", hide);
    holder.prepend(svg);
  }
  requestAnimationFrame(draw);
  new ResizeObserver(() => draw()).observe(holder);
  return wrap;
}
function monthTicks(t0, t1) {
  const span = (t1 - t0) / (30.4 * 864e5), every = span > 90 ? 24 : span > 40 ? 12 : span > 26 ? 6 : span > 10 ? 3 : 1;
  const out = [], d0 = new Date(t0);
  for (let y = d0.getUTCFullYear(), m = d0.getUTCMonth(); ; m++) {
    const t = Date.UTC(y, m, 1);
    if (t > t1) break;
    const dt = new Date(t), mi = dt.getUTCFullYear() * 12 + dt.getUTCMonth();
    if (t >= t0 && mi % every === 0) out.push(t);   // 12·24개월 간격이면 1월에만 (짝수 해)
  }
  return out;
}
function dayTicks(t0, t1) {
  const days = Math.max(1, Math.round((t1 - t0) / 864e5)), step = Math.max(1, Math.ceil(days / 4));
  const out = [];
  for (let t = t0 + 864e5 * Math.ceil(0.5); t <= t1; t += step * 864e5) out.push(Math.round(t / 864e5) * 864e5);
  return out;
}
function Spark(values, color) {
  const W = 300, Hh = 44, pts = values.map((v, i) => [i, v]).filter((p) => p[1] !== null);
  const svg = s("svg", { viewBox: `0 0 ${W} ${Hh}`, preserveAspectRatio: "none", "aria-hidden": "true" });
  if (pts.length < 2) return svg;
  const lo = Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1])), n = values.length - 1;
  const X = (i) => 2 + (i / n) * (W - 6), Y = (v) => 4 + (1 - (v - lo) / ((hi - lo) || 1)) * (Hh - 8);
  svg.append(s("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join(""),
    style: `fill:none;stroke:${color};stroke-width:2;stroke-linejoin:round;vector-effect:non-scaling-stroke` }));
  const last = pts[pts.length - 1];
  svg.append(s("circle", { cx: X(last[0]), cy: Y(last[1]), r: 3, style: `fill:${color}` }));
  return svg;
}

// ───── 데이터 ─────
const state = { data: null, band: store.get("band", "84"), nowView: store.get("nowView", "trades"), range: store.get("range", "36"), offerKind: "all", offerCx: "all",
  cmpView: store.get("cmpView", "all"), cmpDeal: store.get("cmpDeal", "both"), dtlView: "band",
  macroRange: store.get("macroRange", "36"), marketView: store.get("marketView", "mood"), feedKind: "news", ovMode: store.get("ovMode", "region"), ovRegion: store.get("ovRegion", "gangdong"), ovCx: store.get("ovCx", ""), error: null };
async function loadData(force) {
  try {
    const res = await fetch("data/app.json", { cache: force ? "reload" : "no-cache" });
    const ct = res.headers.get("content-type") || "";
    if (!res.ok || !ct.includes("json")) throw new Error(res.status === 200 ? "login" : "HTTP " + res.status);
    const d = await res.json();
    if (d.format !== 1) throw new Error("데이터 형식이 맞지 않습니다");
    state.data = d; state.error = null;
  } catch (e) {
    state.error = e.message === "login" ? "로그인이 만료됐을 수 있습니다. 새로고침해 주세요." : "데이터를 불러오지 못했습니다 (" + e.message + ")";
  }
}
const cx = (id) => state.data.complexes.find((c) => c.id === id);
const colorOf = (c) => SLOT[c.slot % SLOT.length];
function monthsView() {
  const m = state.data.months, n = state.range === "12" ? 12 : m.length;
  return m.slice(m.length - n);
}
function xDomain(months) { return [ymDate(months[0]) - 20 * 864e5, ymDate(months[months.length - 1]) + 20 * 864e5]; }
const seriesPts = (obj, months, all) => all.map((ym, i) => ({ t: ymDate(ym), v: obj.v[i], n: obj.n ? obj.n[i] : undefined }))
  .filter((p) => months.includes(new Date(p.t).toISOString().slice(0, 7)));
// 아실 일별 매물 수 (열 형식: d 날짜, s 매매, j 전세, w 월세)
// 시계열 A = {d, s, j, w}: 단지 전체(c.asil, 아실 일별 매물 수 3년치) 또는 평형별(c.asil_b[band], 매물 목록 추적)
function serLast(A) {
  if (!A || !A.d.length) return null;
  const i = A.d.length - 1;
  return { d: A.d[i], sale: A.s[i], jeonse: A.j[i], wolse: A.w[i], i };
}
// 7일 전(그날 기록이 없으면 그 이전 가장 가까운 날) 대비 증감. 7일치가 안 쌓였으면 null
function serDelta(A, key, days = 7) {
  const last = serLast(A); if (!last) return null;
  const target = dDate(last.d) - days * 864e5;
  for (let i = last.i - 1; i >= 0; i--) if (dDate(A.d[i]) <= target) return A[key][last.i] - A[key][i];
  return null;
}
const serPts = (A, key) => A.d.map((d, i) => ({ t: dDate(d), v: A[key][i] }));
const bandSer = (c, band) => (c.asil_b && c.asil_b[band]) || null;
const asilLast = (c) => serLast(c.asil);
const asilPts = (c, key) => serPts(c.asil, key);
const wkTxt = (A, k) => { const v = serDelta(A, k); return v === null ? "" : ` (${v > 0 ? "+" : ""}${v})`; };

// ───── 화면 ─────
function header(title, sub, withRefresh = true) {
  const btn = withRefresh ? h("button", { class: "iconbtn", "aria-label": "새로고침", onclick: async (e) => {
    const b = e.currentTarget; b.classList.add("spin"); await loadData(true); b.classList.remove("spin"); render();
  } }, svgIcon("M20 12a8 8 0 1 1-2.34-5.66M20 4v4h-4")) : null;
  return h("div", { class: "top" }, h("div", {}, h("h1", {}, title), sub ? h("div", { class: "sub" }, sub) : null), btn);
}
function svgIcon(d) { const v = s("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" }); v.append(s("path", { d })); return v; }
function bandSeg(bands, current, onPick) {
  return h("div", { class: "seg", role: "group", "aria-label": "평형" }, bands.map((b) =>
    h("button", { "aria-pressed": String(b === current), onclick: () => onPick(b) }, `${b}형`)));
}
function updatedLine() {
  const d = state.data;
  return `실거래 ~${dotted(d.data_through).slice(2)} · 아실 매물 ${d.asil_through ? dotted(d.asil_through).slice(5) : "없음"}`;
}

function Home() {
  // 단지 탭: 관심 단지 목록만 — 누르면 단지 상세로
  const d = state.data, band = d.bands.includes(state.band) ? state.band : "84";
  const list = d.complexes.filter((c) => c.bands.includes(band));
  const others = d.complexes.filter((c) => !c.bands.includes(band));
  return h("div", {},
    header("관심 단지", updatedLine()),
    bandSeg(d.bands, band, (b) => { state.band = b; store.set("band", b); render(); }),
    h("div", { class: "cards" }, list.map((c) => Card(c, band))),
    others.length ? h("div", { class: "others" }, h("div", { class: "others-h" }, `${band}형이 없는 단지`),
      others.map((c) => h("a", { class: "cardmini", href: `#/c/${c.id}/${c.bands[c.bands.length - 1]}` },
        h("span", { class: "dot", style: `background:${colorOf(c)}` }), h("b", {}, c.name), h("span", { class: "area" }, c.area),
        h("span", { class: "bands" }, c.bands.map((b) => b + "형").join(" · ")), h("span", { class: "chev", "aria-hidden": "true" }, "›")))) : null,
    h("p", { class: "hero-sub", style: "margin-top:14px" }, "3개월 중앙값: 직전 3개월 매매(해제·직거래 제외)를 모은 중앙값. 매물 수는 선택한 평형의 아실 매물(같은 물건 1개), 괄호는 1주 전 대비."));
}
// 현황 탭: 관심 단지 전체의 최근 실거래 · 최근 매물 (행을 누르면 그 단지 상세로)
function Now() {
  const d = state.data, band = d.bands.includes(state.band) ? state.band : "84";
  const sub = state.nowView === "offers" ? "offers" : "trades";
  const seg = h("div", { class: "seg", role: "group", "aria-label": "보기" }, [["trades", "실거래"], ["offers", "매물"]].map(([v, t]) =>
    h("button", { "aria-pressed": String(sub === v), onclick: () => { state.nowView = v; store.set("nowView", v); render(); } }, t)));
  return h("div", {},
    header("실거래·매물 현황", updatedLine()),
    seg,
    bandSeg(d.bands, band, (b) => { state.band = b; store.set("band", b); render(); }),
    h("div", { class: "feeds one" }, sub === "trades" ? TradeFeed(band) : OfferFeed(null, band)));
}
const dtxt = (v) => v === null ? null : h("span", { class: "delta" }, v === 0 ? "±0" : (v > 0 ? "+" : "") + v);

// ───── 단지 탭 상단: 전체 단지 최근 실거래 · 최근 매물 표 ─────
const md = (s) => s ? dotted(s).slice(5) : "–";          // 2026-09-28 → 09.28
const ymd2 = (s) => s ? dotted(s).slice(2) : "–";        // → 26.09.28
const daysAgo = (s, base) => (dDate(base) - dDate(s)) / 864e5;
const feedMore = {};                                      // 표별 펼친 줄 수 (새로고침 전까지 유지)
function cxShort(id) { const c = cx(id); return c ? h("span", { class: "cname" }, h("span", { class: "dot", style: `background:${colorOf(c)}` }), c.short) : id; }
function goCx(id) { const c = cx(id); if (c) location.hash = `#/c/${id}/${c.bands.includes(state.band) ? state.band : c.bands[c.bands.length - 1]}`; }
function Feed(key, title, note, chips, head, rows, total, scroll = false) {
  // scroll: 전부 그려 두고 표 안에서 스크롤 (머리글 고정). 아니면 10줄씩 '더 보기'
  const shown = scroll ? rows.length : (feedMore[key] || 10);
  const more = !scroll && rows.length > shown
    ? h("button", { class: "more", onclick: () => { feedMore[key] = shown + 20; render(); } }, `더 보기 (${rows.length - shown}건 더)`) : null;
  return h("section", { class: "section feed" },
    h("div", { class: "feed-h" }, h("h2", {}, title), h("span", { class: "cnt" }, `${total}건`)),
    note ? h("p", { class: "note" }, note) : null, chips,
    h("div", { class: "tscroll" + (scroll ? " fixed" : "") }, h("table", { class: "ftable" }, h("thead", {}, h("tr", {}, head.map((x) => h("th", { class: x.r ? "r" : "" }, x.t)))),
      h("tbody", {}, rows.length ? rows.slice(0, shown) : h("tr", {}, h("td", { colspan: head.length, class: "emptyrow" }, "조건에 맞는 매물이 없습니다"))))),
    more);
}
function TradeFeed(band) {
  const d = state.data, T = (d.trades_recent || []).filter((x) => !band || x.b === band);
  const base = d.generated_at.slice(0, 10);
  const rows = T.map((x) => h("tr", { class: x.x ? "x" : "", onclick: () => goCx(x.c) },
    h("td", {}, cxShort(x.c)),
    h("td", { class: "nw" }, ymd2(x.d), x.pub && x.pub > (d.trades_since || "") && daysAgo(x.pub, base) <= 3 ? h("span", { class: "badge new" }, "NEW") : null),
    h("td", {}, h("span", { class: "sub2" }, `${x.dong ? x.dong + "동 " : ""}${x.f}층 · ${x.ar}㎡`),
      x.t === "direct" ? h("span", { class: "tag" }, "직거래") : null, x.x ? h("span", { class: "tag" }, "해제") : null),
    h("td", { class: "r b" }, eok(x.p))));
  return Feed("trades", `최근 실거래 · ${band}형`, `관심 단지 전체 ${band}형 · 계약일 최신순 · NEW = 최근 3일 안에 새로 신고·공개된 거래 · 국토부 자료에 호수는 없음(동·층까지)`, null,
    [{ t: "단지" }, { t: "계약일" }, { t: "동·층·전용" }, { t: "금액", r: 1 }], rows, T.length, true);
}
const OFFER_T = { sale: "매매", jeonse: "전세", wolse: "월세" };
function offerPrice(o) { return o.t === "wolse" ? `${eok(o.p)}/${o.r ?? "–"}` : eok(o.p); }
// fixedId 가 있으면 그 단지 상세 화면용: 단지 필터·단지 열을 빼고 매물 특징을 함께 보여 준다
function OfferFeed(fixedId, band) {
  const d = state.data, all = (d.offers || []).filter((o) => (!fixedId || o.c === fixedId) && (!band || o.b === band));
  const kKey = fixedId ? "offerKindCx" : "offerKind";
  const kind = state[kKey] || "all", cid = fixedId || state.offerCx || "all";
  const byCx = all.filter((o) => cid === "all" || o.c === cid);
  const tKey = fixedId ? "offerTenCx" : "offerTen", ten = state[tKey] || "all";
  const byKind = byCx.filter((o) => kind === "all" || o.t === kind);
  const tenOf = (o) => o.ten || "none";
  const O = byKind.filter((o) => ten === "all" || (o.t === "sale" && tenOf(o) === ten));
  const since = d.offers_since;
  const cxIds = d.complexes.map((c) => c.id).filter((id) => all.some((o) => o.c === id));
  const pick = (k, v) => () => { state[k] = v; render(); };
  const kindChips = h("div", { class: "chips" }, [["all", "전체"], ["sale", "매매"], ["jeonse", "전세"], ["wolse", "월세"]].map(([v, t]) =>
    h("button", { "aria-pressed": String(kind === v), onclick: pick(kKey, v) },
      t + (v === "all" ? "" : ` ${byCx.filter((o) => o.t === v).length}`))));
  // 매매 매물의 세안고 / 입주 가능 / 언급 없음 (중개사 설명 문구 기준)
  const saleList = byCx.filter((o) => o.t === "sale");
  const tenChips = (kind === "all" || kind === "sale") && saleList.length ? h("div", { class: "chips" },
    [["all", "매매 전체"], ["t", "세안고"], ["m", "입주 가능"], ["none", "언급 없음"]].map(([v, t]) =>
      h("button", { "aria-pressed": String(ten === v), onclick: pick(tKey, v) },
        t + (v === "all" ? "" : ` ${saleList.filter((o) => tenOf(o) === v).length}`)))) : null;
  const chips = fixedId ? h("div", {}, kindChips, tenChips) : h("div", {},
    h("div", { class: "chips" }, [["all", "전체 단지", all.length], ...cxIds.map((id) => [id, cx(id).short, all.filter((o) => o.c === id).length])].map(([v, t, n]) =>
      h("button", { "aria-pressed": String(cid === v), onclick: pick("offerCx", v) },
        v === "all" ? t : h("span", { class: "cname" }, h("span", { class: "dot", style: `background:${colorOf(cx(v))}` }), `${t} ${n}`)))),
    kindChips, tenChips);
  const rows = O.map((o) => {
    const down = o.prev && o.p < o.prev, up = o.prev && o.p > o.prev;
    const fresh = since && o.seen > since;   // 추적 시작 뒤 처음 나타난 매물 = 실제 신규 등록
    return h("tr", { onclick: fixedId ? null : () => goCx(o.c), class: fixedId ? "static" : "", title: o.desc || "" },
      fixedId ? null : h("td", {}, cxShort(o.c)),
      h("td", { class: "nw" }, h("span", { class: `kind k-${o.t}` }, OFFER_T[o.t] || o.t), " ", h("b", {}, offerPrice(o)),
        o.chg ? h("span", { class: `badge ${down ? "dn" : up ? "upb" : ""}` }, `${down ? "▼" : up ? "▲" : "변경"} ${md(o.chg)}`) : null),
      h("td", {}, h("span", { class: "sub2" }, `${o.dong ? o.dong + "동 " : ""}${o.f ? o.f + "층" : ""}${o.ar ? " · " + o.ar + "㎡" : ""}`),
        o.n > 1 ? h("span", { class: "tag" }, `${o.n}곳`) : null,
        o.t === "sale" && o.ten === "t" ? h("span", { class: "tag ten-t" }, "세안고") : null,
        o.t === "sale" && o.ten === "m" ? h("span", { class: "tag ten-m" }, "입주 가능") : null,
        fixedId && o.desc ? h("div", { class: "desc" }, o.desc) : null),
      h("td", { class: "nw" }, fresh ? h("span", {}, md(o.seen), h("span", { class: "badge new" }, "신규")) : md(o.reg)));
  });
  const note = (fixedId ? `이 단지 아실 매물 · ${band}형 · ` : `아실 매물 목록 · ${band}형 · `) +
    `최근 날짜순 · 같은 물건을 여러 중개사가 올리면 1줄(N곳) · ▼▲ 가격 변경일. ` +
    `날짜: '신규'는 ${md(since)} 추적 시작 뒤 처음 나타난 날(실제 등록일), 그 외는 아실 게시일(중개사가 광고를 다시 올린 날이라 최근 날짜에 몰림) · ` +
    `세안고·입주 가능은 중개사 설명 문구로 가린 것(언급 없는 매물이 절반 넘음)`;
  const head = [{ t: "가격" }, { t: fixedId ? "동·층·전용 · 특징" : "동·층·전용" }, { t: "게시일" }];
  const anyOffers = (d.offers || []).length > 0;
  return Feed(fixedId ? "offers-" + fixedId : "offers", `최근 매물 · ${band}형`,
    all.length ? note : !anyOffers ? "아직 매물 목록이 없습니다. Mac의 매일 자동 수집(install_asil_offers.py)을 켜면 쌓입니다."
      : `지금 올라온 ${band}형 아실 매물이 없습니다.`,
    all.length ? chips : null, fixedId ? head : [{ t: "단지" }, ...head], rows, O.length, true);
}
function Card(c, band) {
  const b = c.b[band], sm = b.summary, B = bandSer(c, band), L = serLast(B);
  return h("a", { class: "card", href: `#/c/${c.id}/${band}` },
    h("div", { class: "card-h" }, h("span", { class: "dot", style: `background:${colorOf(c)}` }), h("b", {}, c.name),
      h("span", { class: "area" }, c.area), h("span", { class: "chev", "aria-hidden": "true" }, "›")),
    h("div", { class: "hero" }, sm.median ? eok(sm.median).replace("억", "") : "–", h("small", {}, "억")),
    h("div", { class: "hero-sub" }, `3개월 중앙값 · ${dotted(sm.ym || "")} · n=${sm.n}`,
      sm.n > 0 && sm.n < 3 ? h("span", { class: "warn" }, " ⚠ 표본 적음") : null),
    h("div", { class: "kv" },
      h("div", {}, h("span", {}, "1년 전 대비"), h("b", {}, pctSigned(sm.yoy_pct))),
      h("div", {}, h("span", {}, `상한 ${eok(d0().cap)} 대비`), h("b", {}, eokSigned(sm.vs_cap))),
      h("div", {}, h("span", {}, "전세가율"), h("b", {}, pct(sm.ratio)))),
    h("div", { class: "spark" }, Spark(b.trade_3m.v, colorOf(c))),
    L ? h("div", { class: "lrow" }, h("span", { class: "lbl" }, `${band}형 매물 ${dotted(L.d).slice(5)}`),
      h("span", {}, "매매 ", h("b", {}, L.sale), dtxt(serDelta(B, "s"))),
      h("span", {}, "전세 ", h("b", {}, L.jeonse), dtxt(serDelta(B, "j"))),
      h("span", {}, "월세 ", h("b", {}, L.wolse), dtxt(serDelta(B, "w"))))
      : h("div", { class: "lrow" }, h("span", { class: "lbl" }, `${band}형 매물 데이터 없음`)));
}
const d0 = () => state.data;

function rangeChips() {
  return h("div", { class: "chips" }, [["12", "1년"], ["36", "3년"]].map(([v, t]) =>
    h("button", { "aria-pressed": String(state.range === v), onclick: () => { state.range = v; store.set("range", v); render(); } }, t)));
}
function Section(title, note, ...kids) {
  return h("section", { class: "section" }, h("h2", {}, title), note ? h("p", { class: "note" }, note) : null, ...kids);
}
// PC 레이아웃에서 2열 격자의 한 줄 전체를 쓰는 섹션 (모바일에선 차이 없음)
const wide = (el) => { el.classList.add("wide"); return el; };

function Detail(id, band) {
  const d = state.data, c = cx(id);
  if (!c) return h("div", { class: "empty" }, "단지를 찾을 수 없습니다");
  if (!c.bands.includes(band)) band = c.bands[c.bands.length - 1];
  const b = c.b[band], sm = b.summary, months = monthsView(), all = d.months;
  // 가격·전세·거래량·단지 전체 매물 차트가 같은 시간축을 쓰도록 실거래 월 범위와 아실 일별 범위를 합친다
  const X = (() => {
    const [a0, a1] = xDomain(months), A = c.asil && c.asil.d.length ? c.asil : null;
    if (!A) return [a0, a1];
    const t1 = dDate(A.d[A.d.length - 1]), t0 = Math.max(dDate(A.d[0]), t1 - (state.range === "12" ? 365 : 3 * 365 + 1) * 864e5);
    return [Math.min(a0, t0 - 5 * 864e5), Math.max(a1, t1 + 5 * 864e5)];
  })();
  const cap = d.cap;
  const back = h("div", { class: "back" },
    h("button", { class: "iconbtn", "aria-label": "뒤로", onclick: () => { history.length > 1 ? history.back() : (location.hash = "#/"); } },
      svgIcon("M15 5l-7 7 7 7")),
    h("span", { class: "dot", style: `background:${colorOf(c)}` }), h("h1", {}, c.name));

  const deals = b.deals.filter((x) => months.includes(x.d.slice(0, 7)));
  const tradeChart = Chart({
    label: "매매 실거래와 3개월 중앙값", xDomain: X, height: 220, yFmt: (v) => eok(v, 0), tipFmt: (v) => eok(v),
    refs: [{ v: cap, label: `상한 ${eok(cap)}` }],
    series: [
      { name: "중개거래", kind: "dots", color: "var(--broker)", pts: deals.filter((x) => !x.x && x.t === "broker").map((x) => ({ t: dDate(x.d), v: x.p, tip: `${x.dong ? x.dong + "동 " : ""}${x.f}층 · ${x.ar}㎡` })) },
      { name: "직거래", kind: "dots", shape: "diamond", color: "var(--direct)", pts: deals.filter((x) => !x.x && x.t === "direct").map((x) => ({ t: dDate(x.d), v: x.p, tip: `직거래 · ${x.f}층` })) },
      { name: "해제", kind: "dots", shape: "x", color: "var(--muted)", pts: deals.filter((x) => x.x).map((x) => ({ t: dDate(x.d), v: x.p, tip: `해제 · ${x.f}층` })) },
      { name: "3개월 중앙값", kind: "line", color: "var(--ink)", pts: seriesPts(b.trade_3m, months, all) },
    ],
  });
  const tjChart = Chart({
    label: "매매와 전세 3개월 중앙값", xDomain: X, height: 200, yFmt: (v) => eok(v, 0), tipFmt: (v) => eok(v),
    refs: [{ v: cap, label: `상한 ${eok(cap)}` }],
    series: [
      { name: "매매", kind: "line", color: "var(--ink)", pts: seriesPts(b.trade_3m, months, all) },
      { name: "전세 (신규)", kind: "line", color: "var(--jeonse)", pts: seriesPts(b.jeonse_3m, months, all) },
    ],
  });
  const ratioChart = Chart({
    label: "전세가율", xDomain: X, height: 170, yFmt: (v) => v + "%", tipFmt: (v) => v.toFixed(1) + "%",
    series: [{ name: "전세가율", kind: "line", color: colorOf(c), pts: seriesPts(b.ratio_3m, months, all) },
      { name: "갱신 비율", kind: "line", color: "var(--broker)", width: 1.5, endDot: false,
        pts: seriesPts(b.renew_ratio_3m, months, all), fmt: (v) => v + "%" }],
    legend: true,
  });
  const volChart = Chart({
    label: "월별 거래량", xDomain: X, height: 150, yMin: 0, yFmt: (v) => String(v), tipFmt: (v) => v + "건", yTicks: 3,
    series: [
      { name: "중개", kind: "bar", color: "var(--broker)", pts: months.map((m) => ({ t: ymDate(m), v: b.volume.broker[all.indexOf(m)] })) },
      { name: "직거래", kind: "bar", color: "var(--direct)", pts: months.map((m) => ({ t: ymDate(m), v: b.volume.direct[all.indexOf(m)] })) },
      { name: "해제", kind: "bar", color: "var(--muted)", pts: months.map((m) => ({ t: ymDate(m), v: b.volume.canceled[all.indexOf(m)] })) },
    ],
  });

  // 아실 매물: ① 선택한 평형(매물 목록 추적으로 센 일별 수, 추적 시작일부터) ② 단지 전체 3년(아실 일별 매물 수, 평형 구분 없음)
  const lineSeries = (A) => [
    { name: "매매", kind: "line", color: "var(--ink)", width: 1.8, pts: serPts(A, "s") },
    { name: "전세", kind: "line", color: "var(--jeonse)", width: 1.8, pts: serPts(A, "j") },
    { name: "월세", kind: "line", color: "var(--wolse)", width: 1.8, pts: serPts(A, "w") },
  ];
  const B = bandSer(c, band), BL = serLast(B), AL = asilLast(c);
  let bandChart = null;
  if (BL) {
    const t0 = dDate(B.d[0]), t1 = dDate(BL.d), span = Math.max(14, (t1 - t0) / 864e5);  // 쌓인 날이 적어도 2주 폭으로
    const tenSeries = B.st ? [{ name: "매매 중 세안고", kind: "line", color: "var(--ink)", width: 1.5, dash: true, endDot: false, pts: serPts(B, "st") }] : [];
    bandChart = Chart({
      label: `${band}형 아실 매물 수`, xDomain: [t1 - span * 864e5 - 864e5, t1 + 864e5], height: 170, yMin: 0,
      yFmt: (v) => String(v), tipFmt: (v) => v + "건", xTicks: dayTicks, xFmt: fmtMD, tipDate: fmtYMD, series: [...lineSeries(B), ...tenSeries],
    });
  }
  let allChart = null;
  if (AL) {
    allChart = Chart({
      label: "단지 전체 아실 일별 매물 수", xDomain: X, height: 150, yMin: 0, yFmt: (v) => String(v), tipFmt: (v) => v + "건",
      tipDate: fmtYMD, series: lineSeries(c.asil),
    });
  }
  // 한 섹션에서 평형 필터를 따른다: 기본은 선택 평형(추적분), 없거나 사용자가 고르면 단지 전체 3년.
  // 두 출처는 범위가 달라 한 선에 이어 붙이지 않는다 — 추적 목록은 아실 제휴 중개사 매물만이라 단지 전체 수보다 적다.
  const bandSum = (k) => c.bands.reduce((acc, bb) => { const L2 = serLast(bandSer(c, bb)); return acc + (L2 ? L2[k] : 0); }, 0);
  const cover = AL && AL.sale && c.bands.some((bb) => serLast(bandSer(c, bb))) ? Math.round(bandSum("sale") / AL.sale * 100) : null;
  const dView = !BL ? "all" : (state.dtlView === "all" ? "all" : "band");
  const viewChips = h("div", { class: "chips" },
    [["band", `${band}형만 · 추적분`], ["all", "단지 전체 · 3년"]].map(([v, t]) =>
      h("button", { "aria-pressed": String(dView === v), disabled: v === "band" && !BL ? true : null,
        onclick: () => { state.dtlView = v; render(); } }, t)));
  const noBandMsg = c.asil_b && Object.values(c.asil_b).some((x) => x.d.length)
    ? `${band}형은 지금 추적 목록에 올라온 매물이 없습니다.`
    : "이 단지는 아실 매물 목록을 받을 수 없어 평형별 매물 수가 없습니다 (단지 전체 수만 있음)";
  const listingSec = Section(`매물 수 · ${dView === "band" ? band + "형" : "단지 전체"}`,
    dView === "band"
      ? `${dotted(BL.d)} 매매 ${BL.sale}${wkTxt(B, "s")} · 전세 ${BL.jeonse}${wkTxt(B, "j")} · 월세 ${BL.wolse}${wkTxt(B, "w")} · ` +
        `아실 매물 목록에서 ${band}형만 센 수(같은 물건 1개) · ${dotted(B.d[0])}부터 매일 쌓임 · 괄호는 1주 전 대비` +
        (B.st ? ` · 매매 중 세안고 ${B.st[B.st.length - 1]} · 입주 가능 ${B.sm[B.sm.length - 1]} (설명 문구 기준, 점선 = 세안고)` : "") +
        (cover !== null ? ` · 이 목록은 아실 제휴 중개사 매물만이라 단지 전체 매매 ${AL.sale}건 중 약 ${cover}%를 잡음` : "")
      : (!BL ? noBandMsg + " · " : "") + `아실 일별 매물 수 · 2023.09부터 · 전체 면적 합계(아실이 평형별 과거 값을 주지 않음)` +
        (AL ? ` · ${dotted(AL.d)} 매매 ${AL.sale}${wkTxt(c.asil, "s")} · 전세 ${AL.jeonse} · 월세 ${AL.wolse}` : ""),
    viewChips,
    dView === "band" ? bandChart : allChart);
  // 네이버 호가 (북마클릿으로 수집한 날만): 기록이 있을 때만 표시
  const L = c.listings;
  let askSec = null;
  if (L.some((x) => x.sale_min !== null)) {
    const t0 = dDate(L[0].d), t1 = dDate(L[L.length - 1].d), pad = Math.max(2, (t1 - t0) / 864e5 * 0.06) * 864e5;
    askSec = Section("매매 최저 호가 (네이버)", `북마클릿으로 수집한 날만 · ${L.length}회 기록 · 최근 ${dotted(L[L.length - 1].d)}`, Chart({
      label: "매매 최저 호가", xDomain: [t0 - pad, t1 + pad], height: 160, yFmt: (v) => eok(v, 1), tipFmt: (v) => eok(v),
      xTicks: dayTicks, xFmt: fmtMD, tipDate: fmtYMD, refs: [{ v: cap, label: `상한 ${eok(cap)}` }],
      series: [{ name: "매매 최저 호가", kind: "line", color: colorOf(c), pts: L.map((x) => ({ t: dDate(x.d), v: x.sale_min })) }],
    }));
  }

  const recent = b.deals.slice(-15).reverse();
  const table = h("table", { class: "deals" },
    h("thead", {}, h("tr", {}, h("th", {}, "계약일"), h("th", {}, "동·층"), h("th", {}, "전용"), h("th", { class: "r" }, "금액"))),
    h("tbody", {}, recent.map((x) => h("tr", { class: x.x ? "x" : "" },
      h("td", {}, dotted(x.d).slice(2)),
      h("td", {}, `${x.dong ? x.dong + " · " : ""}${x.f}층`, x.t === "direct" ? h("span", { class: "tag", style: "margin-left:4px" }, "직거래") : null),
      h("td", {}, x.ar + "㎡"),
      h("td", { class: "r" }, eok(x.p))))));

  return h("div", {},
    back,
    c.bands.length > 1 ? h("div", { style: "margin-top:8px" }, bandSeg(c.bands, band, (nb) => { state.band = nb; store.set("band", nb); location.replace(`#/c/${id}/${nb}`); })) : null,
    h("div", { class: "hero", style: "margin-top:4px" }, sm.median ? eok(sm.median).replace("억", "") : "–", h("small", {}, "억")),
    h("div", { class: "hero-sub" }, `${band}형 3개월 중앙값 · ${dotted(sm.ym || "")} · n=${sm.n}`, sm.n > 0 && sm.n < 3 ? " ⚠ 표본 적음" : ""),
    h("div", { class: "stats" },
      h("div", {}, h("span", {}, "1년 전 대비"), h("b", {}, pctSigned(sm.yoy_pct))),
      h("div", {}, h("span", {}, `상한 ${eok(cap)} 대비`), h("b", {}, eokSigned(sm.vs_cap))),
      h("div", {}, h("span", {}, `전세 중앙값 (n=${sm.jeonse_n})`), h("b", {}, eok(sm.jeonse))),
      h("div", {}, h("span", {}, "전세가율"), h("b", {}, pct(sm.ratio)))),
    h("div", { style: "margin-top:14px" }, rangeChips()),
    h("div", { class: "sections" },
      wide(Section("매매 실거래", "점: 개별 거래 · 선: 3개월 중앙값(해제·직거래 제외)", tradeChart)),
      wide(listingSec),  // 가격 바로 아래에 같은 폭으로 두어 매물 증감과 가격 흐름을 위아래로 비교
      // 아래 셋도 한 줄 전체 폭 + 같은 시간축 → 위 가격·매물 차트와 세로로 맞춰 비교
      wide(Section("매매 vs 전세", "3개월 중앙값 · 전세는 갱신 계약 제외", tjChart)),
      wide(Section("전세가율 · 갱신 비율", "갱신 비율↑ = 신규 전세 공급 감소 신호 (3개월 표본 5건 이상만)", ratioChart)),
      wide(Section("월별 거래량", null, volChart)),
      askSec ? wide(askSec) : null,
      wide(Section(`최근 거래 · ${band}형`, sm.last_deal ? `최근 정상 거래 ${dotted(sm.last_deal.d)} · ${eok(sm.last_deal.p)}` : null, table)),
      wide(OfferFeed(id, band))));
}

// 단지 비교: 아실 매물 수 추이. 매매 = 실선, 전월세(전세+월세) = 점선, 색 = 단지.
// 보기: 단지 전체(아실 일별 매물 수, 2023.09~) / 선택 평형(아실 매물 목록 추적으로 센 수, 추적 시작일~).
// 아실은 평형별 과거 추이를 주지 않으므로 3년 추세는 단지 전체 값이고, 평형 필터는 '그 평형이 있는 단지'를 고른다.
function OfferTrend(list, band) {
  const view = state.cmpView === "band" ? "band" : "all", deal = ["sale", "rent"].includes(state.cmpDeal) ? state.cmpDeal : "both";
  const pick = (k, v) => () => { state[k] = v; store.set(k, v); render(); };
  const serOf = (c) => view === "band" ? bandSer(c, band) : (c.asil && c.asil.d.length ? c.asil : null);
  const have = list.filter((c) => serLast(serOf(c)));
  const chips = h("div", {},
    h("div", { class: "chips" }, [["all", "단지 전체 · 3년"], ["band", `${band}형만 · 추적분`]].map(([v, t]) =>
      h("button", { "aria-pressed": String(view === v), onclick: pick("cmpView", v) }, t))),
    h("div", { class: "chips" }, [["both", "매매 + 전월세"], ["sale", "매매"], ["rent", "전월세"]].map(([v, t]) =>
      h("button", { "aria-pressed": String(deal === v), onclick: pick("cmpDeal", v) }, t))));
  const title = view === "band" ? `${band}형 매물 수 추이` : "매물 수 추이 · 단지 전체";
  const note = view === "band"
    ? `아실 매물 목록에서 ${band}형만 센 일별 수(같은 물건 1개) · 추적을 시작한 날부터 매일 쌓임 · 실선 매매, 점선 전월세(전세+월세)`
    : `아실 일별 매물 수(2023.09~, 같은 물건 1개)의 7일 평균 · 아실이 평형별 과거 추이를 주지 않아 단지 전체 면적 합계 · ` +
      `${band}형이 있는 단지만 표시 · 실선 매매, 점선 전월세(전세+월세) · 아래 표는 최근일 실제 값`;
  if (!have.length) return Section(title, note, chips, h("div", { class: "empty" }, view === "band"
    ? `${band}형 매물 기록이 아직 없습니다. 매일 아침 매물 목록 수집으로 쌓입니다.` : "아실 매물 기록이 없습니다"));
  const rentPts = (A) => A.d.map((d, i) => ({ t: dDate(d), v: (A.j[i] ?? 0) + (A.w[i] ?? 0) }));
  // 3년 보기는 하루 단위 흔들림이 커서 7일 평균(그날 포함 직전 7일)으로 그린다. 표의 숫자는 원래 값.
  const smooth = view === "all";
  const avg7 = (pts) => {
    if (!smooth) return pts;
    return pts.map((p, i) => {
      let sum = 0, n = 0;
      for (let k = i; k >= 0 && pts[k].t > p.t - 7 * 864e5; k--) { sum += pts[k].v; n++; }
      return { t: p.t, v: Math.round(sum / n * 10) / 10 };
    });
  };
  const series = [];
  for (const c of have) {
    const A = serOf(c), col = colorOf(c);
    if (deal !== "rent") series.push({ name: `${c.short} 매매`, group: c.short, kind: "line", color: col, width: 1.6, endDot: false, pts: avg7(serPts(A, "s")) });
    if (deal !== "sale") series.push({ name: `${c.short} 전월세`, group: c.short, kind: "line", color: col, width: 1.6, dash: true, endDot: false, pts: avg7(rentPts(A)) });
  }
  const t1 = Math.max(...have.map((c) => dDate(serLast(serOf(c)).d)));
  let xDom, xTicks, xFmt;
  if (view === "band") {
    const t0 = Math.min(...have.map((c) => dDate(serOf(c).d[0]))), span = Math.max(14, (t1 - t0) / 864e5);  // 쌓인 날이 적어도 2주 폭
    xDom = [t1 - span * 864e5 - 864e5, t1 + 864e5]; xTicks = dayTicks; xFmt = fmtMD;
  } else {
    const first = Math.min(...have.map((c) => dDate(serOf(c).d[0])));
    const t0 = Math.max(first, t1 - (state.range === "12" ? 365 : 3 * 365 + 1) * 864e5);
    const pad = Math.max(2, (t1 - t0) / 864e5 * 0.02) * 864e5;
    xDom = [t0 - pad, t1 + pad];
  }
  const legendItems = [...have.map((c) => ({ name: c.short, kind: "line", color: colorOf(c) })), { sep: true },
    ...(deal !== "rent" ? [{ name: "매매", kind: "line", color: "var(--ink2)" }] : []),
    ...(deal !== "sale" ? [{ name: "전월세", kind: "line", dash: true, color: "var(--ink2)" }] : [])];
  const chart = Chart({
    label: title, xDomain: xDom, height: 230, yMin: 0, yFmt: (v) => String(v), tipFmt: (v) => (smooth ? String(Math.round(v)) : v) + "건",
    xTicks, xFmt, tipDate: fmtYMD, series, legendItems,
    tipNote: (deal === "both" ? "매매 / 전월세" : deal === "sale" ? "매매" : "전월세") + (smooth ? " · 7일 평균" : ""),
  });
  // 최근일 · 1주 전 대비 한 줄 요약 (색 대신 이름으로도 읽히게)
  const rows = have.map((c) => {
    const A = serOf(c), L = serLast(A), r = (L.jeonse ?? 0) + (L.wolse ?? 0);
    const ds = serDelta(A, "s"), dj = serDelta(A, "j"), dw = serDelta(A, "w");
    const dr = dj === null || dw === null ? null : dj + dw;
    return h("tr", {}, h("td", {}, h("span", { class: "dot", style: `display:inline-block;margin-right:6px;background:${colorOf(c)}` }), c.short),
      h("td", {}, String(L.sale), dtxt(ds)), h("td", {}, String(r), dtxt(dr)), h("td", {}, md(L.d)));
  });
  const table = h("table", { class: "cmp otr" },
    h("thead", {}, h("tr", {}, h("th", {}, "단지"), h("th", {}, "매매 (1주)"), h("th", {}, "전월세 (1주)"), h("th", {}, "기준일"))),
    h("tbody", {}, rows));
  return Section(title, note, chips, chart, table);
}

function Compare() {
  const d = state.data, band = d.bands.includes(state.band) ? state.band : "84";
  const list = d.complexes.filter((c) => c.bands.includes(band)), months = monthsView(), X = xDomain(months);
  const med = Chart({
    label: "단지별 3개월 중앙값", xDomain: X, height: 230, yFmt: (v) => eok(v, 0), tipFmt: (v) => eok(v),
    refs: [{ v: d.cap, label: `상한 ${eok(d.cap)}`, left: true }],
    series: list.map((c) => ({ name: c.short, kind: "line", color: colorOf(c), pts: seriesPts(c.b[band].trade_3m, months, d.months) })),
  });
  const ratio = Chart({
    label: "단지별 전세가율", xDomain: X, height: 190, yFmt: (v) => v + "%", tipFmt: (v) => v.toFixed(1) + "%",
    series: list.map((c) => ({ name: c.short, kind: "line", color: colorOf(c), pts: seriesPts(c.b[band].ratio_3m, months, d.months) })),
  });
  const offers = OfferTrend(list, band);
  const table = h("table", { class: "cmp" },
    h("thead", {}, h("tr", {}, h("th", {}, "단지"), h("th", {}, "중앙값"), h("th", {}, "1년"), h("th", {}, "전세율"),
      h("th", {}, "매물"), h("th", {}, "1주"))),
    h("tbody", {}, list.map((c) => {
      const sm = c.b[band].summary, B = bandSer(c, band), A = serLast(B), dw = serDelta(B, "s");
      return h("tr", {}, h("td", {}, h("span", { class: "dot", style: `display:inline-block;margin-right:6px;background:${colorOf(c)}` }), c.short),
        h("td", {}, eok(sm.median)), h("td", {}, pctSigned(sm.yoy_pct)), h("td", {}, pct(sm.ratio)),
        h("td", {}, A ? String(A.sale) : "–"), h("td", {}, dw === null ? "–" : (dw > 0 ? "+" : dw < 0 ? "−" : "±") + Math.abs(dw)));
    })));
  return h("div", {},
    header("단지 비교", updatedLine()),
    bandSeg(d.bands, band, (b) => { state.band = b; store.set("band", b); render(); }),
    rangeChips(),
    h("div", { class: "sections" },
      Section(`${band}형 매매 3개월 중앙값`, null, med),
      Section(`${band}형 전세가율`, "전세 3개월 중앙값 ÷ 매매 3개월 중앙값", ratio),
      wide(offers),
      wide(Section("요약", `중앙값 = 3개월 매매 중앙값 · 전세율 = 전세가율 · 매물 = ${band}형 아실 매매 매물 수(최근일) · 1주 = 1주 전 대비`, table))));
}

// ───── 매물 × 가격 ─────
// 매물(아실 일별 매물 수)과 가격(실거래)을 같은 시간축에 둔다. 한 차트에 축 두 개를 겹치지 않고,
// 겹쳐 보기는 둘 다 시작 달=100 으로 맞춘 지수로 그린다.
const pctChg = (a, b) => (a && b) ? (b / a - 1) * 100 : null;
function lastValid(arr, upto) { for (let i = Math.min(upto ?? arr.length - 1, arr.length - 1); i >= 0; i--) if (arr[i] !== null && arr[i] !== undefined) return i; return -1; }
function weeklyFromDaily(A) {   // 단지 일별 → 주(일요일 끝) 7일 평균 {d, s, r}
  const out = { d: [], s: [], r: [] };
  if (!A || !A.d.length) return out;
  let bucket = null, ss = 0, rr = 0, n = 0;
  const flush = () => { if (n) { out.d.push(bucket); out.s.push(Math.round(ss / n * 10) / 10); out.r.push(Math.round(rr / n * 10) / 10); } };
  A.d.forEach((d, i) => {
    const t = dDate(d), dow = new Date(t).getUTCDay(), end = new Date(t + ((7 - dow) % 7) * 864e5).toISOString().slice(0, 10);
    if (end !== bucket) { flush(); bucket = end; ss = rr = n = 0; }
    ss += A.s[i]; rr += (A.j[i] ?? 0) + (A.w[i] ?? 0); n++;
  });
  flush();
  return out;
}
function LeadLag(ll, what) {
  if (!ll || ll.r.every((x) => x === null)) return h("div", { class: "empty" }, "상관을 계산할 표본이 부족합니다");
  const rows = ll.k.map((k, i) => {
    const r = ll.r[i];
    const w = r === null ? 0 : Math.min(50, Math.abs(r) * 50);
    const bar = h("div", { class: "llbar" }, h("span", { class: "mid" }),
      r === null ? null : h("i", { class: r < 0 ? "neg" : "pos", style: r < 0 ? `right:50%;width:${w}%` : `left:50%;width:${w}%` }));
    return h("tr", { class: k === ll.best ? "best" : "" }, h("td", {}, k === 0 ? "같은 달" : `${k}개월 뒤`), h("td", { class: "llcell" }, bar),
      h("td", { class: "r" }, r === null ? "–" : (r > 0 ? "+" : r < 0 ? "−" : "") + Math.abs(r).toFixed(2)));
  });
  const bi = ll.k.indexOf(ll.best), br = bi >= 0 ? ll.r[bi] : null;
  const verdict = br === null ? "" : Math.abs(br) < 0.3 ? "뚜렷한 관계 없음"
    : br < 0 ? `매물이 늘면 약 ${ll.best}개월 뒤 가격이 약해지는 경향 (r ${br.toFixed(2)})`
      : `매물과 가격이 ${ll.best ? ll.best + "개월 시차로 " : ""}같은 방향 (r +${br.toFixed(2)}) — 오를 때 매물도 느는 활황형`;
  return h("div", {},
    h("p", { class: "llverdict" }, h("b", {}, what + " · "), verdict),
    h("table", { class: "cmp ll" }, h("thead", {}, h("tr", {}, h("th", {}, "가격 시점"), h("th", { class: "llhead" }, h("span", {}, "− 매물↑ 가격↓"), h("span", {}, "매물↑ 가격↑ +")), h("th", {}, "상관"))),
      h("tbody", {}, rows)),
    h("p", { class: "note" }, `매물(월평균 매매 매물)의 3개월 변화와 그 k개월 뒤 가격(84㎡ 환산 3개월 중앙값)의 3개월 변화 사이 상관 · ` +
      `짝 ${ll.n[0]}개월(3개월 변화끼리 겹쳐 실제 독립 표본은 더 적음) · 신고 기한이 남은 최근 2개월 가격 제외 · 참고용`));
}
function Overlap() {
  const d = state.data, O = d.overlap;
  if (!O || !O.regions) return h("div", {}, header("매물 × 가격", updatedLine()), h("div", { class: "empty" }, "분석 데이터가 아직 없습니다"));
  const mode = state.ovMode === "cx" ? "cx" : "region";
  const pick = (k, v) => () => { state[k] = v; store.set(k, v); render(); };
  const months = monthsView(), all = d.months, X = xDomain(months), mi = months.map((m) => all.indexOf(m));
  let title, wk, lstM, priceV, priceN, priceLabel, vol, ll, color = "var(--s1)", controls;
  if (mode === "region") {
    const R = O.regions.find((r) => r.id === state.ovRegion) || O.regions[0];
    title = R.name; wk = R.wk; lstM = R.lst_m; priceV = R.p84.v; priceN = R.p84.n; vol = R.p84.vol; ll = R.ll;
    priceLabel = "84㎡ 환산 3개월 중앙값";
    const chip = (r) => h("button", { "aria-pressed": String(r.id === R.id), onclick: pick("ovRegion", r.id) }, r.short);
    controls = h("div", {},
      h("div", { class: "chips wrap" }, h("span", { class: "chl" }, "구·시"), O.regions.filter((r) => r.level === "sgg").map(chip)),
      h("div", { class: "chips wrap" }, h("span", { class: "chl" }, "동"), O.regions.filter((r) => r.level === "dong").map(chip)));
  } else {
    const c = cx(state.ovCx) || d.complexes[0], C = O.complexes[c.id] || {};
    const band = c.bands.includes(state.band) ? state.band : (c.bands.includes("84") ? "84" : c.bands[c.bands.length - 1]);
    title = `${c.name} · ${band}형`; color = colorOf(c); wk = weeklyFromDaily(c.asil); lstM = C.lst_m || []; ll = C.ll;
    priceV = c.b[band].trade_3m.v; priceN = c.b[band].trade_3m.n; priceLabel = `${band}형 3개월 중앙값`;
    vol = all.map((_, i) => (c.b[band].volume.broker[i] || 0) + (c.b[band].volume.direct[i] || 0));
    controls = h("div", {},
      h("div", { class: "chips wrap" }, d.complexes.map((x) => h("button", { "aria-pressed": String(x.id === c.id), onclick: pick("ovCx", x.id) },
        h("span", { class: "cname" }, h("span", { class: "dot", style: `background:${colorOf(x)}` }), x.short)))),
      bandSeg(c.bands, band, (b) => { state.band = b; store.set("band", b); render(); }));
  }
  // ① 겹쳐 보기: 보이는 기간 첫 달(둘 다 값 있는 달) = 100
  const base = mi.find((i) => lstM[i] && priceV[i]);
  const idx = (arr) => months.map((m, j) => ({ t: ymDate(m), v: base !== undefined && arr[mi[j]] ? Math.round(arr[mi[j]] / arr[base] * 1000) / 10 : null }));
  const ov = Chart({
    label: "매물과 가격 지수", xDomain: X, height: 230, yFmt: (v) => String(v), tipFmt: (v) => v.toFixed(1),
    refs: [{ v: 100, label: "시작=100", left: true }],
    series: [
      { name: "매매 매물 (월평균)", kind: "line", color: "var(--s2)", width: 2, pts: idx(lstM) },
      { name: `가격 (${priceLabel})`, kind: "line", color: "var(--ink)", width: 2, pts: idx(priceV) },
    ],
  });
  const li = lastValid(lstM), pi = lastValid(priceV, all.length - 3);
  const lchg = li >= 3 ? pctChg(lstM[li - 3], lstM[li]) : null, pchg = pi >= 3 ? pctChg(priceV[pi - 3], priceV[pi]) : null;
  // ② 매물 수 (주별 7일 평균): 매매 실선, 전월세 점선
  const wt = wk.d.map(dDate), t1 = wt.length ? wt[wt.length - 1] : X[1];
  const t0 = Math.max(wt.length ? wt[0] : X[0], t1 - (state.range === "12" ? 365 : 3 * 365 + 1) * 864e5);
  const lstChart = Chart({
    label: "매물 수", xDomain: [t0 - 10 * 864e5, t1 + 10 * 864e5], height: 180, yMin: 0, yFmt: (v) => String(v), tipFmt: (v) => Math.round(v) + "건",
    tipDate: (t) => fmtYMD(t) + " 주",
    series: [
      { name: "매매", kind: "line", color, width: 1.8, endDot: false, pts: wk.d.map((x, i) => ({ t: wt[i], v: wk.s[i] })) },
      { name: "전월세", kind: "line", color, width: 1.6, dash: true, endDot: false, pts: wk.d.map((x, i) => ({ t: wt[i], v: wk.r[i] })) },
    ],
  });
  // ③ 가격 · ④ 거래량
  const priceChart = Chart({
    label: priceLabel, xDomain: X, height: 180, yFmt: (v) => eok(v, 0), tipFmt: (v) => eok(v),
    refs: mode === "cx" ? [{ v: d.cap, label: `상한 ${eok(d.cap)}` }] : [],
    series: [{ name: priceLabel, kind: "line", color: "var(--ink)", pts: months.map((m, j) => ({ t: ymDate(m), v: priceV[mi[j]], n: priceN[mi[j]] })) }],
  });
  const volChart = Chart({
    label: "월별 거래량", xDomain: X, height: 120, yMin: 0, yTicks: 3, yFmt: (v) => String(v), tipFmt: (v) => v + "건",
    series: [{ name: "거래", kind: "bar", color: "var(--broker)", pts: months.map((m, j) => ({ t: ymDate(m), v: vol[mi[j]] })) }],
  });
  // ⑤ 지역 요약표 (지역 모드)
  const table = mode === "region" ? h("table", { class: "cmp" },
    h("thead", {}, h("tr", {}, h("th", {}, "지역"), h("th", {}, "매물 3개월"), h("th", {}, "가격 3개월"), h("th", {}, "가장 강한 관계"))),
    h("tbody", {}, O.regions.map((r) => {
      const a = lastValid(r.lst_m), b = lastValid(r.p84.v, all.length - 3);
      const bi = r.ll.k.indexOf(r.ll.best), br = bi >= 0 ? r.ll.r[bi] : null;
      return h("tr", { onclick: pick("ovRegion", r.id), class: r.id === state.ovRegion ? "sel" : "" },
        h("td", {}, r.short), h("td", {}, pctSigned(a >= 3 ? pctChg(r.lst_m[a - 3], r.lst_m[a]) : null)),
        h("td", {}, pctSigned(b >= 3 ? pctChg(r.p84.v[b - 3], r.p84.v[b]) : null)),
        h("td", {}, br === null ? "–" : `${r.ll.best ? r.ll.best + "개월 뒤" : "같은 달"} ${(br > 0 ? "+" : "−") + Math.abs(br).toFixed(2)}`));
    }))) : null;
  return h("div", {},
    header("매물 × 가격", updatedLine()),
    h("div", { class: "seg", role: "group", "aria-label": "단위" }, [["region", "지역"], ["cx", "단지"]].map(([v, t]) =>
      h("button", { "aria-pressed": String(mode === v), onclick: pick("ovMode", v) }, t))),
    controls, rangeChips(),
    h("div", { class: "sections" },
      wide(Section(`${title} · 겹쳐 보기`, `둘 다 보이는 기간 첫 달 = 100 · 최근 3개월 매물 ${pctSigned(lchg)} · 가격 ${pctSigned(pchg)}` +
        ` (가격은 신고가 덜 끝난 최근 2개월 제외) · 최근 1~2개월 가격은 거래 신고가 늘며 바뀔 수 있음`, ov)),
      Section("매물 수 · 주별 7일 평균", mode === "region" ? "아실 지역 일별 매물 수(같은 물건 1건) · 실선 매매, 점선 전월세" :
        "아실 단지 일별 매물 수(평형 구분 없음) · 실선 매매, 점선 전월세", lstChart),
      Section(`가격 · ${priceLabel}`, mode === "region" ? "지역 전체 아파트 매매(해제 제외)의 ㎡당 가격 × 84 · 그 달 포함 직전 3개월 거래" :
        "해제·직거래 제외 · 그 달 포함 직전 3개월 거래", priceChart),
      Section("선행 관계", mode === "cx" ? "단지 가격은 모든 평형의 84㎡ 환산가로 계산 (표본 확보)" : null, LeadLag(ll, title)),
      Section("월별 거래량", mode === "region" ? "지역 전체 아파트 매매 (해제 제외)" : `${title} (해제 제외)`, volChart),
      table ? wide(Section("지역 한눈에", "매물·가격 = 최근 3개월 변화 · 가장 강한 관계 = 매물 변화 뒤 가격 변화와 상관이 가장 큰 시차 · 줄을 누르면 위 차트가 바뀜", table)) : null));
}

// ───── 시장 > 심리 (네이버 검색량·카페/뉴스·유튜브 + 한국은행 CSI) ─────
function Tile(label, value, sub, tone) {
  return h("div", { class: "stile" }, h("span", { class: "sl" }, label), h("b", { class: tone ? "t-" + tone : "" }, value), h("span", { class: "ss" }, sub));
}
const avgN = (a, n) => a.map((_, i) => { const w = a.slice(Math.max(0, i - n + 1), i + 1).filter((x) => x !== null && x !== undefined); return w.length ? w.reduce((x, y) => x + y, 0) / w.length : null; });
function Sentiment() {
  const d = state.data, S = d.sentiment, M = d.macro || { months: [], v: {} };
  if (!S || !S.wk) return h("div", { class: "empty" }, "심리 데이터가 아직 없습니다. 다음 자동 갱신(매일 아침) 때 채워집니다.");
  const W = S.wk, wt = W.d.map(dDate), hasW = wt.length > 0;
  const span = state.macroRange === "all" ? Infinity : 3 * 365;
  const tEnd = hasW ? wt[wt.length - 1] : Date.now(), t0 = hasW ? Math.max(wt[0], tEnd - span * 864e5) : tEnd - span * 864e5;
  const XW = [t0 - 10 * 864e5, tEnd + 10 * 864e5];
  const g4 = W.greed ? avgN(W.greed, 4) : [];
  const gLast = g4.length ? g4[g4.length - 1] : null;
  const gTop = gLast === null ? null : Math.round(g4.filter((x) => x !== null && x >= gLast).length / g4.filter((x) => x !== null).length * 100);
  const s4 = W.sell ? avgN(W.sell, 4) : [];
  const sChg = s4.length > 13 && s4[s4.length - 13] ? Math.round((s4[s4.length - 1] / s4[s4.length - 13] - 1) * 100) : null;
  const yn = (S.yt || {}).n || [], yLast = yn.length ? yn[yn.length - 1] : null;
  const y30 = yn.slice(-31, -1), yAvg = y30.length ? Math.round(y30.reduce((a, b) => a + b, 0) / y30.length) : null;
  const csiArr = (M.v.csi_house || []).filter((x) => x !== null), csi = csiArr.length ? csiArr[csiArr.length - 1] : null;
  const tiles = h("div", { class: "stiles" },
    Tile("탐욕 / 공포", gLast === null ? "–" : gLast.toFixed(2), gLast === null ? "검색량 수집 전" : `상승÷하락 검색 · 2016년 이후 상위 ${gTop}%`, gLast === null ? "" : gLast > 1 ? "up" : "dn"),
    Tile("주택가격전망CSI", csi === null ? "–" : String(csi), "100 초과 = 오른다 우세", csi === null ? "" : csi > 100 ? "up" : "dn"),
    Tile("급매 검색", sChg === null ? "–" : (sChg > 0 ? "+" : "") + sChg + "%", "최근 4주 vs 3개월 전", sChg === null ? "" : sChg > 0 ? "dn" : "up"),
    Tile("유튜브 새 영상", yLast === null ? "–" : yLast.toLocaleString() + "개", yAvg ? `전날 · 30일 평균 ${yAvg.toLocaleString()}개` : "전날 올라온 부동산 영상 (추정치) · 수집 시작", ""));

  // 주요 글
  const F = S.feed || {}, fk = ["news", "cafe", "yt"].includes(state.feedKind) ? state.feedKind : "news";
  const list = F[fk] || [];
  const feedChips = h("div", { class: "chips" }, [["news", "뉴스"], ["cafe", "카페"], ["yt", "유튜브"]].map(([v, t]) =>
    h("button", { "aria-pressed": String(fk === v), onclick: () => { state.feedKind = v; render(); } }, `${t} ${(F[v] || []).length}`)));
  const items = list.length ? h("ul", { class: "flist" }, list.map((x) => h("li", {},
    h("a", { href: x.u, class: "ft", target: "_blank", rel: "noopener noreferrer" }, x.t),
    h("div", { class: "fm" }, x.g ? h("span", { class: "tag" }, x.g) : null, x.s ? h("span", {}, x.s) : null, x.d ? h("span", {}, x.d) : null,
      x.v ? h("span", {}, "조회 " + (x.v >= 10000 ? (x.v / 10000).toFixed(1) + "만" : x.v.toLocaleString())) : null),
    x.x ? h("p", { class: "fx" }, x.x) : null))) : h("div", { class: "empty" }, "아직 모은 글이 없습니다");
  const feedSec = wide(Section("주요 글", `네이버 뉴스·카페 검색과 유튜브에서 매일 아침 고른 글${F.generated_at ? " · " + F.generated_at.replace("T", " ").slice(5) + " 기준" : ""} · ` +
    "제목을 누르면 원문으로 이동 · 요약은 각 서비스가 주는 미리보기 문구 · 유튜브는 전날 올라온 영상 중 조회수 상위", feedChips, items));

  // 심리와 가격
  const rb = (arr) => { const b = arr.find((p) => p.v !== null && p.v !== undefined); return arr.map((p) => ({ t: p.t, v: b && p.v !== null && p.v !== undefined ? Math.round(p.v / b.v * 1000) / 10 : null })); };
  const mPts = (id) => (M.months || []).map((m, i) => ({ t: ymDate(m), v: (M.v[id] || [])[i] })).filter((p) => p.t >= t0 - 20 * 864e5);
  const over = Chart({ label: "가격과 CSI", xDomain: XW, height: 180, yFmt: (v) => String(v), tipFmt: (v) => v.toFixed(1),
    refs: [{ v: 100, label: "시작=100", left: true }], series: [
      { name: "KB 서울 아파트 매매 (시작=100)", kind: "line", color: "var(--ink)", width: 2.2, pts: rb(mPts("kb_seoul_apt")) },
      { name: "주택가격전망CSI (시작=100)", kind: "line", color: "var(--s1)", width: 1.6, dash: true, endDot: false, pts: rb(mPts("csi_house")) }] });
  const greed = g4.length ? Chart({ label: "탐욕/공포", xDomain: XW, height: 130, yFmt: (v) => v.toFixed(1), tipFmt: (v) => v.toFixed(2), tipDate: fmtYMD, yTicks: 3,
    refs: [{ v: 1, label: "1 = 상승·하락 검색 같음", left: true }], series: [
      { name: "탐욕/공포 (상승÷하락 검색, 4주 평균)", kind: "line", color: "var(--s2)", width: 1.8, pts: wt.map((t, i) => ({ t, v: g4[i] === null ? null : Math.round(g4[i] * 100) / 100 })).filter((p) => p.t >= t0) }] }) : null;
  const overSec = wide(Section("심리와 가격 겹쳐 보기", "위: KB 서울 아파트 매매지수와 주택가격전망CSI (각 선 시작 = 100) · 아래: 탐욕/공포 = 네이버 '상승 기대' ÷ '하락 기대' 검색량 " +
    "(1 초과 = 오른다는 검색이 더 많음) · 같은 시간축", over, greed));

  // 네이버 검색량 (묶음별 각자 최댓값=100)
  const COL = { up: "var(--s2)", down: "var(--s1)", buy: "var(--s3)", sell: "var(--s5)", area: "var(--s4)" };
  const gk = Object.keys(S.groups || {}).filter((k) => W[k]);
  const search = gk.length ? Chart({ label: "네이버 검색량", xDomain: XW, height: 210, yMin: 0, yFmt: (v) => String(v), tipFmt: (v) => v.toFixed(0), tipDate: fmtYMD,
    series: gk.map((k) => { const a = avgN(W[k], 4); return { name: S.groups[k].name, kind: "line", color: COL[k] || "var(--s6)", width: 1.6, endDot: false,
      pts: wt.map((t, i) => ({ t, v: a[i] })).filter((p) => p.t >= t0) }; }) }) : h("div", { class: "empty" }, "검색량 수집 전");
  const groupNote = gk.map((k) => `${S.groups[k].name}(${S.groups[k].kw.join("·")})`).join(" · ");

  // 선행 관계
  const llRows = (S.ll || []).map((L) => {
    const bi = L.k.indexOf(L.best), r = bi >= 0 ? L.r[bi] : null, w = r === null ? 0 : Math.min(50, Math.abs(r) * 50);
    return h("tr", {}, h("td", {}, L.label), h("td", {}, L.best === null ? "–" : L.best ? `${L.best}개월 뒤` : "같은 달"),
      h("td", { class: "llcell" }, h("div", { class: "llbar" }, h("span", { class: "mid" }), r === null ? null :
        h("i", { class: r < 0 ? "neg" : "pos", style: r < 0 ? `right:50%;width:${w}%` : `left:50%;width:${w}%` }))),
      h("td", { class: "r" }, r === null ? "–" : (r > 0 ? "+" : "−") + Math.abs(r).toFixed(2)));
  });
  const ll = llRows.length ? h("table", { class: "cmp ll" }, h("thead", {}, h("tr", {}, h("th", {}, "검색 지표"), h("th", {}, "시차"),
    h("th", { class: "llhead" }, h("span", {}, "−"), h("span", {}, "+")), h("th", {}, "상관"))), h("tbody", {}, llRows)) : h("div", { class: "empty" }, "검색량 수집 전");

  // 카페·뉴스 일별 글 수 / 유튜브 일별 새 영상
  const D = S.daily || { d: [] }, dt = D.d.map(dDate);
  const sum = (...ids) => D.d.map((_, i) => { const xs = ids.map((id) => (D[id] || [])[i]); return xs.some((x) => x === null || x === undefined) ? null : xs.reduce((a, b) => a + b, 0); });
  const nDays = (D.cafe_sell || []).filter((x) => x !== null).length;
  const XD = dt.length ? [dt[0] - 864e5, dt[dt.length - 1] + 864e5] : XW;
  const cafe = nDays >= 2 ? Chart({ label: "카페·뉴스 글 수", xDomain: XD, height: 170, yMin: 0, xTicks: dayTicks, xFmt: fmtMD, tipDate: fmtYMD, yFmt: (v) => String(v), tipFmt: (v) => v + "건", series: [
    { name: "카페 '급매'+'세안고'", kind: "line", color: "var(--s5)", width: 1.8, pts: dt.map((t, i) => ({ t, v: sum("cafe_sell", "cafe_seango")[i] })) },
    { name: "카페 '집값 폭락'", kind: "line", color: "var(--s1)", width: 1.8, pts: dt.map((t, i) => ({ t, v: (D.cafe_crash || [])[i] })) },
    { name: "카페 '집값 폭등'", kind: "line", color: "var(--s2)", width: 1.8, pts: dt.map((t, i) => ({ t, v: (D.cafe_surge || [])[i] })) },
    { name: "뉴스 '부동산 대책'", kind: "line", color: "var(--s3)", width: 1.6, dash: true, pts: dt.map((t, i) => ({ t, v: (D.news_policy || [])[i] })) }] })
    : h("div", { class: "empty" }, `하루 새 글 수는 이틀째부터 계산됩니다 (어제와 오늘 검색 결과 총수의 차이) · ${D.d.length ? dotted(D.d[0]) + " 수집 시작" : "수집 전"}`);
  // 유튜브: 최근 90일은 하루 단위 막대, 1년은 주별 '하루 평균' 선 (주 단위 백필 + 하루 단위를 주로 묶은 값)
  const Y = S.yt || { d: [], n: [] }, YW = S.ytw || { d: [], n: [] };
  const ycut = Y.d.length ? dDate(Y.d[Y.d.length - 1]) - 90 * 864e5 : 0;
  const yd = Y.d.map(dDate), yIdx = yd.map((t, i) => i).filter((i) => yd[i] > ycut);
  const ytc = yIdx.length ? Chart({ label: "유튜브 새 영상 (일별)", xDomain: [yd[yIdx[0]] - 864e5 * (yIdx.length < 7 ? 7 : 1), yd[yd.length - 1] + 864e5], height: 150, yMin: 0,
    xTicks: dayTicks, xFmt: fmtMD, tipDate: fmtYMD, yFmt: (v) => String(v), tipFmt: (v) => v.toLocaleString() + "개",
    series: [{ name: "부동산 주제 새 영상 (유튜브 추정치)", kind: "bar", color: "var(--broker)", pts: yIdx.map((i) => ({ t: yd[i], v: Y.n[i] })) }] }) : h("div", { class: "empty" }, "수집 전");
  const dW = {};   // 하루 단위 값을 월요일 시작 주로 묶음
  yd.forEach((t, i) => { const m = t - ((new Date(t).getUTCDay() + 6) % 7) * 864e5; (dW[m] = dW[m] || { s: 0, c: 0 }); dW[m].s += Y.n[i]; dW[m].c += 1; });
  const wkMap = {};
  for (const m in dW) if (dW[m].c >= 4) wkMap[m] = dW[m].s / dW[m].c;
  YW.d.forEach((w, i) => { wkMap[dDate(w)] = YW.n[i] / 7; });   // 주 단위 백필(7일 합계)
  const wkPts = Object.keys(wkMap).map(Number).sort((a, b) => a - b).map((t) => ({ t: t + 3 * 864e5, v: Math.round(wkMap[t]) }));
  const ytw = wkPts.length >= 8 ? Chart({ label: "유튜브 새 영상 (주별)", xDomain: [wkPts[0].t - 7 * 864e5, wkPts[wkPts.length - 1].t + 7 * 864e5], height: 150, yMin: 0,
    tipDate: (t) => fmtYMD(t - 3 * 864e5) + " 주", yFmt: (v) => String(v), tipFmt: (v) => "하루 평균 " + v.toLocaleString() + "개",
    series: [{ name: "주별 하루 평균 새 영상 (유튜브 추정치)", kind: "line", color: "var(--broker)", width: 1.8, pts: wkPts }] }) : null;

  return h("div", { class: "sections" },
    wide(h("section", { class: "section" }, tiles)),
    feedSec, overSec,
    Section("네이버 검색량 (주별, 4주 평균)", "데이터랩 검색어트렌드 · 묶음마다 2016년 이후 최댓값 = 100 (묶음끼리 높이 비교는 의미 없음, 흐름만) · " + groupNote, search),
    Section("선행 관계 (2016년~)", "검색 지표(월평균) 3개월 변화 vs k(0~12)개월 뒤 KB 서울 아파트 3개월 변화의 상관 중 가장 큰 시차 · 과거 패턴, 예측 아님", ll),
    Section("카페·뉴스 글 수 (일별)", "네이버 카페·뉴스 검색의 하루 새 글 수 (검색 결과 총수의 전일 대비 증가) · 수집 시작일부터 쌓임", cafe),
    Section("유튜브 새 영상", "'부동산·아파트·집값' 주제로 올라온 영상 수 · 위: 최근 1년 주별 하루 평균, 아래: 최근 90일 하루 단위 · " +
      "과거 날짜는 올린 날짜로 거슬러 센 값(지금 남아 있는 영상 기준, 지워진 영상은 빠짐) · 유튜브 검색이 주는 추정치라 흐름만 볼 것", ytw, ytc));
}
function Market() {
  const sub = state.marketView === "mood" ? "mood" : "macro";
  const seg = h("div", { class: "seg", role: "group", "aria-label": "시장 화면" }, [["macro", "거시 지표"], ["mood", "심리"]].map(([v, t]) =>
    h("button", { "aria-pressed": String(sub === v), onclick: () => { state.marketView = v; store.set("marketView", v); render(); } }, t)));
  if (sub === "macro") { const m = Macro(); m.children[0].after(seg); return m; }
  const range = h("div", { class: "chips" }, [["36", "3년"], ["all", "전체"]].map(([v, t]) =>
    h("button", { "aria-pressed": String((state.macroRange || "36") === v), onclick: () => { state.macroRange = v; store.set("macroRange", v); render(); } }, t)));
  return h("div", {}, header("시장", "심리 · 네이버 검색량·카페·뉴스 · 유튜브 · 한국은행 CSI"), seg, range, Sentiment());
}

// ───── 시장 > 거시 지표 (한국은행 ECOS) ─────
function Macro() {
  const d = state.data, M = d.macro;
  if (!M || !M.months) return h("div", {}, header("시장", updatedLine()),
    h("div", { class: "empty" }, "한국은행 지표가 아직 없습니다. GitHub Secrets 에 ECOS_KEY 를 넣으면 다음 갱신 때 채워집니다."));
  const span = state.macroRange === "all" ? M.months.length : 36;
  const mm = M.months.slice(Math.max(0, M.months.length - span)), off = M.months.length - mm.length;
  const X = xDomain(mm), V = (id) => (M.v[id] || []).slice(off);
  const pts = (id, f = (x) => x) => mm.map((m, i) => ({ t: ymDate(m), v: V(id)[i] === null || V(id)[i] === undefined ? null : f(V(id)[i]) }));
  const name = (id) => (M.meta[id] || {}).name || id;
  const lastTxt = (id, unit = "", nd = 2) => { const a = M.v[id] || []; for (let i = a.length - 1; i >= 0; i--) if (a[i] !== null) return `${dotted(M.months[i])} ${(+a[i]).toFixed(nd).replace(/\.?0+$/, "")}${unit}`; return "–"; };
  const rangeSeg = h("div", { class: "chips" }, [["36", "3년"], ["all", "2013년~"]].map(([v, t]) =>
    h("button", { "aria-pressed": String((state.macroRange || "36") === v), onclick: () => { state.macroRange = v; store.set("macroRange", v); render(); } }, t)));
  const rate = Chart({ label: "금리", xDomain: X, height: 200, yFmt: (v) => v + "%", tipFmt: (v) => v.toFixed(2) + "%", series: [
    { name: "기준금리", kind: "line", color: "var(--s1)", pts: pts("base_rate") },
    { name: "주담대 금리(신규)", kind: "line", color: "var(--s2)", pts: pts("mort_rate") },
    { name: "국고채 3년", kind: "line", color: "var(--s3)", width: 1.5, pts: pts("ktb3") }] });
  const mood = Chart({ label: "소비자 심리", xDomain: X, height: 190, yFmt: (v) => String(v), tipFmt: (v) => String(v),
    refs: [{ v: 100, label: "100 = 오른다·내린다 같음", left: true }], series: [
      { name: "주택가격전망CSI", kind: "line", color: "var(--s2)", pts: pts("csi_house") },
      { name: "금리수준전망CSI", kind: "line", color: "var(--s1)", pts: pts("csi_rate") }] });
  // 가격 겹쳐 보기: 각 선을 보이는 기간에서 처음 값이 있는 달 = 100
  const rebase = (arr) => { const b = arr.find((p) => p.v !== null && p.v !== undefined); return arr.map((p) => ({ t: p.t, v: b && p.v !== null ? Math.round(p.v / b.v * 1000) / 10 : null })); };
  const O = d.overlap || {}, reg = (id) => (O.regions || []).find((r) => r.id === id);
  const regPts = (id) => { const r = reg(id); if (!r) return []; return mm.map((m) => { const i = d.months.indexOf(m); return { t: ymDate(m), v: i >= 0 && i < d.months.length - 2 ? r.p84.v[i] : null }; }); };
  const price = Chart({ label: "가격 지수", xDomain: X, height: 230, yFmt: (v) => String(v), tipFmt: (v) => v.toFixed(1),
    refs: [{ v: 100, label: "각 선의 시작=100", left: true }], series: [
      { name: "KB 서울 아파트 매매", kind: "line", color: "var(--ink)", width: 2.2, pts: rebase(pts("kb_seoul_apt")) },
      { name: "KB 서울 아파트 전세", kind: "line", color: "var(--ink)", width: 1.6, dash: true, endDot: false, pts: rebase(pts("kb_seoul_apt_jeonse")) },
      { name: "강동구 실거래(84㎡ 환산)", kind: "line", color: "var(--s1)", width: 1.6, endDot: false, pts: rebase(regPts("gangdong")) },
      { name: "분당구 실거래", kind: "line", color: "var(--s2)", width: 1.6, endDot: false, pts: rebase(regPts("bundang")) },
      { name: "하남시 실거래", kind: "line", color: "var(--s3)", width: 1.6, endDot: false, pts: rebase(regPts("hanam")) }] });
  const loan = Chart({ label: "주택관련대출 월 순증", xDomain: X, height: 150, yFmt: (v) => v + "조", tipFmt: (v) => v.toFixed(1) + "조원", yTicks: 3,
    series: [{ name: "주택관련대출 월 순증", kind: "bar", color: "var(--broker)", pts: pts("loan_flow").map((p) => ({ ...p, v: p.v === null ? null : Math.max(0, p.v) })) }] });
  const supply = Chart({ label: "공급", xDomain: X, height: 190, yMin: 0, yFmt: (v) => (v / 10000).toFixed(v % 10000 ? 1 : 0) + "만", tipFmt: (v) => Math.round(v).toLocaleString() + "호", series: [
    { name: "인허가 서울 (12개월 합)", kind: "line", color: "var(--s1)", pts: pts("permit_seoul_12m") },
    { name: "인허가 경기 (12개월 합)", kind: "line", color: "var(--s3)", pts: pts("permit_gyeonggi_12m") },
    { name: "수도권 미분양", kind: "line", color: "var(--s2)", width: 1.6, dash: true, pts: pts("unsold_capital") }] });
  const llRows = (M.ll || []).map((L) => {
    const bi = L.k.indexOf(L.best), r = bi >= 0 ? L.r[bi] : null, w = r === null ? 0 : Math.min(50, Math.abs(r) * 50);
    const txt = r === null ? "–" : Math.abs(r) < 0.3 ? "약함" : (r < 0 ? "오르면 → 집값 둔화" : "오르면 → 집값 상승");
    return h("tr", {}, h("td", {}, L.label), h("td", {}, L.best === null ? "–" : (L.best ? `${L.best}개월 뒤` : "같은 달")),
      h("td", { class: "llcell" }, h("div", { class: "llbar" }, h("span", { class: "mid" }), r === null ? null :
        h("i", { class: r < 0 ? "neg" : "pos", style: r < 0 ? `right:50%;width:${w}%` : `left:50%;width:${w}%` }))),
      h("td", { class: "r" }, r === null ? "–" : (r > 0 ? "+" : "−") + Math.abs(r).toFixed(2)), h("td", {}, txt));
  });
  const ll = h("table", { class: "cmp ll" }, h("thead", {}, h("tr", {}, h("th", {}, "지표 변화"), h("th", {}, "가장 강한 시차"),
    h("th", { class: "llhead" }, h("span", {}, "−"), h("span", {}, "+")), h("th", {}, "상관"), h("th", {}, "방향"))), h("tbody", {}, llRows));
  return h("div", {},
    header("시장", `거시 지표 · 한국은행 ECOS · 기준금리 ${lastTxt("base_rate", "%")} · 주택가격전망CSI ${lastTxt("csi_house", "", 0)}`),
    rangeSeg,
    h("div", { class: "sections" },
      wide(Section("가격 겹쳐 보기", "KB 서울 아파트 지수(한국은행 수록)와 관심 지역 실거래 84㎡ 환산가(3개월 중앙값, 2023.10~) · " +
        "각 선을 보이는 기간의 첫 값 = 100 · 실거래는 신고가 덜 끝난 최근 2개월 제외", price)),
      Section("금리", `기준금리 ${lastTxt("base_rate", "%")} · 주담대(신규) ${lastTxt("mort_rate", "%")} · 국고채 3년 ${lastTxt("ktb3", "%")}`, rate),
      Section("소비자 심리 (CSI)", "100 초과 = 1년 뒤 오른다고 보는 가구가 더 많음 · " +
        `주택가격전망 ${lastTxt("csi_house", "", 0)} · 금리수준전망 ${lastTxt("csi_rate", "", 0)}`, mood),
      Section("주택관련대출 월 순증", `예금취급기관 주택관련대출 잔액의 전월 대비 증가 · 최근 ${lastTxt("loan_flow", "조원", 1)}`, loan),
      Section("공급", "주택 인허가 12개월 합(서울·경기, 2~4년 뒤 입주 물량의 선행 지표) · 점선 = 수도권 미분양", supply),
      wide(Section("선행 관계 (2013년~)", "지표의 3개월 변화와 k(0~12)개월 뒤 KB 서울 아파트 매매지수 3개월 변화의 상관 중 가장 큰 시차 · " +
        "3개월 변화끼리 겹쳐 실제 독립 표본은 더 적음 · 과거 패턴이며 예측이 아님", ll))));
}

function Info() {
  const d = state.data;
  return h("div", { class: "info" },
    header("정보", null, false),
    h("div", { class: "banner" }, `데이터 생성 ${d.generated_at.replace("T", " ")} · 실거래 ${dotted(d.data_through)}까지 · 아실 매물 ${d.asil_through ? dotted(d.asil_through) : "없음"}까지`),
    h("h2", {}, "기준"),
    h("ul", {},
      h("li", {}, "3개월 중앙값: 그 달 포함 직전 3개월의 개별 매매를 모은 중앙값. 해제·직거래 제외. n은 거래 수(3건 미만은 ⚠)."),
      h("li", {}, "전세: 신규 계약만(갱신은 5% 인상 상한 때문에 제외). 전세가율 = 전세 ÷ 매매 (같은 3개월 창)."),
      h("li", {}, "평형: 전용 59형 57~62㎡ · 74형 72~77㎡ · 84형 82~87㎡ · 93형 90~97㎡ · 101형 97~107㎡ · 118형 112~125㎡."),
      h("li", {}, `매수 상한 ${eok(d.cap)} (설정 파일 config/settings.yaml).`),
      h("li", {}, "최근 1~2개월은 신고 기한(30일)이 남아 거래 수가 늘어날 수 있습니다."),
      h("li", {}, "매물×가격: 지역 가격 = 지역 전체 아파트 매매의 ㎡당 가격 × 84(84㎡ 환산) 3개월 중앙값. 선행 관계 = 매물 3개월 변화와 k개월 뒤 가격 3개월 변화의 상관(참고용).")),
    h("h2", {}, "출처"),
    h("ul", {},
      h("li", {}, "국토교통부 아파트 매매·전월세 실거래가 (공공데이터포털) — 매일 06:30 자동 갱신"),
      h("li", {}, "아실(asil.kr) 일별 매물 수(매매·전세·월세) — 단지·지역(구·동), 2023.09부터, 매일 06:30 자동 갱신. 여러 중개사가 올린 같은 물건은 1건. 평형 구분 없음."),
      h("li", {}, "네이버페이 부동산 매매 최저 호가 — 북마클릿으로 수집한 날만 기록")),
    h("h2", {}, "홈 화면에 추가"),
    h("ul", {},
      h("li", {}, "아이폰(Safari): 공유 버튼 → 홈 화면에 추가"),
      h("li", {}, "안드로이드(Chrome): 메뉴 ⋮ → 앱 설치 (또는 홈 화면에 추가)")),
    h("p", { class: "hero-sub" }, "개인 매수 검토용. 투자 판단의 근거로 단독 사용하지 마세요."));
}

// ───── 라우터 ─────
function render() {
  const app = $("#app");
  const route = (location.hash || "#/").slice(1).split("/").filter(Boolean);
  const tab = route[0] === "now" ? "now" : route[0] === "compare" ? "compare" : route[0] === "info" ? "info" : route[0] === "overlap" ? "overlap" : (route[0] === "market" || route[0] === "macro") ? "market" : "home";
  document.querySelectorAll(".tabbar a").forEach((a) => {
    if (a.dataset.tab === tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  if (!state.data) {
    app.replaceChildren(h("div", { class: "empty" }, state.error || "불러오는 중…",
      state.error ? h("div", { style: "margin-top:12px" }, h("button", { class: "chips", onclick: () => location.reload() }, "다시 시도")) : null));
    return;
  }
  let view;
  if (route[0] === "c") view = Detail(route[1], route[2] || state.band);
  else if (tab === "now") view = Now();
  else if (tab === "compare") view = Compare();
  else if (tab === "info") view = Info();
  else if (tab === "overlap") view = Overlap();
  else if (tab === "market") { if (route[0] === "macro") state.marketView = "macro"; view = Market(); }
  else view = Home();
  if (state.error) view.prepend(h("div", { class: "banner" }, state.error + " (저장된 데이터를 표시 중)"));
  app.replaceChildren(view);
}
window.addEventListener("hashchange", () => { render(); window.scrollTo(0, 0); });
(async function main() {
  await loadData(false);
  render();
  if ("serviceWorker" in navigator && location.protocol === "https:") {
    navigator.serviceWorker.register("sw.js").catch(() => { /* 서비스워커 실패는 무시 (온라인 동작엔 영향 없음) */ });
  }
})();
