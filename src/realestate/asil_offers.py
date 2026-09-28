"""아실 단지별 매물 목록 수집·추적 (Mac에서 실행, Python 3.9 이상, 표준 라이브러리만).

아실 단지 화면의 '매물' 목록(realty.asil.kr)을 단지마다 끝까지 받아
data/listings/asil/asil_offers.csv 에 매물 단위로 추적한다.

- 아실 매물 서버는 해외 접속을 끊는다 → GitHub Actions(미국)에서는 못 돌리고 국내 PC(Mac launchd)에서 실행.
- 매물의 SVC_DATE_STRT(게시일)는 중개사가 광고를 다시 올리면 바뀐다(대부분 최근 한 달 이내).
  그래서 최초 확인일(first_seen)·가격 변경(price_changed/prev_price)·내려간 날(last_seen, active=0)은
  매일 비교해서 이 파일이 직접 기록한다.
- 중개사 전화번호 등 개인 연락처는 저장하지 않는다.
- 한 단지라도 받다가 실패하면 그 단지의 기존 매물은 '내려감'으로 바꾸지 않는다.
"""
from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

URL = "https://realty.asil.kr/api_asil/data_sale_of_apt_nomal.aspx"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; real_estate-collector; +https://github.com/GTigerPapa/real_estate)",
    "Referer": "https://asil.kr/", "Origin": "https://asil.kr",
    "Content-Type": "application/x-www-form-urlencoded",
}
PAGE = 20
MAX_PAGES = 40            # 단지당 최대 800건 (안전장치)
KEEP_INACTIVE_DAYS = 120  # 내려간 매물은 이 기간 뒤 파일에서 정리
FIELDS = ["uid", "complex_id", "deal", "price", "rent", "dong", "floor", "excl_area", "supply_area",
          "desc", "broker", "posted", "first_seen", "last_seen", "price_changed", "prev_price", "active"]
DEALS = {"매매": "sale", "전세": "jeonse", "월세": "wolse"}


class AsilOfferError(RuntimeError):
    pass


def _amt(s) -> int:
    s = str(s or "0").replace(",", "").strip()
    return int(float(s)) if s else 0


def fetch_page(bld: str, n: int, timeout: float = 30) -> dict:
    body = urllib.parse.urlencode({
        "asil_bldcode": bld, "focus_bldcode": bld, "oidx": "1", "oby": "down", "total": str(PAGE),
        "dealmode": "A01,B01,B02,B03", "dong": "", "user": "", "ptp_no": "",
        "asil_preminum": "", "asil_focus": "", "last_mm_num": str(n * PAGE), "pre_mm_uid": "",
    }).encode()
    req = urllib.request.Request(URL, data=body, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_all(bld: str, fetcher=fetch_page, pause: float = 1.5) -> list:
    rows = []
    for n in range(MAX_PAGES):
        if n:
            time.sleep(pause)
        d = fetcher(bld, n)
        items = d.get("list_result") or []
        rows += items
        if not items or not d.get("next_page"):
            break
    return rows


def normalize(item: dict, complex_id: str) -> dict:
    """아실 응답 1건 → 저장 형식. price: 매매가 또는 보증금(만원), rent: 월세(만원)."""
    deal = DEALS.get(item.get("DEALTYPE_NM", ""), item.get("DEALTYPE_NM", ""))
    price = _amt(item.get("DEAL_AMT")) if deal == "sale" else _amt(item.get("WRRNT_AMT"))
    return {
        "uid": str(item["mm_uid"]), "complex_id": complex_id, "deal": deal,
        "price": str(price), "rent": str(_amt(item.get("LEASE_AMT")) if deal == "wolse" else ""),
        "dong": str(item.get("BDONG_NM") or "").strip(),
        "floor": str(item.get("CORES_FLR_CNT_NM") or item.get("CORES_FLR_CNT") or "").strip(),
        "excl_area": str(item.get("EXCLS_SPC") or ""), "supply_area": str(item.get("SPLY_SPC") or ""),
        "desc": " ".join(str(item.get("FETR_DESC") or "").split())[:120],
        "broker": str(item.get("BRKG_NM") or "").strip(),
        "posted": str(item.get("SVC_DATE_STRT") or "")[:10],
    }


def read_csv(path: Path) -> dict:
    rows = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                rows[r["uid"]] = r
    return rows


def write_csv(path: Path, rows: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: (r["complex_id"], r["active"] != "1", r["posted"], r["uid"]))
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    tmp.replace(path)


def merge(rows: dict, complex_id: str, fetched: list, today: str) -> dict:
    """한 단지의 이번 목록을 반영. 통계 {new, changed, gone, active} 반환."""
    seen = set()
    stats = {"new": 0, "changed": 0, "gone": 0, "active": 0}
    for item in fetched:
        n = normalize(item, complex_id)
        seen.add(n["uid"])
        old = rows.get(n["uid"])
        if old is None:
            n.update(first_seen=today, last_seen=today, price_changed="", prev_price="", active="1")
            stats["new"] += 1
        else:
            n.update(first_seen=old["first_seen"], last_seen=today, active="1",
                     price_changed=old.get("price_changed", ""), prev_price=old.get("prev_price", ""))
            if old.get("price") != n["price"] or (old.get("rent") or "") != (n["rent"] or ""):
                n.update(price_changed=today, prev_price=old.get("price", ""))
                stats["changed"] += 1
        rows[n["uid"]] = n
    for uid, r in rows.items():
        if r["complex_id"] == complex_id and uid not in seen and r.get("active") == "1":
            r["active"] = "0"   # last_seen = 마지막으로 보인 날
            stats["gone"] += 1
    stats["active"] = len(seen)
    return stats


def prune(rows: dict, today: str) -> None:
    from datetime import date
    t = date.fromisoformat(today)
    for uid in [u for u, r in rows.items() if r.get("active") != "1" and r.get("last_seen")
                and (t - date.fromisoformat(r["last_seen"])).days > KEEP_INACTIVE_DAYS]:
        del rows[uid]


def collect(complexes: list, out: Path, today: str, fetcher=fetch_page, pause: float = 1.5, log=print) -> list:
    """asil_id 가 있는 단지마다 목록 전체를 받아 추적 파일 갱신. 실패한 단지 id 목록 반환."""
    rows = read_csv(out)
    failed = []
    for c in complexes:
        cid, bld = c["id"], c.get("asil_id")
        if not bld:
            log(f"{cid}: asil_id 없음 → 건너뜀")
            continue
        try:
            items = fetch_all(str(bld), fetcher, pause)
            if not items:
                raise AsilOfferError("빈 목록 (형식 변경·차단 가능성)")
        except Exception as e:  # noqa: BLE001
            log(f"{cid}: 실패 — {type(e).__name__}: {e}")
            failed.append(cid)
            continue
        s = merge(rows, cid, items, today)
        log(f"{c.get('name', cid)}: 매물 {s['active']}건 · 신규 {s['new']} · 가격변경 {s['changed']} · 내려감 {s['gone']}")
        time.sleep(pause)
    prune(rows, today)
    write_csv(out, rows)
    return failed
