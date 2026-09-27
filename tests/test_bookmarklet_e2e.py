"""북마클릿 종단 테스트: 실제 Chromium에서 tools/bookmarklet.html 의 javascript: 링크를 그대로 실행.

네이버는 가짜로 응답(라우트 가로채기)하므로 네트워크 없이 돈다. 확인하는 것:
- href 의 퍼센트 인코딩이 브라우저에서 올바로 풀려 실행되는가 (bookmarklet 클릭과 같은 경로: location.href = 'javascript:...')
- 단지 4개 × 엔드포인트 호출 → 파일 다운로드 → listings.ingest_file 로 적재 → 스냅샷 규칙으로 값이 뽑히는가
"""
import json
import os
import re
import shutil
from pathlib import Path

import pytest

from realestate import config, db, listings

ROOT = Path(__file__).resolve().parents[1]
CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM", "/opt/pw-browsers/chromium")
playwright = pytest.importorskip("playwright.sync_api")


def _href() -> str:
    html = (ROOT / "tools" / "bookmarklet.html").read_text(encoding="utf-8")
    return re.search(r'href="(javascript:[^"]+)"', html).group(1)


def _fake_api(route):
    url = route.request.url
    path = url.split("front-api/v1/")[1].split("?")[0]
    q = dict(p.split("=") for p in url.split("?")[1].split("&")) if "?" in url else {}
    body = None
    if path == "complex/pyeongList":
        body = {"result": [{"pyeongTypeNumber": 3, "exclusiveArea": 84.97}, {"pyeongTypeNumber": 5, "exclusiveArea": 59.9}]}
    elif path == "complex/article/stats":
        body = {"result": {"dealCount": 31, "leaseCount": 9}}
    elif path == "complex/asking-price":
        base = 2_000_000_000 if q.get("tradeType") == "A1" else 900_000_000
        body = {"result": {"minPrice": base + int(q.get("pyeongTypeNumber", 0)) * 1000, "maxPrice": base * 1.1}}
    elif path == "complex/marketPrice/recent":
        body = {"result": {"kb": 1950000000}}
    if body is None:
        route.fulfill(status=404, content_type="application/json", body='{"detailCode":"NOT_FOUND"}')
    else:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


@pytest.mark.skipif(not shutil.which(CHROMIUM) and not Path(CHROMIUM).exists(), reason="chromium 없음")
def test_bookmarklet_runs_in_real_chromium(tmp_path, conn):
    href = _href()
    calls = []
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        page = browser.new_page(accept_downloads=True)
        page.route("https://fin.land.naver.com/**", lambda r: (
            calls.append(r.request.url),
            _fake_api(r) if "front-api" in r.request.url
            else r.fulfill(status=200, content_type="text/html", body="<html><body><h1>fake naver</h1></body></html>")))
        dialogs = []
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        page.goto("https://fin.land.naver.com/")
        with page.expect_download(timeout=120_000) as dl:
            page.evaluate("h => { location.href = h; }", href)  # 즐겨찾기 클릭과 같은 javascript: 내비게이션
        path = tmp_path / dl.value.suggested_filename
        dl.value.save_as(path)
        browser.close()

    assert re.fullmatch(r"naver_listings_\d{8}_\d{4}\.json", path.name)
    assert any("성공" in m for m in dialogs), dialogs
    d = listings.load_dump(path)
    assert [c["naver_id"] for c in d["complexes"]] == [121977, 118210, 102283, 111028]
    keys = [r["key"] for r in d["complexes"][0]["responses"]]
    # pyeongList, stats, asking-price × (A1,B1) × (0,3,5), marketPrice
    assert keys.count("asking_price") == 6 and {"pyeong_list", "article_stats", "market_price_recent"} <= set(keys)
    assert len(d["discovery"]) == 4 and all(not r["ok"] for r in d["discovery"])
    assert sum(1 for u in calls if "front-api" in u) == 4 * 9 + 4

    r = listings.ingest_file(conn, path)
    assert r["loaded"] and r["metrics"] > 0
    snap = listings.snapshot(conn, config.load_settings())
    got = snap[(snap["complex_id"] == "godeok_xi") & (snap["pyeong_type"].isin([0, None]) | snap["pyeong_type"].isna())]
    vals = got.groupby("metric")["value"].first()
    assert vals["sale_count"] == 31 and vals["lease_count"] == 9
    assert vals["sale_min_ask"] == 2_000_000_000 and vals["lease_min_ask"] == 900_000_000
