"""아실 단지별 일별 매물 수 수집 → data/listings/asil/asil_offer_counts.csv

    python scripts/asil_collect.py                  # 최근 3개월 (매일 GitHub Actions가 실행)
    python scripts/asil_collect.py --start 2023-09  # 백필 (아실은 약 3년치 제공)

단지 목록은 config/complexes.yaml (naver_id = 아실 단지 번호). 단지당 1회 요청, 요청 간 2초.
한 단지라도 실패하면 나머지는 저장하고 종료 코드 1 (Actions 실패 알림).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from realestate import asil, config  # noqa: E402

OUT = ROOT / "data" / "listings" / "asil" / "asil_offer_counts.csv"
REGION_OUT = ROOT / "data" / "listings" / "asil" / "asil_region_counts.csv"   # 지역(시군구·동) 일별 매물 수


def month_start(s: str) -> date:
    return datetime.strptime(s, "%Y-%m").date().replace(day=1)


def main(argv=None) -> int:
    today = datetime.now(config.KST).date()
    ap = argparse.ArgumentParser(description="아실 일별 매물 수 수집")
    ap.add_argument("--start", help="YYYY-MM (기본: 2개월 전 달 = 최근 약 3개월)")
    ap.add_argument("--end", help="YYYY-MM (기본: 이번 달)")
    a = ap.parse_args(argv)

    default_start = date(today.year + (today.month - 3) // 12, (today.month - 3) % 12 + 1, 1)
    start = month_start(a.start) if a.start else default_start
    end = month_start(a.end) if a.end else today.replace(day=1)
    complexes = config.load_complexes()
    print(f"아실 매물 수 수집: {start:%Y-%m} ~ {end:%Y-%m} · 단지 {len(complexes)}개")
    failed = asil.collect(complexes, OUT, start, end)
    print(f"저장: {OUT.relative_to(ROOT)}")
    regions = config.load_settings().get("regions", [])
    if regions:
        # 지역 파일이 아직 없으면 3년치부터 받는다
        r_start = start if REGION_OUT.exists() else min(start, date(today.year - 3, today.month, 1))
        print(f"지역 매물 수: {r_start:%Y-%m} ~ {end:%Y-%m} · 지역 {len(regions)}곳")
        failed += asil.collect_regions(regions, REGION_OUT, r_start, end)
        print(f"저장: {REGION_OUT.relative_to(ROOT)}")
    if failed:
        print(f"실패 단지: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
