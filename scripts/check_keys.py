"""API 키 점검 (GitHub Actions '키 점검' 워크플로가 수동 실행). 키 값은 출력하지 않는다.

ECOS_KEY · NAVER_CLIENT_ID/NAVER_CLIENT_SECRET · YOUTUBE_API_KEY 각각 최소 1회 호출해 결과만 보여 준다.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta


def call(req) -> tuple[int, dict | str]:
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        body, code = e.read().decode("utf-8", "replace"), e.code
    except Exception as e:  # noqa: BLE001 — URL(키 포함)이 섞일 수 있어 타입명만
        return 0, type(e).__name__
    try:
        return code, json.loads(body)
    except ValueError:
        return code, body[:200]


def mask(text: str) -> str:
    for k in ("ECOS_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
        v = os.environ.get(k)
        if v:
            text = text.replace(v, "***")
    return text


def main() -> int:
    ok = True
    today = date.today()

    key = os.environ.get("ECOS_KEY")
    if not key:
        print("ECOS      : 키 없음"); ok = False
    else:
        ym = lambda d: d.strftime("%Y%m")  # noqa: E731
        u = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/10/722Y001/M/{ym(today - timedelta(days=95))}/{ym(today)}/0101000"
        code, d = call(u)
        rows = (d.get("StatisticSearch") or {}).get("row") if isinstance(d, dict) else None
        if rows:
            print(f"ECOS      : 정상 · 기준금리 {rows[-1]['TIME']} {rows[-1]['DATA_VALUE']}%")
        else:
            print(f"ECOS      : 실패 HTTP {code} · {mask(json.dumps(d, ensure_ascii=False)[:200])}"); ok = False

    cid, sec = os.environ.get("NAVER_CLIENT_ID"), os.environ.get("NAVER_CLIENT_SECRET")
    for name, v in (("NAVER_CLIENT_ID", cid), ("NAVER_CLIENT_SECRET", sec)):
        if v and v != v.strip():
            print(f"네이버    : {name} 앞뒤에 공백·줄바꿈이 있음 (다시 저장 권장)")
    cid, sec = (cid or "").strip(), (sec or "").strip()
    if not (cid and sec):
        print("네이버    : 키 없음 (NAVER_CLIENT_ID / NAVER_CLIENT_SECRET)"); ok = False
    else:
        h = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec, "Content-Type": "application/json"}
        body = {"startDate": (today - timedelta(days=60)).isoformat(), "endDate": (today - timedelta(days=1)).isoformat(),
                "timeUnit": "week", "keywordGroups": [{"groupName": "집값", "keywords": ["집값", "아파트값"]}]}
        code, d = call(urllib.request.Request("https://openapi.naver.com/v1/datalab/search",
                                              data=json.dumps(body).encode(), headers=h, method="POST"))
        res = (d.get("results") or [{}])[0].get("data") if isinstance(d, dict) else None
        if res:
            print(f"네이버 데이터랩 : 정상 · '집값' 주별 검색 지수 {len(res)}주 (최근 {res[-1]['period']} = {res[-1]['ratio']})")
        else:
            print(f"네이버 데이터랩 : 실패 HTTP {code} · {mask(json.dumps(d, ensure_ascii=False)[:200])}"
                  + (" → 애플리케이션 '사용 API'에 데이터랩(검색어트렌드) 추가 필요" if code in (401, 403) else "")); ok = False
        q = urllib.parse.urlencode({"query": "집값", "display": 1, "sort": "date"})
        code, d = call(urllib.request.Request(f"https://openapi.naver.com/v1/search/news.json?{q}", headers=h))
        if isinstance(d, dict) and "total" in d:
            print(f"네이버 검색(뉴스) : 정상 · '집값' 뉴스 {d['total']:,}건")
        else:
            print(f"네이버 검색(뉴스) : 실패 HTTP {code} · {mask(json.dumps(d, ensure_ascii=False)[:200])} (선택 사항)")

    yk = os.environ.get("YOUTUBE_API_KEY")
    if not yk:
        print("유튜브    : 키 없음"); ok = False
    else:
        q = urllib.parse.urlencode({"part": "snippet", "q": "집값", "type": "video", "maxResults": 1, "regionCode": "KR",
                                    "relevanceLanguage": "ko", "publishedAfter": (today - timedelta(days=7)).isoformat() + "T00:00:00Z",
                                    "key": yk})
        code, d = call(f"https://www.googleapis.com/youtube/v3/search?{q}")
        if isinstance(d, dict) and "pageInfo" in d:
            t = (d.get("items") or [{}])[0].get("snippet", {}).get("title", "")
            print(f"유튜브    : 정상 · 최근 7일 '집값' 영상 약 {d['pageInfo'].get('totalResults', 0):,}개 · 예: {t[:40]}")
        else:
            err = (d.get("error") or {}).get("message", "") if isinstance(d, dict) else d
            print(f"유튜브    : 실패 HTTP {code} · {mask(str(err))[:200]}"); ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
