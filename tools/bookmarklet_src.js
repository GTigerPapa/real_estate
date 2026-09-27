/* 네이버페이 부동산 매물 덤프 북마클릿 (원본). tools/build_bookmarklet.py 가 단지 목록을 끼워 넣고
   한 줄 javascript: 링크와 설치 페이지(tools/bookmarklet.html)를 만든다.
   - fin.land.naver.com 탭에서 실행해야 한다 (그 페이지의 세션으로 같은 출처 API를 호출).
   - 단지마다 평형 목록·매물 통계·거래유형/평형별 호가·시세를 받고, 매물 목록 엔드포인트 후보는
     첫 단지에서만 시도한다. 결과 전체를 naver_listings_YYYYMMDD_HHMM.json 으로 내려받는다.
   - 요청 사이 400ms. 이 파일 안에서는 //, 문자열 안 '\n' 을 쓰지 않는다 (빌드 시 줄 단위로 합침). */
(async function () {
  var COMPLEXES = __COMPLEXES__;
  var GAP = 400;
  var host = "fin.land.naver.com";
  if (location.hostname !== host) {
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
    var walk = function (o) {
      if (!o || typeof o !== "object") { return; }
      if (Array.isArray(o)) { o.forEach(walk); return; }
      if (typeof o.pyeongTypeNumber === "number" && nums.indexOf(o.pyeongTypeNumber) < 0) {
        nums.push(o.pyeongTypeNumber);
      }
      Object.keys(o).forEach(function (k) { walk(o[k]); });
    };
    walk(json);
    return nums;
  };
  var dump = { format: 1, captured_at: nowKst(), page: location.href, complexes: [], discovery: [] };
  var total = COMPLEXES.length;
  for (var i = 0; i < total; i++) {
    var c = COMPLEXES[i];
    var n = c.naver_id;
    var out = { id: c.id, naver_id: n, name: c.name, responses: [] };
    say("매물 수집 중 " + (i + 1) + "/" + total + " " + c.name);
    var pl = await api("pyeong_list", "complex/pyeongList", { complexNumber: n });
    out.responses.push(pl);
    out.responses.push(await api("article_stats", "complex/article/stats", { complexNumber: n }));
    var types = [0].concat(pyeongNumbers(pl.json || {}).filter(function (x) { return x !== 0; }));
    var trades = ["A1", "B1"];
    for (var t = 0; t < trades.length; t++) {
      for (var k = 0; k < types.length; k++) {
        out.responses.push(await api("asking_price", "complex/asking-price",
          { complexNumber: n, pyeongTypeNumber: types[k], realEstateType: "A01", tradeType: trades[t] }));
      }
    }
    out.responses.push(await api("market_price_recent", "complex/marketPrice/recent",
      { complexNumber: n, pyeongTypeNumber: 0, realEstateType: "A01", cpList: ["kab", "kbstar", "neonet"] }));
    if (i === 0) {
      say("매물 목록 엔드포인트 확인 중 (첫 단지)");
      dump.discovery.push(await api("cand_article_list_get", "complex/article/list",
        { complexNumber: n, tradeTypes: ["A1", "B1"], realEstateType: "A01", page: 0, size: 50 }));
      dump.discovery.push(await api("cand_article_list_post", "complex/article/list", null, "POST",
        { complexNumber: n, tradeTypes: ["A1", "B1"], realEstateTypes: ["A01"], page: 0, size: 50 }));
      dump.discovery.push(await api("cand_articles", "complex/articles",
        { complexNumber: n, tradeTypes: ["A1", "B1"], page: 0, size: 50 }));
      dump.discovery.push(await api("cand_article_search", "article/list",
        { complexNumber: n, tradeTypes: ["A1", "B1"], page: 0, size: 50 }));
    }
    dump.complexes.push(out);
  }
  var okCount = 0, failCount = 0;
  dump.complexes.forEach(function (c) {
    c.responses.forEach(function (r) { if (r.ok) { okCount++; } else { failCount++; } });
  });
  var stamp = dump.captured_at.slice(0, 16).replace(/[-:T]/g, "").replace(/(\d{8})(\d{4})/, "$1_$2");
  var name = "naver_listings_" + stamp + ".json";
  var blob = new Blob([JSON.stringify(dump)], { type: "application/json" });
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); box.remove(); }, 3000);
  alert("저장: " + name + "\n성공 " + okCount + " / 실패 " + failCount +
    (failCount ? "\n(실패가 많으면 네이버페이 부동산 페이지를 새로고침한 뒤 다시 눌러 보세요)" : "") +
    "\n\n다음: 터미널에서  python3 scripts/save_listings.py");
})();
