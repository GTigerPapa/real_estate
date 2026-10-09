import csv
from pathlib import Path

from realestate import naver_offers as no, webexport


def art(a, g, t="A1", dong="101", fl="5", ex=84.97, p=1_400_000_000, w=0, r=0, d="", dt="2026-10-09"):
    return {"a": a, "g": g, "t": t, "dong": dong, "fl": fl, "ex": ex, "p": p, "w": w, "r": r, "d": d, "dt": dt, "bk": "X", "rc": 2}


def dump(day, items, ok=True):
    return {"captured_at": f"{day}T09:00:00+09:00",
            "complexes": [{"id": "c1", "name": "C1", "responses": [], "articles": {"ok": ok, "items": items}}]}


def test_track_new_change_gone(tmp_path):
    p = tmp_path / "n.csv"
    no.update(p, dump("2026-10-09", [art("1", "1"), art("2", "1"), art("3", "3", t="B2", w=100_000_000, r=2_000_000)]), log=lambda *_: None)
    rows = no.read_csv(p)
    assert rows["1"]["price"] == "140000" and rows["3"]["deal"] == "wolse" and rows["3"]["rent"] == "200"
    # 다음 날: 1번 가격 인하, 2번 내려감
    st = no.update(p, dump("2026-10-10", [art("1", "1", p=1_350_000_000), art("3", "3", t="B2", w=100_000_000, r=2_000_000)]),
                   log=lambda *_: None)["c1"]
    rows = no.read_csv(p)
    assert st == {"new": 0, "changed": 1, "gone": 1, "active": 2}
    assert rows["1"]["prev_price"] == "140000" and rows["1"]["price_changed"] == "2026-10-10"
    assert rows["2"]["active"] == "0" and rows["1"]["first_seen"] == "2026-10-09"
    # 목록을 끝까지 못 받은 날은 내려감 판정 안 함
    no.update(p, dump("2026-10-11", [art("1", "1", p=1_350_000_000)], ok=False), log=lambda *_: None)
    assert no.read_csv(p)["3"]["active"] == "1"


def test_strip_articles_keeps_summary():
    d = dump("2026-10-09", [art("1", "1")])
    d["discovery"] = [1]
    s = no.strip_articles(d)
    assert "articles" not in s["complexes"][0] and s["complexes"][0]["articles_summary"]["n"] == 1 and "discovery" not in s
    assert "articles" in d["complexes"][0]   # 원본은 그대로


def test_load_offers_merges_sources(tmp_path):
    a = tmp_path / "a.csv"
    with a.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["uid", "complex_id", "deal", "price", "rent", "dong", "floor", "excl_area", "supply_area",
                                          "desc", "broker", "posted", "first_seen", "last_seen", "price_changed", "prev_price", "active"])
        w.writeheader()
        base = dict(complex_id="c1", deal="sale", rent="", dong="101", excl_area="84.97", supply_area="", broker="b",
                    posted="2026-10-01", first_seen="2026-10-01", last_seen="2026-10-09", price_changed="", prev_price="", active="1")
        w.writerow(dict(base, uid="x1", price="140000", floor="5", desc=""))
        w.writerow(dict(base, uid="x2", price="150000", floor="저", desc=""))
    n = tmp_path / "n.csv"
    no.update(n, dump("2026-10-09", [art("1", "1", fl="5"), art("2", "2", fl="5", p=1_600_000_000, d="세안고 매매")]),
              log=lambda *_: None)
    bands = [{"band": "84", "min": 82, "max": 87}]
    o = webexport.load_offers(a, bands, n)
    by = {(i["p"]): i for i in o["items"]}
    assert by[140000]["src"] == "an" and by[140000]["n"] == 1      # 같은 물건 → 1줄, 출처 둘 다
    assert by[150000]["src"] == "a" and by[160000]["src"] == "n" and by[160000]["ten"] == "t"
    assert o["naver_through"] == "2026-10-09"
    # 네이버 목록이 오래되면 빠진다
    no.update(n, dump("2026-10-09", []), log=lambda *_: None)
    assert all(i["src"] != "n" for i in webexport.load_offers(a, bands, Path(tmp_path / "none.csv"))["items"])
