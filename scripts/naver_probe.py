"""네이버 부동산 응답 구조 확인용 1회성 프로브 (국내 PC에서 실행).

클라우드 서버 IP에서는 네이버 부동산 API가 첫 요청부터 429(TOO_MANY_REQUESTS)를 주거나 응답 없이
연결을 끊는다(2026-09 확인). 그래서 실제 응답 형식을 확인하려고
사용자의 PC에서 한 번 실행해 원문을 data/naver_probe/ 에 저장한다. 저장된 파일로 수집기 파서를 만든다.

    python scripts/naver_probe.py

- 요청은 모두 합쳐 20회 안팎, 요청 사이 2초 간격. 로그인·쿠키 불필요.
- 후보 엔드포인트 여러 개를 시도해 어떤 것이 동작하는지 표로 출력한다 (네이버 구조가 자주 바뀜).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "naver_probe"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
GAP_SEC = 2.0
MAX_BODY = 300_000  # 파일당 저장 상한 (bytes)

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9",
                        "Referer": "https://new.land.naver.com/"})
results: list[tuple[str, str, str]] = []  # (단계, 상태, 저장 파일)


def fetch(step: str, url: str, headers: dict | None = None) -> requests.Response | None:
    time.sleep(GAP_SEC)
    try:
        r = session.get(url, headers=headers or {}, timeout=20)
    except requests.RequestException as e:
        results.append((step, f"실패: {type(e).__name__}", ""))
        return None
    ext = "json" if "json" in r.headers.get("Content-Type", "") else "txt"
    fname = re.sub(r"[^\w.-]+", "_", step)[:80] + "." + ext
    (OUT / fname).write_bytes(r.content[:MAX_BODY])
    results.append((step, f"HTTP {r.status_code} ({len(r.content):,}B)", fname))
    return r


def as_json(r: requests.Response | None):
    if r is None or r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    complexes = yaml.safe_load((ROOT / "config" / "complexes.yaml").read_text(encoding="utf-8"))["complexes"]
    keywords = [c["name"] for c in complexes]

    # 1) new.land 페이지에서 API 토큰 추출 (있으면)
    token = None
    r = fetch("new_land_page", "https://new.land.naver.com/complexes")
    if r is not None and r.status_code == 200:
        m = re.search(r'"token"\s*:\s*"([\w.\-]+)"', r.text) or re.search(r"Bearer\s+([\w.\-]+)", r.text)
        token = m.group(1) if m else None
    results.append(("new_land_token", "있음" if token else "없음", ""))
    auth = {"authorization": f"Bearer {token}"} if token else {}

    # 2) 단지 검색 → complexNo
    found: dict[str, str] = {}
    for kw in keywords:
        data = as_json(fetch(f"new_search_{kw}", f"https://new.land.naver.com/api/search?keyword={quote(kw)}", auth))
        for c in (data or {}).get("complexes", [])[:5]:
            found.setdefault(kw, str(c.get("complexNo")))
        if kw not in found:  # 모바일 검색 페이지 (HTML에 단지번호가 있으면 추출)
            r = fetch(f"m_search_{kw}", f"https://m.land.naver.com/search/result/{quote(kw)}")
            m = re.search(r"hscpNo[\"'=:\s]+(\d+)", r.text) if r is not None else None
            if m:
                found[kw] = m.group(1)

    # 3) 단지별 매물 목록 (매매 A1, 전세 B1) 첫 페이지 — 후보 엔드포인트 둘 다 시도
    for kw, no in found.items():
        fetch(f"new_complex_{kw}", f"https://new.land.naver.com/api/complexes/{no}?sameAddressGroup=false", auth)
        for trade in ("A1", "B1"):
            fetch(f"new_articles_{kw}_{trade}",
                  f"https://new.land.naver.com/api/articles/complex/{no}?realEstateType=APT&tradeType={trade}"
                  f"&page=1&order=rank&sameAddressGroup=false", auth)
            fetch(f"m_articles_{kw}_{trade}",
                  f"https://m.land.naver.com/complex/getComplexArticleList?hscpNo={no}&tradTpCd={trade}"
                  f"&order=point_&showR0=N&page=1")

    (OUT / "_summary.json").write_text(json.dumps(
        {"complex_no": found, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n단지번호: {found or '못 찾음'}\n")
    print(f"{'단계':45} {'상태':25} 파일")
    for step, status, fname in results:
        print(f"{step:45} {status:25} {fname}")
    print(f"\n저장 위치: {OUT}")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
