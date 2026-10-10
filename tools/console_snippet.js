(async function () {
  try {
  var COMPLEXES = [{"id":"yeosu_central_town","naver_id":102283,"name":"센트럴타운"},{"id":"yatap_jangmi8_hyundai","naver_id":2229,"name":"장미마을8단지현대"},{"id":"yatap_top_byeoksan","naver_id":2875,"name":"탑마을벽산"},{"id":"misa_central_xi","naver_id":109215,"name":"미사강변센트럴자이"},{"id":"misa_thesharp_central_forest","naver_id":111028,"name":"미사강변더샵센트럴포레스트"},{"id":"misa_golden_centro","naver_id":105286,"name":"미사강변골든센트로"},{"id":"godeok_xi","naver_id":121977,"name":"고덕자이"},{"id":"godeok_central_ipark","naver_id":118210,"name":"고덕센트럴아이파크"},{"id":"myeongil_samik_green2","naver_id":1308,"name":"삼익그린2차"},{"id":"godeok_lotte_castle_venezia","naver_id":117309,"name":"고덕롯데캐슬베네루체"}];
  var GAP = 400;
  var host = "fin.land.naver.com";
  var AUTO = !!window.__RE_AUTO;   
  if (location.hostname !== host) {
    if (AUTO) { window.__RE_DONE = "wrong-host"; return; }
    if (confirm("네이버페이 부동산 탭에서 실행해야 합니다. 지금 열까요? (열린 뒤 다시 북마클릿을 누르세요)")) {
      location.href = "https://" + host + "/";
    }
    return;
  }
  var box = document.createElement("div");
  box.style.cssText = "position:fixed;top:12px;right:12px;z-index:2147483647;background:#111;color:#fff;" +
    "padding:10px 14px;border-radius:8px;font:13px/1.5 system-ui,sans-serif;max-width:360px;white-space:pre-wrap";
  document.body.appendChild(box);
  var say = function (t) { box.textContent = t; };
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var nowKst = function () {
    var d = new Date(Date.now() + 9 * 3600 * 1000);
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getUTCFullYear() + "-" + p(d.getUTCMonth() + 1) + "-" + p(d.getUTCDate()) + "T" +
      p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()) + ":" + p(d.getUTCSeconds()) + "+09:00";
  };
  var qs = function (params) {
    return Object.keys(params).map(function (k) {
      var v = params[k];
      if (Array.isArray(v)) {
        return v.map(function (x) { return encodeURIComponent(k + "[]") + "=" + encodeURIComponent(x); }).join("&");
      }
      return encodeURIComponent(k) + "=" + encodeURIComponent(v);
    }).join("&");
  };
  var api = async function (key, path, params, method, body) {
    var url = "/front-api/v1/" + path + (params && method !== "POST" ? "?" + qs(params) : "");
    var rec = { key: key, url: url, params: params || {}, method: method || "GET", status: 0, ok: false };
    try {
      var opt = { credentials: "include", headers: { accept: "application/json" } };
      if (method === "POST") {
        opt.method = "POST";
        opt.headers["content-type"] = "application/json";
        opt.body = JSON.stringify(body || params || {});
      }
      var res = await fetch(url, opt);
      rec.status = res.status;
      var text = await res.text();
      try { rec.json = JSON.parse(text); rec.ok = res.status === 200; }
      catch (e) { rec.text = text.slice(0, 4000); }
    } catch (e) {
      rec.error = String(e && e.message || e);
    }
    await sleep(GAP);
    return rec;
  };
  var pyeongNumbers = function (json) {
    var nums = [];
    var list = json && Array.isArray(json.result) ? json.result : [];
    list.forEach(function (o) {
      var n = typeof o.number === "number" ? o.number : o.pyeongTypeNumber;
      if (typeof n === "number" && n > 0 && nums.indexOf(n) < 0) { nums.push(n); }
    });
    return nums;
  };
  
  var TRADES = ["A1", "B1", "B2"];
  var flat = function (a, g, rc) {
    var sp = a.spaceInfo || {}, dt = a.articleDetail || {}, pr = a.priceInfo || {}, v = a.verificationInfo || {}, bk = a.brokerInfo || {};
    var fd = dt.floorDetailInfo || {};
    return { a: String(a.articleNumber), g: g, t: a.tradeType, dong: a.dongName || "", fl: fd.targetFloor || "", tf: fd.totalFloor || "",
      ex: sp.exclusiveSpace || null, sp: sp.supplySpace || null, p: pr.dealPrice || 0, w: pr.warrantyPrice || 0, r: pr.rentPrice || 0,
      pc: pr.priceChangeStatus || 0, d: (dt.articleFeatureDescription || "").replace(/\s+/g, " ").slice(0, 120),
      dt: v.exposureStartDate || "", cf: v.articleConfirmDate || "", bk: bk.brokerageName || "", rc: rc };
  };
  var collectArticles = async function (n, name, idx, total) {
    var res = { ok: true, trades: {}, items: [] };
    var seen = {};
    for (var t = 0; t < TRADES.length; t++) {
      var tr = TRADES[t], seed = null, last = null, info = { pages: 0, total: null, groups: 0, stop: "" };
      for (var pg = 0; pg < 40; pg++) {
        say("매물 목록 " + idx + "/" + total + " " + name + " · " + tr + " · " + (pg + 1) + "쪽");
        var body = { complexNumber: n, tradeTypes: [tr], pyeongTypes: [], dongNumbers: [], userChannelType: "PC", page: pg, size: 20 };
        if (seed) { body.seed = seed; }
        if (last) { body.lastInfo = last; }
        var r = await api("article_list", "complex/article/list", null, "POST", body);
        var R = r.ok && r.json && r.json.result;
        if (!R) { info.stop = "error " + r.status; res.ok = false; break; }
        info.pages++;
        if (info.total === null) { info.total = R.totalCount; }
        var list = R.list || [], fresh = 0;
        list.forEach(function (o) {
          var rep = o.representativeArticleInfo || {}, dup = o.duplicatedArticleInfo || {};
          var g = String(rep.articleNumber), arts = (dup.articleInfoList && dup.articleInfoList.length) ? dup.articleInfoList : [rep];
          if (seen["g" + g]) { return; }
          seen["g" + g] = 1; fresh++; info.groups++;
          arts.forEach(function (a) {
            if (!a || seen["a" + a.articleNumber]) { return; }
            seen["a" + a.articleNumber] = 1;
            res.items.push(flat(a, g, dup.realtorCount || arts.length));
          });
        });
        seed = R.seed || seed; last = R.lastInfo || last;
        if (!R.hasNextPage) { info.stop = "end"; break; }
        if (!fresh) { info.stop = "no-new"; res.ok = false; break; }
      }
      res.trades[tr] = info;
    }
    return res;
  };
  var dump = { format: 1, captured_at: nowKst(), page: location.href, complexes: [] };
  var total = COMPLEXES.length;
  for (var i = 0; i < total; i++) {
    var c = COMPLEXES[i];
    var n = c.naver_id;
    var out = { id: c.id, naver_id: n, name: c.name, responses: [] };
    say("매물 수집 중 " + (i + 1) + "/" + total + " " + c.name);
    var pl = await api("pyeong_list", "complex/pyeongList", { complexNumber: n });
    out.responses.push(pl);
    out.responses.push(await api("article_stats", "complex/article/stats", { complexNumber: n }));
    var types = pyeongNumbers(pl.json || {});
    var trades = ["A1", "B1"];
    for (var t = 0; t < trades.length; t++) {
      for (var k = 0; k < types.length; k++) {
        out.responses.push(await api("asking_price", "complex/asking-price",
          { complexNumber: n, pyeongTypeNumber: types[k], realEstateType: "A01", tradeType: trades[t] }));
      }
    }
    for (var m = 0; m < types.length; m++) {
      out.responses.push(await api("market_price_recent", "complex/marketPrice/recent",
        { complexNumber: n, pyeongTypeNumber: types[m], realEstateType: "A01", cpList: ["kab", "kbstar", "neonet"] }));
    }
    out.articles = await collectArticles(n, c.name, i + 1, total);
    dump.complexes.push(out);
  }
  var okCount = 0, failCount = 0;
  dump.complexes.forEach(function (c) {
    c.responses.forEach(function (r) { if (r.ok) { okCount++; } else { failCount++; } });
  });
  var stamp = dump.captured_at.slice(0, 16).replace(/[-:T]/g, "").replace(/(\d{8})(\d{4})/, "$1_$2");
  var name = "naver_listings_" + stamp + ".json";
  if (AUTO) {   
    window.__RE_JSON = JSON.stringify(dump).replace(/[\uD800-\uDFFF]/g, "");   
    window.__RE_DONE = name;
    box.remove();
    return;
  }
  var blob = new Blob([JSON.stringify(dump)], { type: "application/json" });
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); box.remove(); }, 3000);
  var nArt = 0; dump.complexes.forEach(function (c) { nArt += c.articles ? c.articles.items.length : 0; });
  window.__RE_DONE = name;
  alert("저장: " + name + "\n매물 " + nArt + "건" + "\n성공 " + okCount + " / 실패 " + failCount +
    (failCount ? "\n(실패가 많으면 네이버페이 부동산 페이지를 새로고침한 뒤 다시 눌러 보세요)" : "") +
    "\n\n다음: 터미널에서  python3 scripts/save_listings.py");
  } catch (err) {
    window.__RE_DONE = "error: " + (err && err.message ? err.message : err);
    if (window.__RE_AUTO) { return; }
    alert("네이버 매물 덤프 오류: " + (err && err.message ? err.message : err));
  }
})();
