"""네이버 부동산 3차 프로브: 실제 브라우저로 단지 페이지를 열어 페이지가 받는 데이터(JSON)를 저장 (국내 PC).

네이버페이 부동산은 브라우저가 아닌 요청을 거절(429)하므로, Chromium 창을 띄워 사람이 보는 것과 같은
지도 URL을 열고, 그 페이지가 네이버에서 받아오는 JSON 응답을 data/naver_probe3/ 에 저장한다.

준비 (처음 한 번):
    python3 -m pip install --user playwright
    python3 -m playwright install chromium

실행:
    python3 scripts/naver_probe3.py

- 단지 4개 × 탭 2개(매물 추정 'article', 실거래 'transaction') = 페이지 8번, 페이지 사이 5초
- 창이 떴다가 자동으로 닫힌다. 로그인 불필요.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from realestate.lzstring import compress_uri  # noqa: E402

OUT = ROOT / "data" / "naver_probe3"
MAX_BODY = 300_000
# 사용자가 브라우저에서 확인한 네이버 단지번호와 지도 중심값
COMPLEXES = {
    121977: "3zpGBI-2ALsfm",   # 고덕자이
    118210: "3zpvHU-2ALsgO",   # 고덕센트럴아이파크
    102283: "3znRqM-2AFPbg",   # 센트럴타운
    111028: "3zqgBP-2ALzwa",   # 미사강변더샵센트럴포레
}
TABS = ("article", "transaction")


def map_url(complex_id: int, center: str, tab: str) -> str:
    layer = json.dumps([{"id": "complex_detail", "params": {"complexId": complex_id},
                         "searchParams": {"tab": tab, "articleTradeTypes": "A1-B1"}, "returnable": True}],
                       separators=(",", ":"))
    return f"https://fin.land.naver.com/map?center={center}&zoom=16.5&layer={quote(compress_uri(layer), safe='')}"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright가 없습니다. 먼저 실행:\n  python3 -m pip install --user playwright\n"
              "  python3 -m playwright install chromium")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    index = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(locale="ko-KR", viewport={"width": 1280, "height": 900})
        captured: list = []

        def on_response(resp):
            url = resp.url
            if "land.naver.com" not in url:
                return
            if "json" not in resp.headers.get("content-type", ""):
                return
            try:
                body = resp.body()[:MAX_BODY]
            except Exception:  # noqa: BLE001 (리다이렉트 등 본문 없음)
                body = b""
            req = resp.request
            captured.append({"url": url, "method": req.method, "status": resp.status,
                             "post_data": req.post_data, "body": body.decode("utf-8", "replace")})

        page.on("response", on_response)
        for cid, center in COMPLEXES.items():
            for tab in TABS:
                captured.clear()
                url = map_url(cid, center, tab)
                status = "ok"
                try:
                    page.goto(url, wait_until="networkidle", timeout=40_000)
                    page.wait_for_timeout(4000)
                except Exception as e:  # noqa: BLE001
                    status = f"오류: {type(e).__name__}"
                shot = f"{cid}_{tab}.png"
                try:
                    page.screenshot(path=str(OUT / shot))
                except Exception:  # noqa: BLE001
                    shot = ""
                for i, c in enumerate(captured):
                    path = re.sub(r"[^\w.-]+", "_", c["url"].split("?")[0].split("land.naver.com")[-1])[:60]
                    fname = f"{cid}_{tab}_{i:02d}{path}.json"
                    (OUT / fname).write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
                index.append({"complex": cid, "tab": tab, "status": status, "url": url, "screenshot": shot,
                              "responses": [(c["status"], c["method"], c["url"][:160]) for c in captured]})
                print(f"{cid} {tab:12} {status:10} JSON 응답 {len(captured)}개")
                time.sleep(5)
        browser.close()

    (OUT / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장 위치: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
