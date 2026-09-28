import json

from realestate import db, listings, webexport
from tests.test_db import _rows
from tests.test_listings import DUMP

SETTINGS = {
    "buy_cap_manwon": 140000,
    "size_bands": [{"band": "59", "min": 57, "max": 62}, {"band": "84", "min": 82, "max": 87}],
    "listing_metrics": {
        "sale_count": {"endpoint": "article_stats", "paths": ["(?i)deal.*count$"]},
        "sale_min_ask": {"endpoint": "asking_price", "trade": "A1", "paths": ["(?i)min.*price"]},
    },
}
COMPLEXES = [{"id": "x", "name": "테스트자이", "short": "테스트", "sgg_cd": "11740", "umd_nm": "상일동",
              "apt_seq": ["11740-9999"], "bands": [59, 84]}]


def _payload(conn, tmp_path):
    db.upsert_rows(conn, "apt_trade", _rows_fixture(), "t")
    db.sync_config(conn, SETTINGS, COMPLEXES)
    p = tmp_path / "naver_listings_20260928_0710.json"
    p.write_text(json.dumps(DUMP, ensure_ascii=False), encoding="utf-8")
    listings.ingest_file(conn, p)
    return webexport.build_payload(conn, SETTINGS, COMPLEXES)


def _rows_fixture():
    from pathlib import Path
    return _rows((Path(__file__).parent / "fixtures" / "trade_sample.xml").read_text(encoding="utf-8"))


def test_payload_structure(conn, tmp_path):
    d = _payload(conn, tmp_path)
    assert d["format"] == 1 and d["cap"] == 140000 and d["bands"] == ["59", "84"]
    assert d["months"][-1] == "2025-08" and len(d["months"]) == 36
    c = d["complexes"][0]
    assert c["short"] == "테스트" and c["bands"] == ["59", "84"] and c["slot"] == 0
    b84 = c["b"]["84"]
    assert len(b84["trade_3m"]["v"]) == 36 and b84["trade_3m"]["v"][-1] == 150000
    assert b84["summary"]["median"] == 150000 and b84["summary"]["vs_cap"] == 10000
    # 59형: 해제 1건 + 정상 1건(직거래) → 중앙값은 직거래 제외라 없음, 거래 목록엔 둘 다
    b59 = c["b"]["59"]
    assert b59["summary"]["median"] is None and len(b59["deals"]) == 2
    assert sum(b59["volume"]["canceled"]) == 1 and sum(b59["volume"]["direct"]) == 1
    json.dumps(d, allow_nan=False)  # NaN 이 섞이면 브라우저 JSON.parse 실패


def test_payload_listing_units(conn, tmp_path):
    d = _payload(conn, tmp_path)
    L = d["complexes"][0]["listings"]
    # 테스트 덤프의 id 'x' 단지: 매매 12건, 최저호가 14.5억(원) → 145000 만원
    assert L == [{"d": "2026-09-28", "sale": 12, "lease": None, "wolse": None,
                  "sale_min": 145000, "sale_max": None, "lease_min": None}]
    assert d["listing_through"] == "2026-09-28"


def test_payload_asil_columns(conn, tmp_path):
    csv = tmp_path / "asil.csv"
    csv.write_text("date,complex_id,naver_id,sale,jeonse,wolse,total\n"
                   "2026-09-28,x,1,59,6,4,69\n2026-09-27,x,1,58,6,4,68\n2026-09-28,other,2,1,1,1,3\n", encoding="utf-8")
    db.upsert_rows(conn, "apt_trade", _rows_fixture(), "t")
    db.sync_config(conn, SETTINGS, COMPLEXES)
    d = webexport.build_payload(conn, SETTINGS, COMPLEXES, asil_csv=csv)
    assert d["complexes"][0]["asil"] == {"d": ["2026-09-27", "2026-09-28"], "s": [58, 59], "j": [6, 6], "w": [4, 4]}
    assert d["asil_through"] == "2026-09-28"
    # CSV 가 없으면 빈 열
    d2 = webexport.build_payload(conn, SETTINGS, COMPLEXES, asil_csv=tmp_path / "none.csv")
    assert d2["complexes"][0]["asil"]["d"] == [] and d2["asil_through"] is None


def test_payload_recent_trades_and_grouped_offers(conn, tmp_path):
    offers = tmp_path / "offers.csv"
    head = "uid,complex_id,deal,price,rent,dong,floor,excl_area,supply_area,desc,broker,posted,first_seen,last_seen,price_changed,prev_price,active\n"
    offers.write_text(head +
        "1,x,sale,185000,,105,저,59.93,83.3,로얄동,A,2026-09-21,2026-09-29,2026-09-30,,,1\n"
        "2,x,sale,185000,,105,저,59.93,83.3,,B,2026-09-28,2026-09-29,2026-09-30,,,1\n"          # 같은 물건, 다른 중개사
        "3,x,wolse,30000,300,110,중,84.44,110.4,,C,2026-09-29,2026-09-30,2026-09-30,2026-09-30,35000,1\n"
        "4,x,sale,200000,,101,고,84.9,110,,D,2026-09-25,2026-09-29,2026-09-29,,,0\n", encoding="utf-8")  # 내려간 매물
    db.upsert_rows(conn, "apt_trade", _rows_fixture(), "t")
    db.sync_config(conn, SETTINGS, COMPLEXES)
    d = webexport.build_payload(conn, SETTINGS, COMPLEXES, offers_csv=offers, asil_csv=tmp_path / "none.csv")
    o = d["offers"]
    assert len(o) == 2 and o[0]["t"] == "wolse"            # 최신 등록 먼저
    assert (o[0]["p"], o[0]["r"], o[0]["chg"], o[0]["prev"]) == (30000, 300, "2026-09-30", 35000)
    assert (o[1]["n"], o[1]["reg"], o[1]["upd"], o[1]["desc"]) == (2, "2026-09-21", "2026-09-28", "로얄동")
    assert d["offers_since"] == "2026-09-29" and d["offers_through"] == "2026-09-30"
    tr = d["trades_recent"]
    assert tr and all(a["d"] >= b["d"] for a, b in zip(tr, tr[1:]))   # 계약일 최신순
    assert {"c", "d", "p", "f", "dong", "ar", "t", "x", "pub"} <= set(tr[0])
    json.dumps(d, allow_nan=False)
