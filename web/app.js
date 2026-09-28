/* 관심 단지 실거래 — 모바일 웹앱. 데이터: data/app.json (scripts/export_web.py 가 생성).
   금액 단위: 만원. 화면에는 억으로 표시. 외부 라이브러리 없음(SVG 차트 직접 그림). */
"use strict";

// ───── 유틸 ─────
const $ = (sel, el = document) => el.querySelector(sel);
const SLOT = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];
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
// series: {name, color, kind: line|dots|bar, pts: [{t, v, n?, tip?}], shape?, width?}
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
  if (series.length > 1 || opts.legend) {
    wrap.append(h("div", { class: "legend" }, series.filter((se) => !se.noLegend).map((se) =>
      h("span", {}, h("i", { class: se.kind === "line" ? "l" : se.kind === "bar" ? "b" : "d", style: `background:${se.color}` }), se.name))));
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
      svg.append(s("path", { d, style: `fill:none;stroke:${se.color};stroke-width:${se.width || 2};stroke-linejoin:round;stroke-linecap:round` }));
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
        for (const se of series.filter((x) => x.kind !== "dots")) {
          const p = se.pts.find((q) => q.t === t);
          if (!p || p.v === null || p.v === undefined) continue;
          tip.append(h("div", { class: "row" }, h("i", { style: `background:${se.color}` }),
            h("b", {}, (se.fmt || opts.tipFmt || yf)(p.v)), h("span", {}, se.name + (p.n !== undefined ? ` (n=${p.n})` : ""))));
        }
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
  const span = (t1 - t0) / (30.4 * 864e5), every = span > 26 ? 6 : span > 10 ? 3 : 1;
  const out = [], d0 = new Date(t0);
  for (let y = d0.getUTCFullYear(), m = d0.getUTCMonth(); ; m++) {
    const t = Date.UTC(y, m, 1);
    if (t > t1) break;
    if (t >= t0 && (new Date(t).getUTCMonth()) % every === 0) out.push(t);
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
const state = { data: null, band: store.get("band", "84"), range: store.get("range", "36"), offerKind: "all", offerCx: "all", error: null };
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
const colorOf = (c) => SLOT[c.slot % 4];
function monthsView() {
  const m = state.data.months, n = state.range === "12" ? 12 : m.length;
  return m.slice(m.length - n);
}
function xDomain(months) { return [ymDate(months[0]) - 20 * 864e5, ymDate(months[months.length - 1]) + 20 * 864e5]; }
const seriesPts = (obj, months, all) => all.map((ym, i) => ({ t: ymDate(ym), v: obj.v[i], n: obj.n ? obj.n[i] : undefined }))
  .filter((p) => months.includes(new Date(p.t).toISOString().slice(0, 7)));
// 아실 일별 매물 수 (열 형식: d 날짜, s 매매, j 전세, w 월세)
function asilLast(c) {
  const A = c.asil; if (!A || !A.d.length) return null;
  const i = A.d.length - 1;
  return { d: A.d[i], sale: A.s[i], jeonse: A.j[i], wolse: A.w[i], i };
}
// 7일 전(그날 기록이 없으면 그 이전 가장 가까운 날) 대비 증감
function asilDelta(c, key, days = 7) {
  const A = c.asil, last = asilLast(c); if (!last) return null;
  const target = dDate(last.d) - days * 864e5;
  for (let i = last.i - 1; i >= 0; i--) if (dDate(A.d[i]) <= target) return A[key][last.i] - A[key][i];
  return null;
}
const asilPts = (c, key) => c.asil.d.map((d, i) => ({ t: dDate(d), v: c.asil[key][i] }));

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
  const d = state.data, band = d.bands.includes(state.band) ? state.band : "84";
  const list = d.complexes.filter((c) => c.bands.includes(band));
  return h("div", {},
    header("관심 단지", updatedLine()),
    // 평형이 최우선 필터: 탭 하나로 아래 실거래·매물 표와 단지 카드가 모두 바뀐다
    bandSeg(d.bands, band, (b) => { state.band = b; store.set("band", b); render(); }),
    h("div", { class: "feeds" }, TradeFeed(band), OfferFeed(null, band)),
    h("div", { class: "cards" }, list.map((c) => Card(c, band))),
    h("p", { class: "hero-sub", style: "margin-top:14px" }, "3개월 중앙값: 직전 3개월 매매(해제·직거래 제외)를 모은 중앙값. 아실 매물은 단지 전체 기준(같은 물건 중복 제외), 괄호는 1주 전 대비."));
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
    [{ t: "단지" }, { t: "계약일" }, { t: "동·층·전용" }, { t: "금액", r: 1 }], rows, T.length);
}
const OFFER_T = { sale: "매매", jeonse: "전세", wolse: "월세" };
function offerPrice(o) { return o.t === "wolse" ? `${eok(o.p)}/${o.r ?? "–"}` : eok(o.p); }
// fixedId 가 있으면 그 단지 상세 화면용: 단지 필터·단지 열을 빼고 매물 특징을 함께 보여 준다
function OfferFeed(fixedId, band) {
  const d = state.data, all = (d.offers || []).filter((o) => (!fixedId || o.c === fixedId) && (!band || o.b === band));
  const kKey = fixedId ? "offerKindCx" : "offerKind";
  const kind = state[kKey] || "all", cid = fixedId || state.offerCx || "all";
  const byCx = all.filter((o) => cid === "all" || o.c === cid);
  const O = byCx.filter((o) => kind === "all" || o.t === kind);
  const since = d.offers_since;
  const cxIds = d.complexes.map((c) => c.id).filter((id) => all.some((o) => o.c === id));
  const pick = (k, v) => () => { state[k] = v; render(); };
  const kindChips = h("div", { class: "chips" }, [["all", "전체"], ["sale", "매매"], ["jeonse", "전세"], ["wolse", "월세"]].map(([v, t]) =>
    h("button", { "aria-pressed": String(kind === v), onclick: pick(kKey, v) },
      t + (v === "all" ? "" : ` ${byCx.filter((o) => o.t === v).length}`))));
  const chips = fixedId ? kindChips : h("div", {},
    h("div", { class: "chips" }, [["all", "전체 단지", all.length], ...cxIds.map((id) => [id, cx(id).short, all.filter((o) => o.c === id).length])].map(([v, t, n]) =>
      h("button", { "aria-pressed": String(cid === v), onclick: pick("offerCx", v) },
        v === "all" ? t : h("span", { class: "cname" }, h("span", { class: "dot", style: `background:${colorOf(cx(v))}` }), `${t} ${n}`)))),
    kindChips);
  const rows = O.map((o) => {
    const down = o.prev && o.p < o.prev, up = o.prev && o.p > o.prev;
    const fresh = since && o.seen > since;   // 추적 시작 뒤 처음 나타난 매물 = 실제 신규 등록
    return h("tr", { onclick: fixedId ? null : () => goCx(o.c), class: fixedId ? "static" : "", title: o.desc || "" },
      fixedId ? null : h("td", {}, cxShort(o.c)),
      h("td", { class: "nw" }, h("span", { class: `kind k-${o.t}` }, OFFER_T[o.t] || o.t), " ", h("b", {}, offerPrice(o)),
        o.chg ? h("span", { class: `badge ${down ? "dn" : up ? "upb" : ""}` }, `${down ? "▼" : up ? "▲" : "변경"} ${md(o.chg)}`) : null),
      h("td", {}, h("span", { class: "sub2" }, `${o.dong ? o.dong + "동 " : ""}${o.f ? o.f + "층" : ""}${o.ar ? " · " + o.ar + "㎡" : ""}`),
        o.n > 1 ? h("span", { class: "tag" }, `${o.n}곳`) : null,
        fixedId && o.desc ? h("div", { class: "desc" }, o.desc) : null),
      h("td", { class: "nw" }, fresh ? h("span", {}, md(o.seen), h("span", { class: "badge new" }, "신규")) : md(o.reg)));
  });
  const note = (fixedId ? `이 단지 아실 매물 · ${band}형 · ` : `아실 매물 목록 · ${band}형 · `) +
    `최근 날짜순 · 같은 물건을 여러 중개사가 올리면 1줄(N곳) · ▼▲ 가격 변경일. ` +
    `날짜: '신규'는 ${md(since)} 추적 시작 뒤 처음 나타난 날(실제 등록일), 그 외는 아실 게시일(중개사가 광고를 다시 올린 날이라 최근 날짜에 몰림)`;
  const head = [{ t: "가격" }, { t: fixedId ? "동·층·전용 · 특징" : "동·층·전용" }, { t: "게시일" }];
  const anyOffers = (d.offers || []).length > 0;
  return Feed(fixedId ? "offers-" + fixedId : "offers", `최근 매물 · ${band}형`,
    all.length ? note : !anyOffers ? "아직 매물 목록이 없습니다. Mac의 매일 자동 수집(install_asil_offers.py)을 켜면 쌓입니다."
      : `지금 올라온 ${band}형 아실 매물이 없습니다.`,
    all.length ? chips : null, fixedId ? head : [{ t: "단지" }, ...head], rows, O.length, true);
}
function Card(c, band) {
  const b = c.b[band], sm = b.summary, L = asilLast(c);
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
    L ? h("div", { class: "lrow" }, h("span", { class: "lbl" }, `아실 매물 ${dotted(L.d).slice(5)}`),
      h("span", {}, "매매 ", h("b", {}, L.sale), dtxt(asilDelta(c, "s"))),
      h("span", {}, "전세 ", h("b", {}, L.jeonse), dtxt(asilDelta(c, "j"))),
      h("span", {}, "월세 ", h("b", {}, L.wolse), dtxt(asilDelta(c, "w"))))
      : h("div", { class: "lrow" }, h("span", { class: "lbl" }, "아실 매물 데이터 없음")));
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
  const b = c.b[band], sm = b.summary, months = monthsView(), all = d.months, X = xDomain(months);
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

  // 아실 일별 매물 수: 기간 선택(1년/3년)을 따르고, 끝은 마지막 기록일
  const AL = asilLast(c);
  let listingSec;
  if (AL) {
    const t1 = dDate(AL.d), t0 = Math.max(dDate(c.asil.d[0]), t1 - (state.range === "12" ? 365 : 3 * 365 + 1) * 864e5);
    const pad = Math.max(2, (t1 - t0) / 864e5 * 0.02) * 864e5;
    const lc = Chart({
      label: "아실 일별 매물 수", xDomain: [t0 - pad, t1 + pad], height: 190, yMin: 0, yFmt: (v) => String(v), tipFmt: (v) => v + "건",
      tipDate: fmtYMD,
      series: [
        { name: "매매", kind: "line", color: "var(--ink)", width: 1.6, pts: asilPts(c, "s") },
        { name: "전세", kind: "line", color: "var(--jeonse)", width: 1.6, pts: asilPts(c, "j") },
        { name: "월세", kind: "line", color: "var(--wolse)", width: 1.6, pts: asilPts(c, "w") },
      ],
    });
    const wk = (k) => { const v = asilDelta(c, k); return v === null ? "" : ` (${v > 0 ? "+" : ""}${v})`; };
    listingSec = Section("아실 매물",
      `단지 전체 · 같은 물건 중복 제외 · ${dotted(AL.d)} 매매 ${AL.sale}${wk("s")} · 전세 ${AL.jeonse}${wk("j")} · 월세 ${AL.wolse}${wk("w")} · 괄호는 1주 전 대비`, lc);
  } else {
    listingSec = Section("아실 매물", "아직 기록이 없습니다. 매일 06:30 자동 수집으로 쌓입니다.");
  }
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
      Section("매매 vs 전세", "3개월 중앙값 · 전세는 갱신 계약 제외", tjChart),
      Section("전세가율 · 갱신 비율", "갱신 비율↑ = 신규 전세 공급 감소 신호 (3개월 표본 5건 이상만)", ratioChart),
      Section("월별 거래량", null, volChart),
      askSec,
      wide(Section(`최근 거래 · ${band}형`, sm.last_deal ? `최근 정상 거래 ${dotted(sm.last_deal.d)} · ${eok(sm.last_deal.p)}` : null, table)),
      wide(OfferFeed(id, band))));
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
  const withAsil = list.filter((c) => asilLast(c));
  let offers = null;
  if (withAsil.length) {
    const t1 = Math.max(...withAsil.map((c) => dDate(asilLast(c).d)));
    const t0 = Math.max(Math.min(...withAsil.map((c) => dDate(c.asil.d[0]))), t1 - (state.range === "12" ? 365 : 3 * 365 + 1) * 864e5);
    const pad = Math.max(2, (t1 - t0) / 864e5 * 0.02) * 864e5;
    offers = Chart({
      label: "단지별 아실 매매 매물 수", xDomain: [t0 - pad, t1 + pad], height: 210, yMin: 0, yFmt: (v) => String(v), tipFmt: (v) => v + "건",
      tipDate: fmtYMD,
      series: withAsil.map((c) => ({ name: c.short, kind: "line", color: colorOf(c), width: 1.6, pts: asilPts(c, "s") })),
    });
  }
  const table = h("table", { class: "cmp" },
    h("thead", {}, h("tr", {}, h("th", {}, "단지"), h("th", {}, "중앙값"), h("th", {}, "1년"), h("th", {}, "전세율"),
      h("th", {}, "매물"), h("th", {}, "1주"))),
    h("tbody", {}, list.map((c) => {
      const sm = c.b[band].summary, A = asilLast(c), dw = asilDelta(c, "s");
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
      offers ? wide(Section("아실 매매 매물 수", "단지 전체 기준 · 같은 물건 중복 제외 · 일별", offers)) : null,
      wide(Section("요약", "중앙값 = 3개월 매매 중앙값 · 전세율 = 전세가율 · 매물 = 아실 최근일 매매 매물 수(단지 전체) · 1주 = 1주 전 대비", table))));
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
      h("li", {}, "평형: 전용 59형 57~62㎡ · 74형 72~77㎡ · 84형 82~87㎡."),
      h("li", {}, `매수 상한 ${eok(d.cap)} (설정 파일 config/settings.yaml).`),
      h("li", {}, "최근 1~2개월은 신고 기한(30일)이 남아 거래 수가 늘어날 수 있습니다.")),
    h("h2", {}, "출처"),
    h("ul", {},
      h("li", {}, "국토교통부 아파트 매매·전월세 실거래가 (공공데이터포털) — 매일 06:30 자동 갱신"),
      h("li", {}, "아실(asil.kr) 일별 매물 수(매매·전세·월세) — 2023.09부터, 매일 06:30 자동 갱신. 여러 중개사가 올린 같은 물건은 1건."),
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
  const tab = route[0] === "compare" ? "compare" : route[0] === "info" ? "info" : "home";
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
  else if (tab === "compare") view = Compare();
  else if (tab === "info") view = Info();
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
