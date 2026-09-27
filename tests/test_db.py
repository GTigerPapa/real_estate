from realestate import db
from realestate.api.parse import TRADE_KEY, assign_dup_seq, normalize_trade, parse_response


def _rows(xml):
    rows = [normalize_trade(i) for i in parse_response(xml).items]
    return assign_dup_seq(rows, TRADE_KEY)


def test_upsert_idempotent_and_cancel_update(conn, fixture_text):
    xml = fixture_text("trade_sample.xml")
    assert db.upsert_rows(conn, "apt_trade", _rows(xml), "2025-09-01T00:00:00+09:00") == (3, 0)
    # 재수집: 첫 건이 해제됨
    xml2 = xml.replace("<cdealDay> </cdealDay><cdealType> </cdealType><dealAmount>150,000",
                       "<cdealDay>25.10.02</cdealDay><cdealType>O</cdealType><dealAmount>150,000")
    assert db.upsert_rows(conn, "apt_trade", _rows(xml2), "2025-10-05T00:00:00+09:00") == (0, 3)
    r = conn.execute("SELECT * FROM apt_trade WHERE deal_amount=150000").fetchone()
    assert r["is_canceled"] == 1 and r["cancel_date"] == "2025-10-02"
    assert r["first_seen_at"].startswith("2025-09-01") and r["last_seen_at"].startswith("2025-10-05")
    assert conn.execute("SELECT COUNT(*) FROM apt_trade").fetchone()[0] == 3


def test_raw_dedupe(conn):
    args = ("trade", "11740", "202508", 1)
    assert db.insert_raw(conn, *args, "t1", "000", 1, "<a/>") is True
    assert db.insert_raw(conn, *args, "t2", "000", 1, "<a/>") is False
    assert db.insert_raw(conn, *args, "t3", "000", 1, "<b/>") is True
    ids = [r[0] for r in conn.execute("SELECT id FROM raw_response ORDER BY id")]
    assert len(ids) == 3
    assert db.raw_body(conn, ids[1]) == "<a/>"


def test_views_match_and_band(conn, fixture_text):
    db.upsert_rows(conn, "apt_trade", _rows(fixture_text("trade_sample.xml")), "t")
    db.sync_config(conn, {"size_bands": [{"band": "59", "min": 55, "max": 65},
                                         {"band": "84", "min": 80, "max": 90}]},
                   [{"id": "x", "name": "테스트", "sgg_cd": "11740", "umd_nm": "상일동",
                     "apt_seq": ["11740-9999"], "bands": [59, 84]}])
    rows = conn.execute("SELECT size_band, COUNT(*) n FROM v_trade GROUP BY size_band ORDER BY 1").fetchall()
    assert [(r[0], r[1]) for r in rows] == [("59", 2), ("84", 1)]
    # 보조 키(지번+단지명)만으로도 매칭, 중복 매칭 없음
    db.sync_complexes(conn, [{"id": "x", "name": "테스트", "sgg_cd": "11740", "umd_nm": "상일동",
                              "apt_seq": ["11740-9999"], "fallback": [{"jibun": "100", "apt_nm": "테스트자이"}]}])
    assert conn.execute("SELECT COUNT(*) FROM v_trade").fetchone()[0] == 3
