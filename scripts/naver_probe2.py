"""네이버 부동산 2차 프로브: 단지번호로 매물 목록 응답 구조 확인 (국내 PC에서 실행).

    python3 scripts/naver_probe2.py 단지번호1 단지번호2 단지번호3 단지번호4

단지번호는 브라우저에서 단지 페이지를 열었을 때 주소창의 숫자
(예: https://fin.land.naver.com/complexes/12345 → 12345, new.land.naver.com/complexes/12345 도 동일).

- 단지마다 후보 엔드포인트(모바일 매물목록, fin.land 단지 페이지 등)를 시도하고 원문을 data/naver_probe2/ 에 저장
- 모바일 검색 화면의 스크립트(search.min.js)도 저장 → 실제 데이터 주소를 코드에서 확인
- 요청 30회 안팎, 2초 간격, 로그인 불필요
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "naver_probe2"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
GAP_SEC = 2.0
MAX_BODY = 500_000

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
results: list = []


def save(step: str, r: requests.Response) -> str:
    ctype = r.headers.get("Content-Type", "")
    ext = "json" if "json" in ctype else "js" if "javascript" in ctype else "txt"
    fname = re.sub(r"[^\w.-]+", "_", step)[:80] + "." + ext
    (OUT / fname).write_bytes(r.content[:MAX_BODY])
    return fname


def call(step: str, url: str, method: str = "GET", referer: str = "", **kw) -> requests.Response | None:
    time.sleep(GAP_SEC)
    headers = {"Referer": referer} if referer else {}
    try:
        r = session.request(method, url, headers=headers, timeout=20, **kw)
    except requests.RequestException as e:
        results.append((step, f"실패: {type(e).__name__}", ""))
        return None
    results.append((step, f"HTTP {r.status_code} ({len(r.content):,}B)", save(step, r)))
    return r


def main(argv: list[str]) -> int:
    nums = [a for a in argv if a.isdigit()]
    if not nums:
        print(__doc__)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)

    # 모바일 검색 화면 스크립트: 실제 데이터 요청 주소 확인용
    call("js_search_min", "https://ssl.pstatic.net/static.land/static/space/js/deploy/20260914103633/min/search.min.js",
         referer="https://m.land.naver.com/")

    for n in nums:
        m_ref = f"https://m.land.naver.com/complex/info/{n}"
        call(f"m_complex_info_{n}", m_ref, referer="https://m.land.naver.com/")
        for trade in ("A1", "B1"):
            call(f"m_articles_{n}_{trade}",
                 f"https://m.land.naver.com/complex/getComplexArticleList?hscpNo={n}&tradTpCd={trade}"
                 f"&order=point_&showR0=N&page=1", referer=m_ref)
        f_ref = f"https://fin.land.naver.com/complexes/{n}"
        call(f"fin_complex_page_{n}", f_ref, referer="https://fin.land.naver.com/")
        call(f"fin_api_complex_{n}", f"https://fin.land.naver.com/front-api/v1/complex?complexNumber={n}",
             referer=f_ref)
        call(f"fin_api_articles_{n}", "https://fin.land.naver.com/front-api/v1/complex/article/list",
             method="POST", referer=f_ref,
             json={"complexNumber": n, "tradeTypes": ["A1"], "page": 0, "size": 30, "orderType": "RECENT"})

    (OUT / "_summary.json").write_text(json.dumps({"complex_numbers": nums, "results": results},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'단계':40} {'상태':25} 파일")
    for step, status, fname in results:
        print(f"{step:40} {status:25} {fname}")
    print(f"\n저장 위치: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
