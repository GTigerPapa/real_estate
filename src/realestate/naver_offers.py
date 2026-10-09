"""네이버 매물 목록 추적 (북마클릿 덤프의 complexes[].articles → data/listings/naver/naver_offers.csv).

아실 매물 추적(asil_offers.py)과 같은 형식으로 매물(중개사 광고) 단위로 기록한다.
- uid: 네이버 매물 번호. grp: 네이버가 같은 물건으로 묶은 대표 매물 번호.
- 덤프를 받은 날(captured_at)이 '오늘'. 네이버는 북마클릿·자동 실행이 돈 날만 갱신된다.
- 한 단지의 목록을 끝까지 못 받았으면(ok=False) 그 단지 매물은 '내려감'으로 바꾸지 않는다.
- 가격 단위: 네이버는 원 → 만원으로 바꿔 아실과 맞춘다. 중개사 연락처는 저장하지 않는다.
표준 라이브러리만 사용 (Mac Python 3.9 의 scripts/save_listings.py 가 쓴다).
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

FIELDS = ["uid", "grp", "complex_id", "deal", "price", "rent", "dong", "floor", "excl_area", "supply_area",
          "desc", "broker", "realtors", "posted", "first_seen", "last_seen", "price_changed", "prev_price", "active"]
DEALS = {"A1": "sale", "B1": "jeonse", "B2": "wolse"}
KEEP_INACTIVE_DAYS = 120


def _man(won) -> int:
    try:
        return int(round(float(won or 0) / 10000))
    except (TypeError, ValueError):
        return 0


def normalize(a: dict, complex_id: str) -> dict | None:
    deal = DEALS.get(a.get("t"))
    if not deal or not a.get("a"):
        return None
    price = _man(a.get("p")) if deal == "sale" else _man(a.get("w"))
    return {
        "uid": str(a["a"]), "grp": str(a.get("g") or a["a"]), "complex_id": complex_id, "deal": deal,
        "price": str(price), "rent": str(_man(a.get("r"))) if deal == "wolse" else "",
        "dong": str(a.get("dong") or "").removesuffix("동").strip(), "floor": str(a.get("fl") or "").strip(),
        "excl_area": "" if a.get("ex") in (None, "") else f"{float(a['ex']):.2f}",
        "supply_area": "" if a.get("sp") in (None, "") else f"{float(a['sp']):.2f}",
        "desc": " ".join(str(a.get("d") or "").split())[:120], "broker": str(a.get("bk") or "").strip(),
        "realtors": str(a.get("rc") or ""), "posted": str(a.get("dt") or "")[:10],
    }


def read_csv(path: Path) -> dict:
    rows = {}
    if Path(path).exists():
        with Path(path).open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                rows[r["uid"]] = r
    return rows


def write_csv(path: Path, rows: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: (r["complex_id"], r["active"] != "1", r["posted"], r["uid"]))
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    tmp.replace(path)


def merge(rows: dict, complex_id: str, items: list, today: str, complete: bool) -> dict:
    seen = set()
    st = {"new": 0, "changed": 0, "gone": 0, "active": 0}
    for a in items:
        n = normalize(a, complex_id)
        if n is None or n["uid"] in seen:
            continue
        seen.add(n["uid"])
        old = rows.get(n["uid"])
        if old is None:
            n.update(first_seen=today, last_seen=today, price_changed="", prev_price="", active="1")
            st["new"] += 1
        else:
            if old.get("last_seen", "") > today:      # 더 오래된 덤프를 나중에 넣는 경우: 무시
                continue
            n.update(first_seen=old["first_seen"], last_seen=today, active="1",
                     price_changed=old.get("price_changed", ""), prev_price=old.get("prev_price", ""))
            if old.get("price") != n["price"] or (old.get("rent") or "") != (n["rent"] or ""):
                n.update(price_changed=today, prev_price=old.get("price", ""))
                st["changed"] += 1
        rows[n["uid"]] = n
    if complete:
        for uid, r in rows.items():
            if r["complex_id"] == complex_id and uid not in seen and r.get("active") == "1" and r.get("last_seen", "") < today:
                r["active"] = "0"
                st["gone"] += 1
    st["active"] = len(seen)
    return st


def prune(rows: dict, today: str) -> None:
    t = date.fromisoformat(today)
    for uid in [u for u, r in rows.items() if r.get("active") != "1" and r.get("last_seen")
                and (t - date.fromisoformat(r["last_seen"])).days > KEEP_INACTIVE_DAYS]:
        del rows[uid]


def has_articles(dump: dict) -> bool:
    return any(isinstance(c.get("articles"), dict) for c in dump.get("complexes", []))


def update(path: Path, dump: dict, log=print) -> dict:
    """덤프 하나를 추적 파일에 반영. {complex_id: stats} 반환 (articles 가 없는 덤프면 빈 dict)."""
    if not has_articles(dump):
        return {}
    today = str(dump.get("captured_at", ""))[:10]
    rows = read_csv(path)
    out = {}
    for c in dump["complexes"]:
        A = c.get("articles")
        if not isinstance(A, dict):
            continue
        items = A.get("items") or []
        complete = bool(A.get("ok")) and bool(items)
        st = merge(rows, c["id"], items, today, complete)
        out[c["id"]] = st
        log(f"{c.get('name', c['id'])}: 네이버 매물 {st['active']}건 · 신규 {st['new']} · 가격변경 {st['changed']} · 내려감 {st['gone']}"
            + ("" if complete else " (목록을 끝까지 못 받아 내려감 판정 생략)"))
    prune(rows, today)
    write_csv(path, rows)
    return out


def strip_articles(dump: dict) -> dict:
    """저장소에 남길 원본 덤프에서는 매물 목록을 뺀다 (목록은 추적 CSV에 들어감 → 저장소 용량 절약)."""
    d = dict(dump)
    d["complexes"] = []
    for c in dump.get("complexes", []):
        c2 = {k: v for k, v in c.items() if k != "articles"}
        if isinstance(c.get("articles"), dict):
            c2["articles_summary"] = {"ok": c["articles"].get("ok"), "n": len(c["articles"].get("items") or []),
                                      "trades": c["articles"].get("trades")}
        d["complexes"].append(c2)
    d.pop("discovery", None)
    return d
