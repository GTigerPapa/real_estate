"""bookmarklet_src.js + config/complexes.yaml → tools/bookmarklet.html (설치 페이지), tools/bookmarklet.txt (링크 원문).

    python3 tools/build_bookmarklet.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "bookmarklet_src.js"


def build_source() -> str:
    """단지 목록을 끼워 넣은 읽기 쉬운 여러 줄 소스 (DevTools 콘솔에 붙여넣기용)."""
    complexes = yaml.safe_load((ROOT / "config" / "complexes.yaml").read_text(encoding="utf-8"))["complexes"]
    embed = [{"id": c["id"], "naver_id": int(c["naver_id"]), "name": c["name"]} for c in complexes]
    src = SRC.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)  # 머리말 블록 주석 제거
    return src.replace("__COMPLEXES__", json.dumps(embed, ensure_ascii=False, separators=(",", ":"))).strip() + "\n"


def build_js() -> str:
    lines = [ln.strip() for ln in build_source().splitlines()]
    return "javascript:" + " ".join(ln for ln in lines if ln)


def build_href(js: str) -> str:
    # % 와 따옴표·& 만 인코딩 (href 속성 안에서 안전), 나머지는 브라우저가 그대로 실행
    return quote(js, safe=" !$'()*+,-./:;=?@[]^_`{|}~<>|#")


HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>네이버 매물 덤프 북마클릿</title>
<style>
 body{{font:15px/1.7 system-ui,-apple-system,sans-serif;max-width:720px;margin:40px auto;padding:0 16px;color:#222}}
 .btn{{display:inline-block;padding:10px 18px;background:#1a73e8;color:#fff;border-radius:8px;text-decoration:none;font-weight:600}}
 code{{background:#f3f3f3;padding:2px 6px;border-radius:4px}} ol li{{margin:6px 0}} textarea{{width:100%;height:120px;font:12px monospace}}
</style></head><body>
<h2>네이버 매물 덤프 북마클릿</h2>
<p>아래 파란 버튼을 <b>브라우저 즐겨찾기(북마크) 막대로 드래그</b>하세요. (막대가 안 보이면 크롬: <code>⇧⌘B</code>)</p>
<p><a class="btn" href="{href}">📥 네이버 매물 덤프</a></p>
<h3>매일 하는 순서</h3>
<ol>
 <li><a href="https://fin.land.naver.com/" target="_blank">fin.land.naver.com</a> 을 연다 (아무 화면이나 괜찮음).</li>
 <li>즐겨찾기 막대의 <b>📥 네이버 매물 덤프</b>를 누른다. 30초쯤 뒤 <code>naver_listings_….json</code>이 다운로드된다.</li>
 <li>터미널: <code>cd ~/real_estate</code> → <code>python3 scripts/save_listings.py</code> (다운로드 폴더에서 파일을 찾아 저장소에 넣고 push).</li>
</ol>
<p>대상 단지: {names}</p>
<details><summary>드래그가 안 되면 (방법 2): 즐겨찾기 대신 콘솔에 붙여넣기</summary>
<ol><li>fin.land.naver.com 탭에서 <code>⌥⌘J</code> (개발자 도구 Console)</li>
<li><code>tools/console_snippet.js</code> 내용 전체를 붙여넣고 Enter. 처음엔 <code>allow pasting</code> 을 입력하라고 하면 그대로 입력 후 다시 붙여넣기</li></ol>
북마크를 직접 만들 때 URL 칸에 붙여넣을 한 줄:<textarea readonly>{js}</textarea></details>
<p style="color:#777;font-size:13px">생성: tools/build_bookmarklet.py · 단지 목록(config/complexes.yaml)이 바뀌면 다시 빌드</p>
</body></html>
"""


def main() -> int:
    js = build_js()
    complexes = yaml.safe_load((ROOT / "config" / "complexes.yaml").read_text(encoding="utf-8"))["complexes"]
    (ROOT / "tools" / "bookmarklet.txt").write_text(js, encoding="utf-8")
    (ROOT / "tools" / "console_snippet.js").write_text(build_source(), encoding="utf-8")
    (ROOT / "tools" / "bookmarklet.html").write_text(
        HTML.format(href=build_href(js), js=js.replace("&", "&amp;").replace("<", "&lt;"),
                    names=", ".join(c["name"] for c in complexes)), encoding="utf-8")
    print(f"bookmarklet: {len(js):,}자 → tools/bookmarklet.html, tools/bookmarklet.txt, tools/console_snippet.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())
