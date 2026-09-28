"""아실(asil.kr) 단지별 일별 매물 수 (매매·전세·월세) 수집.

아실의 '매물증감 → 일별 매물현황' 화면이 쓰는 데이터를 단지마다 한 번씩 요청해
data/listings/asil/asil_offer_counts.csv 에 날짜·단지별로 병합한다.

- 아실 단지 번호 = 네이버 단지 번호 (config/complexes.yaml 의 naver_id).
- 한 번 요청으로 지정 기간 전체가 오므로 매일 최근 몇 달을 다시 받아 빈 날을 스스로 메운다.
- 아실 집계: 온라인 중개사 매물을 합산하되 같은 물건을 여러 중개사가 올리면 1건으로 센다.
- 공개 API가 아니라 화면 내부 주소다. 응답 형식이 바뀌거나 비면 오류로 처리한다 (우회하지 않음).
"""
from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://asil.kr/app/data/data_offer_sum.jsp"
REFERER = "https://asil.kr/asil/index.jsp"
USER_AGENT = "Mozilla/5.0 (compatible; real_estate-collector; +https://github.com/GTigerPapa/real_estate)"
FIELDS = ["date", "complex_id", "naver_id", "sale", "jeonse", "wolse", "total"]
_ROW = re.compile(r"listData\[\d+\]\s*=\s*(\{[^}]*\})")


class AsilError(RuntimeError):
    pass


def build_url(apt_id: int, start: date, end: date) -> str:
    q = {"apt": apt_id, "area": "", "c_apt": "", "c_area": "", "c_apt2": "", "c_area2": "",
         "deal": "123", "mode": "2", "sSize": "", "eSize": "",
         "sY": start.year, "sM": start.month, "eY": end.year, "eM": end.month}
    return BASE + "?" + urllib.parse.urlencode(q)


def fetch(apt_id: int, start: date, end: date, timeout: float = 30) -> str:
    req = urllib.request.Request(build_url(apt_id, start, end),
                                 headers={"User-Agent": USER_AGENT, "Referer": REFERER})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise AsilError(f"HTTP {r.status}")
        return r.read().decode("utf-8", errors="replace")


def parse(text: str) -> list[dict]:
    """응답 본문 → [{date: 'YYYY-MM-DD', sale, jeonse, wolse}] (날짜 오름차순)."""
    out = {}
    for m in _ROW.finditer(text):
        d = json.loads(m.group(1))
        yy, mm, dd = (int(x) for x in d["Date"].split("/"))
        key = f"{2000 + yy:04d}-{mm:02d}-{dd:02d}"
        out[key] = {"date": key, "sale": int(d.get("VM") or 0),
                    "jeonse": int(d.get("VJ") or 0), "wolse": int(d.get("VW") or 0)}
    return [out[k] for k in sorted(out)]


def read_csv(path: Path) -> dict:
    rows = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                rows[(r["date"], r["complex_id"])] = r
    return rows


def write_csv(path: Path, rows: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: (r["complex_id"], r["date"]))
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in ordered:
            w.writerow({k: r[k] for k in FIELDS})
    tmp.replace(path)


def merge(rows: dict, complex_id: str, naver_id: int, parsed: list[dict]) -> tuple:
    """새로 받은 값으로 덮어쓴다 (아실이 과거 값을 고치면 반영). (추가 수, 변경 수) 반환."""
    added = changed = 0
    for p in parsed:
        new = {"date": p["date"], "complex_id": complex_id, "naver_id": str(naver_id),
               "sale": str(p["sale"]), "jeonse": str(p["jeonse"]), "wolse": str(p["wolse"]),
               "total": str(p["sale"] + p["jeonse"] + p["wolse"])}
        key = (p["date"], complex_id)
        old = rows.get(key)
        if old is None:
            added += 1
        elif any(str(old.get(k)) != new[k] for k in FIELDS):
            changed += 1
        rows[key] = new
    return added, changed


def collect(complexes: list[dict], out: Path, start: date, end: date,
            fetcher=fetch, pause: float = 2.0, log=print) -> list[str]:
    """단지마다 1회 요청해 CSV에 병합. 실패한 단지 id 목록 반환."""
    rows = read_csv(out)
    failed = []
    for i, c in enumerate(complexes):
        cid, nid = c["id"], c.get("naver_id")
        if not nid:
            log(f"{cid}: naver_id 없음 → 건너뜀")
            continue
        if i:
            time.sleep(pause)
        try:
            parsed = parse(fetcher(int(nid), start, end))
            if not parsed:
                raise AsilError("빈 응답 (형식 변경 또는 차단 가능성)")
        except Exception as e:  # noqa: BLE001 — 한 단지 실패가 나머지를 막지 않게
            log(f"{cid}: 실패 — {type(e).__name__}: {e}")
            failed.append(cid)
            continue
        a, ch = merge(rows, cid, int(nid), parsed)
        last = parsed[-1]
        log(f"{c.get('name', cid)}: {len(parsed)}일 ({parsed[0]['date']}~{last['date']}) · 추가 {a} · 수정 {ch} · "
            f"최근 매매 {last['sale']} 전세 {last['jeonse']} 월세 {last['wolse']}")
    write_csv(out, rows)
    return failed
