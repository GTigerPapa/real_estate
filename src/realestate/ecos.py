"""한국은행 ECOS 월별 지표 수집 → data/macro/ecos_monthly.csv (month, series_id, value).

    python scripts/ecos_collect.py        # settings.yaml ecos.series 전부, ecos.start 부터 이번 달까지

- 키: 환경변수 ECOS_KEY (.env 또는 GitHub Secrets). 키는 URL 경로에 들어가므로 오류·로그에 URL을 남기지 않는다.
- 매번 전체 기간을 다시 받아 덮어쓴다 (지표가 소급 수정되는 경우가 있어서). 지표당 1회 요청.
"""
from __future__ import annotations

import csv
import json
import os
import time
import urllib.request
from pathlib import Path

BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
FIELDS = ["month", "series_id", "value"]


class EcosError(RuntimeError):
    pass


def url(key: str, s: dict, start: str, end: str) -> str:
    parts = [BASE, key, "json", "kr", "1", "100000", s["stat"], "M", start, end, str(s["item"])]
    if s.get("item2"):
        parts.append(str(s["item2"]))
    return "/".join(parts)


def fetch_series(key: str, s: dict, start: str, end: str, opener=urllib.request.urlopen) -> list[tuple[str, float]]:
    try:
        with opener(url(key, s, start, end), timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — 메시지에 URL(키 포함)이 들어갈 수 있어 타입명만
        raise EcosError(f"{s['id']}: 요청 실패 ({type(e).__name__})") from None
    rows = (d.get("StatisticSearch") or {}).get("row")
    if not rows:
        res = d.get("RESULT") or {}
        raise EcosError(f"{s['id']}: 데이터 없음 ({res.get('CODE', '?')} {res.get('MESSAGE', '')})")
    out = []
    for r in rows:
        t, v = r.get("TIME", ""), r.get("DATA_VALUE", "")
        if len(t) == 6 and v not in ("", None):
            out.append((f"{t[:4]}-{t[4:]}", float(v)))
    return sorted(out)


def collect(series: list[dict], out: Path, start: str, end: str, key: str | None = None,
            fetcher=fetch_series, pause: float = 0.3, log=print) -> list[str]:
    key = key or os.environ.get("ECOS_KEY")
    if not key:
        raise EcosError("ECOS_KEY 가 없습니다 (.env 또는 GitHub Secrets)")
    rows: dict = {}
    if out.exists():
        with out.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                rows[(r["month"], r["series_id"])] = r
    failed = []
    for i, s in enumerate(series):
        if i:
            time.sleep(pause)
        try:
            got = fetcher(key, s, start, end)
        except EcosError as e:
            log(f"실패 — {e}")
            failed.append(s["id"])
            continue
        for k in [k for k in rows if k[1] == s["id"]]:   # 이 지표는 새로 받은 값으로 통째 교체
            del rows[k]
        for m, v in got:
            rows[(m, s["id"])] = {"month": m, "series_id": s["id"], "value": repr(v) if v != int(v) else str(int(v))}
        log(f"{s['name']}: {len(got)}개월 ({got[0][0]}~{got[-1][0]}) · 최근 {got[-1][1]}{s.get('unit') or ''}")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in sorted(rows.values(), key=lambda r: (r["series_id"], r["month"])):
            w.writerow(r)
    tmp.replace(out)
    return failed
