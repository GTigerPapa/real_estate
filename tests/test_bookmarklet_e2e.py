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
        body = {"result": [{"number": 3, "name": "84A", "exclusiveArea": 84.97}, {"number": 5, "name": "59", "exclusiveArea": 59.9}]}
    elif path == "complex/article/stats":
        body = {"result": {"count": {"dealCount": 31, "leaseDepositCount": 9, "leaseMonthlyCount": 2},
                           "price": {"dealMinPrice": 2_000_000_000, "rentMinPrice": 900_000_000}}}
    elif path == "complex/asking-price":
        base = 2_000_000_000 if q.get("tradeType") == "A1" else 900_000_000
        body = {"result": {"minPrice": base + int(q.get("pyeongTypeNumber", 0)) * 1000, "maxPrice": base * 1.1}}
    elif path == "complex/marketPrice/recent":
        body = {"result": {"kb": 1950000000}}
    elif path == "complex/article/list" and route.request.method == "POST":
        b = json.loads(route.request.post_data)
        tr, n = b["tradeTypes"][0], b["complexNumber"]
        page = 1 if b.get("seed") == "S" and b.get("lastInfo") == [1] else 0   # 다음 쪽은 seed·lastInfo 로
        pages = {"A1": 2, "B1": 1, "B2": 1}[tr]
        groups = [] if tr == "B2" else [f"{n}{tr}{page}{i}" for i in range(2)]

        def art(no, price):
            return {"articleNumber": no, "tradeType": tr, "dongName": "101",
                    "spaceInfo": {"exclusiveSpace": 84.97, "supplySpace": 112.1},
                    "articleDetail": {"articleFeatureDescription": "세안고  급매", "floorDetailInfo": {"targetFloor": "중", "totalFloor": "25"}},
                    "priceInfo": {"dealPrice": price if tr == "A1" else 0, "warrantyPrice": 0 if tr == "A1" else price, "rentPrice": 0},
                    "verificationInfo": {"exposureStartDate": "2026-10-08"}, "brokerInfo": {"brokerageName": "B"}}
        lst = []
        for g in groups:   # 첫 묶음은 중개사 2곳(대표+중복), 둘째는 1곳(중복 정보 없음)
            if g.endswith("0"):
                lst.append({"representativeArticleInfo": art(g, 1_400_000_000),
                            "duplicatedArticleInfo": {"realtorCount": 2, "articleInfoList": [art(g, 1_400_000_000), art(g + "d", 1_400_000_000)]}})
            else:
                lst.append({"representativeArticleInfo": art(g, 1_500_000_000)})
        body = {"result": {"seed": "S", "lastInfo": [page + 1], "hasNextPage": page + 1 < pages, "totalCount": pages * 2, "list": lst}}
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
    import yaml
    expected = [int(c["naver_id"]) for c in yaml.safe_load((ROOT / "config" / "complexes.yaml").read_text(encoding="utf-8"))["complexes"]]
    assert [c["naver_id"] for c in d["complexes"]] == expected
    keys = [r["key"] for r in d["complexes"][0]["responses"]]
    # pyeongList, stats, asking-price × (A1,B1) × (3,5), marketPrice × (3,5)
    assert keys.count("asking_price") == 4 and keys.count("market_price_recent") == 2
    assert {"pyeong_list", "article_stats"} <= set(keys)
    A = d["complexes"][0]["articles"]
    assert A["ok"] and A["trades"]["A1"] == {"pages": 2, "total": 4, "groups": 4, "stop": "end"}
    assert A["trades"]["B2"]["groups"] == 0
    # A1: 2쪽 × (2곳 묶음 2건 + 1곳 1건) = 6, B1: 1쪽 3건
    assert len(A["items"]) == 9 and {x["t"] for x in A["items"]} == {"A1", "B1"}
    it = next(x for x in A["items"] if x["a"].endswith("A100"))
    assert it["fl"] == "중" and it["p"] == 1_400_000_000 and it["rc"] == 2 and it["d"] == "세안고 급매"
    assert any(f"매물 {9 * len(expected)}건" in m for m in dialogs), dialogs
    assert sum(1 for u in calls if "front-api" in u) == len(expected) * (8 + 4)

    r = listings.ingest_file(conn, path)
    assert r["loaded"] and r["metrics"] > 0
    snap = listings.snapshot(conn, config.load_settings())
    vals = snap[snap["complex_id"] == "godeok_xi"].groupby("metric")["value"].first()
    assert vals["sale_count"] == 31 and vals["lease_count"] == 9
    assert vals["sale_min_ask"] == 2_000_000_000 and vals["lease_min_ask"] == 900_000_000
