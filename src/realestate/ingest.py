"""증분 백필 CLI.

    python -m realestate.ingest                     # settings 기준 backfill_start ~ 현재월, trade+rent
    python -m realestate.ingest --api trade --start 202501 --end 202503 --force

- fetch_log가 ok인 월은 건너뜀. 단, 현재월 포함 최근 refetch_recent_months 개월은 매번 재수집.
- 월 단위로 한 트랜잭션: 원문 저장 → 정규화·UPSERT → fetch_log.
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import config, db
from .api.client import ApiError, RtmsClient, setup_logging
from .api.parse import RENT_KEY, TRADE_KEY, assign_dup_seq, normalize_rent, normalize_trade

log = logging.getLogger("realestate.ingest")

APIS = {
    "trade": ("apt_trade", normalize_trade, TRADE_KEY),
    "rent": ("apt_rent", normalize_rent, RENT_KEY),
}


def add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[4:])
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}{idx % 12 + 1:02d}"


def months_between(start: str, end: str) -> list[str]:
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        cur = add_months(cur, 1)
    return out


def current_ym() -> str:
    return config.now_kst().strftime("%Y%m")


def plan(conn, apis, lawds, months, recent_n: int, this_ym: str, force: bool = False) -> list[tuple]:
    recent_from = add_months(this_ym, -(recent_n - 1)) if recent_n > 0 else "999999"
    tasks = []
    for api in apis:
        for lawd in lawds:
            for ym in months:
                if force or ym >= recent_from or db.fetch_status(conn, api, lawd, ym) != "ok":
                    tasks.append((api, lawd, ym))
    return tasks


def ingest_month(conn, client: RtmsClient, api: str, lawd: str, ym: str) -> dict:
    table, normalize, key = APIS[api]
    fetched_at = config.now_iso()
    try:
        pages = client.fetch_month(api, lawd, ym)
        rows = [normalize(it) for p in pages for it in p.parsed.items]
    except (ApiError, KeyError, ValueError, TypeError) as e:
        msg = str(e) if isinstance(e, ApiError) else f"정규화 실패: {type(e).__name__} {e}"
        db.set_fetch_log(conn, api, lawd, ym, "error", None, None, fetched_at, msg)
        conn.commit()
        log.error("%s %s %s 실패: %s", api, lawd, ym, msg)
        return {"status": "error", "error": msg, "fatal": getattr(e, "fatal", False),
                "unreachable": getattr(e, "unreachable", False)}

    total = pages[0].parsed.total_count if pages else 0
    assign_dup_seq(rows, key)
    with conn:
        new_raw = sum(
            db.insert_raw(conn, api, lawd, ym, p.page_no, fetched_at, p.parsed.result_code,
                          p.parsed.total_count, p.body)
            for p in pages
        )
        new, updated = db.upsert_rows(conn, table, rows, fetched_at)
        status = "ok" if len(rows) == total else "error"
        err = None if status == "ok" else f"건수 불일치 total={total} rows={len(rows)}"
        db.set_fetch_log(conn, api, lawd, ym, status, total, len(rows), fetched_at, err)
    log.info("%s %s %s: total=%d rows=%d 신규=%d 갱신=%d 원문변경=%d/%d%s",
             api, lawd, ym, total, len(rows), new, updated, new_raw, len(pages),
             "" if status == "ok" else f" ⚠ {err}")
    return {"status": status, "total": total, "rows": len(rows), "new": new, "updated": updated}


def main(argv: list[str] | None = None) -> int:
    config.load_dotenv_if_present()
    setup_logging()
    settings = config.load_settings()

    ap = argparse.ArgumentParser(description="실거래 증분 백필")
    ap.add_argument("--api", nargs="+", choices=list(APIS), default=list(APIS))
    ap.add_argument("--lawd", nargs="+", default=list(settings["lawd_codes"]))
    ap.add_argument("--start", default=str(settings["backfill_start"]))
    ap.add_argument("--end", default=None, help="YYYYMM (기본: 현재월 KST)")
    ap.add_argument("--force", action="store_true", help="완료된 월도 재수집")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db", default=str(config.db_path()))
    args = ap.parse_args(argv)

    this_ym = current_ym()
    months = months_between(args.start, args.end or this_ym)
    conn = db.connect(args.db)
    db.init_db(conn)
    db.sync_config(conn, settings, config.load_complexes())

    tasks = plan(conn, args.api, args.lawd, months, settings.get("refetch_recent_months", 3), this_ym, args.force)
    log.info("대상 %d건 (api=%s, lawd=%s, %s~%s)", len(tasks), args.api, args.lawd, months[0], months[-1])
    if args.dry_run:
        for t in tasks:
            print(*t)
        return 0

    client = RtmsClient.from_settings(settings)
    errors, stopped, skipped = [], set(), 0
    for t in tasks:
        if t[0] in stopped:
            skipped += 1
            continue
        r = ingest_month(conn, client, *t)
        if r["status"] != "ok":
            errors.append(t)
            if r.get("unreachable"):
                stopped.update(APIS)
                log.error("공공데이터포털 서버에 연결되지 않음 → 남은 호출 모두 건너뜀 (해외 IP 차단·네트워크 확인)")
            elif r.get("fatal"):
                stopped.add(t[0])
                log.error("%s API 치명적 오류 → 남은 월 건너뜀 (키 등록/한도 확인 필요)", t[0])
    log.info("완료: 호출 %d회, 성공 %d, 실패 %d, 건너뜀 %d",
             client.calls, len(tasks) - len(errors) - skipped, len(errors), skipped)
    for t in errors:
        log.warning("실패: %s %s %s", *t)
    conn.close()
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
