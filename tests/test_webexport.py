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
