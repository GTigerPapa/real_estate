"""모바일 웹앱 종단 테스트: 실제 Chromium(휴대폰 크기)으로 web/ 을 열어 화면별 렌더와 JS 오류 없음을 확인."""
import functools
import http.server
import json
import os
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM", "/opt/pw-browsers/chromium")
playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not Path(CHROMIUM).exists(), reason="chromium 없음")


@pytest.fixture(scope="module")
def server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB))
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_screens_render_without_errors(server, scheme):
    data = json.loads((WEB / "data" / "app.json").read_text(encoding="utf-8"))
    n84 = sum(1 for c in data["complexes"] if "84" in c["bands"])
    first = data["complexes"][0]["id"]
    errors = []
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROMIUM)
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, color_scheme=scheme)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.add_init_script("try{localStorage.clear()}catch(e){}")

        pg.goto(server + "#/", wait_until="networkidle")
        pg.wait_for_selector(".card")
        assert pg.locator(".card").count() == n84
        # 가로 스크롤 없음 (모바일 폭 고정)
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        pg.click(".card >> nth=0")
        pg.wait_for_selector(".section .chart svg")
        assert pg.url.endswith(f"#/c/{first}/84")
        assert pg.locator(".chart svg").count() >= 5
        # 축 눈금이 억 단위로 올바르게 표시 (0 제거 버그 회귀 방지)
        ticks = pg.locator(".section >> nth=0").locator("svg text").all_text_contents()
        assert any(t in ("10억", "15억", "20억", "25억") for t in ticks), ticks
        # 차트 탭(터치)하면 툴팁 표시
        box = pg.locator(".section >> nth=0").locator("svg").first.bounding_box()
        pg.mouse.move(box["x"] + box["width"] * 0.7, box["y"] + box["height"] * 0.5)
        assert pg.locator(".tip:not([hidden])").count() >= 1

        pg.goto(server + "#/now")
        pg.wait_for_selector(".feed .ftable")
        assert pg.locator(".feed").count() == 1 and "최근 실거래" in pg.locator(".feed h2").inner_text()
        pg.click(".seg >> nth=0 >> button >> nth=1")
        assert "최근 매물" in pg.locator(".feed h2").inner_text()
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        pg.goto(server + "#/compare")
        pg.wait_for_selector(".cmp")
        assert pg.locator(".cmp:not(.otr) tbody tr").count() == n84
        # 매물 수 추이: 단지별 매매(실선)·전월세(점선), 단지 수만큼 요약 줄
        trend = pg.locator(".section", has_text="매물 수 추이")
        assert trend.locator("path[style*='stroke-dasharray']").count() == n84
        assert trend.locator(".cmp.otr tbody tr").count() == n84
        pg.goto(server + "#/overlap")
        pg.wait_for_selector(".llbar")
        assert pg.locator(".section .chart svg").count() >= 4
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        pg.get_by_role("button", name="단지", exact=True).last.click()
        pg.wait_for_selector(".llbar")
        pg.goto(server + "#/macro")
        pg.wait_for_selector(".section .chart svg, .empty")
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        pg.goto(server + "#/market")
        pg.get_by_role("button", name="심리").click()
        pg.wait_for_selector(".stiles, .empty")
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        pg.goto(server + "#/info")
        pg.wait_for_selector(".info")
        b.close()
    assert not errors, errors
