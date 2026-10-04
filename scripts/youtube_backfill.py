"""유튜브 부동산 새 영상 수 백필 (GitHub Actions 데이터 갱신이 매일 이어서 실행, 다 채우면 아무것도 안 함).

    python scripts/youtube_backfill.py              # 한 번에 최대 45회 호출 (=4,500단위, 하루 무료 한도 10,000)
    python scripts/youtube_backfill.py --max-calls 10

- 최근 90일: 하루 단위 → data/sentiment/youtube_daily.csv (매일 수집과 같은 파일·같은 검색어)
- 그 전 1년까지: 주 단위(월~일) → data/sentiment/youtube_weekly.csv
- 유튜브 검색 1회 = 100단위라, 하루 단위 1년치(365회)는 한도를 넘는다. 그래서 최근만 하루 단위, 나머지는 주 단위로 나눠 며칠에 걸쳐 채운다.
- 값은 유튜브 검색이 주는 추정치(지금 남아 있는 영상 기준). 흐름만 볼 것.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from realestate import config, sentiment as st  # noqa: E402

OUT = ROOT / "data" / "sentiment"
DAILY_DAYS = 90
WEEKS_BACK = 52


def plan(today, daily_done: set, weekly_done: set) -> list[tuple]:
    """('d', 날짜) 또는 ('w', 주 시작 월요일) — 최근부터."""
    jobs = []
    for i in range(1, DAILY_DAYS + 1):
        d = today - timedelta(days=i)
        if d.isoformat() not in daily_done:
            jobs.append(("d", d))
    first_daily = today - timedelta(days=DAILY_DAYS)
    mon = first_daily - timedelta(days=first_daily.weekday())   # 하루 단위 구간 이전의 주들
    for i in range(1, WEEKS_BACK + 1):
        w = mon - timedelta(weeks=i)
        if w < today - timedelta(days=366):
            break
        if w.isoformat() not in weekly_done:
            jobs.append(("w", w))
    return jobs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=45)
    a = ap.parse_args(argv)
    config.load_dotenv_if_present()
    q = ((config.load_settings().get("sentiment") or {}).get("youtube") or {}).get("query", "부동산|아파트|집값")
    try:
        yt = st.YouTube()
    except st.ApiError as e:
        print(f"유튜브: {e} → 건너뜀")
        return 0
    now = datetime.now(st.KST)
    today = now.date()
    daily = {r["date"] for r in st.read_csv(OUT / "youtube_daily.csv")}
    weekly = {r["week"] for r in st.read_csv(OUT / "youtube_weekly.csv")}
    jobs = plan(today, daily, weekly)
    if not jobs:
        print("유튜브 백필: 완료 상태 (할 일 없음)")
        return 0
    drows, wrows = [], []
    for kind, d in jobs[: a.max_calls]:
        start = datetime(d.year, d.month, d.day, tzinfo=st.KST)
        end = start + timedelta(days=1 if kind == "d" else 7)
        try:
            n = yt.count(q, start, end)
        except st.ApiError as e:
            print(f"유튜브 백필 중단: {e}")   # 한도 초과 등 → 다음 실행에서 이어서
            break
        (drows if kind == "d" else wrows).append({"date" if kind == "d" else "week": d.isoformat(), "total_results": n})
    if drows:
        st.upsert_daily(OUT / "youtube_daily.csv", ["date", "total_results"], ("date",), drows)
    if wrows:
        st.upsert_daily(OUT / "youtube_weekly.csv", ["week", "total_results"], ("week",), wrows)
    left = len(jobs) - len(drows) - len(wrows)
    print(f"유튜브 백필: 하루 {len(drows)}개 · 주 {len(wrows)}개 채움 · 남은 {left}개 (다음 실행에서 이어서)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
