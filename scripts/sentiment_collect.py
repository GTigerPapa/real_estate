"""심리 지표 수집 → data/sentiment/ (GitHub Actions 가 매일 실행). 자세한 내용은 src/realestate/sentiment.py.

    python scripts/sentiment_collect.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from realestate import config, sentiment as st  # noqa: E402

OUT = ROOT / "data" / "sentiment"


def main() -> int:
    config.load_dotenv_if_present()
    cfg = config.load_settings().get("sentiment") or {}
    now = datetime.now(st.KST)
    today = now.date()
    problems = []
    try:
        nv = st.Naver()
    except st.ApiError as e:
        print(f"네이버: {e} → 건너뜀")
        nv = None
    try:
        yt = st.YouTube()
    except st.ApiError as e:
        print(f"유튜브: {e} → 건너뜀")
        yt = None

    if nv:
        try:
            rows = st.collect_datalab(nv, cfg, today)
            st.write_csv(OUT / "datalab_weekly.csv", ["week", "series", "value"],
                         sorted(rows, key=lambda r: (r["series"], r["week"])))
            print(f"데이터랩: {len(rows)}행 ({rows[0]['week'] if rows else '-'} ~ {rows[-1]['week'] if rows else '-'})")
        except st.ApiError as e:
            problems.append(f"데이터랩 {e}")
        try:
            tot = st.collect_totals(nv, cfg.get("counts") or [])
            st.upsert_daily(OUT / "search_totals.csv", ["date", "id", "total"], ("date", "id"),
                            [{"date": today.isoformat(), "id": k, "total": v} for k, v in tot.items()])
            print("검색 총수: " + ", ".join(f"{k} {v:,}" for k, v in tot.items()))
        except st.ApiError as e:
            problems.append(f"검색 총수 {e}")
        feed = st.collect_feed(nv, yt, cfg, now, log=lambda m: problems.append(m))
        if yt and feed.get("yt_day"):
            st.upsert_daily(OUT / "youtube_daily.csv", ["date", "total_results"], ("date",),
                            [{"date": feed["yt_day"], "total_results": feed["yt_total"]}])
        (OUT / "feed").mkdir(parents=True, exist_ok=True)
        text = json.dumps(feed, ensure_ascii=False, indent=1)
        (OUT / "feed" / "latest.json").write_text(text, encoding="utf-8")
        (OUT / "feed" / f"{today.isoformat()}.json").write_text(text, encoding="utf-8")
        st.prune_feed(OUT / "feed", 30, today)
        print(f"주요 글: 뉴스 {len(feed['news'])} · 카페 {len(feed['cafe'])} · 유튜브 {len(feed['yt'])}"
              + (f" (전날 영상 약 {feed.get('yt_total', 0):,}개)" if feed.get("yt_day") else ""))
    for p in problems:
        print("문제: " + p)
    return 1 if problems or not nv else 0


if __name__ == "__main__":
    sys.exit(main())
