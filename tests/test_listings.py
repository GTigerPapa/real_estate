import json
import subprocess
import shutil

import pytest

from realestate import db, listings

DUMP = {
    "format": 1, "captured_at": "2026-09-28T07:10:00+09:00", "page": "https://fin.land.naver.com/",
    "complexes": [{
        "id": "x", "naver_id": 1, "name": "X",
        "responses": [
            {"key": "article_stats", "url": "/a", "params": {"complexNumber": 1}, "status": 200, "ok": True,
             "json": {"result": {"dealCount": 12, "leaseCount": "3", "isNew": True, "name": "n"}}},
            {"key": "asking_price", "url": "/b", "params": {"complexNumber": 1, "tradeType": "A1", "pyeongTypeNumber": 0},
             "status": 200, "ok": True, "json": {"result": {"minPrice": "1,450,000,000", "maxPrice": 1600000000}}},
            {"key": "asking_price", "url": "/b", "params": {"complexNumber": 1, "tradeType": "B1", "pyeongTypeNumber": 0},
             "status": 200, "ok": True, "json": {"result": {"minPrice": 700000000, "maxPrice": 800000000}}},
            {"key": "market_price_recent", "url": "/c", "params": {}, "status": 429, "ok": False, "text": "no"},
        ]}],
    "discovery": [],
}
RULES = {"listing_metrics": {
    "sale_count": {"endpoint": "article_stats", "trade": "A1", "paths": ["(?i)deal.*count$"]},
    "lease_count": {"endpoint": "article_stats", "trade": "B1", "paths": ["(?i)lease.*count$"]},
    "sale_min_ask": {"endpoint": "asking_price", "trade": "A1", "paths": ["(?i)min.*price"]},
    "lease_min_ask": {"endpoint": "asking_price", "trade": "B1", "paths": ["(?i)min.*price"]},
}}


def _write(tmp_path, name="naver_listings_20260928_0710.json", dump=DUMP):
    p = tmp_path / name
    p.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    return p


def test_flatten_numbers():
    flat = dict(listings.flatten_numbers({"a": {"b": [1, "2", "x", True, None], "c": "1,234"}}))
    assert flat == {"a.b[0]": 1.0, "a.b[1]": 2.0, "a.c": 1234.0}


def test_ingest_idempotent_and_snapshot(conn, tmp_path):
    p = _write(tmp_path)
    r = listings.ingest_file(conn, p)
    assert r["loaded"] and r["snap_date"] == "2026-09-28" and r["metrics"] == 6  # 실패 응답(429)은 제외
    assert listings.ingest_file(conn, p)["loaded"] is False
    assert conn.execute("SELECT COUNT(*) FROM listing_raw").fetchone()[0] == 1
    snap = listings.snapshot(conn, RULES).set_index("metric")["value"]
    assert snap["sale_count"] == 12 and snap["lease_count"] == 3
    assert snap["sale_min_ask"] == 1_450_000_000 and snap["lease_min_ask"] == 700_000_000
    paths = listings.available_paths(conn)
    assert "result.minPrice" in set(paths["path"])


def test_ingest_dir_reports_bad_file(conn, tmp_path):
    _write(tmp_path)
    (tmp_path / "naver_listings_bad.json").write_text("{not json", encoding="utf-8")
    results = dict(listings.ingest_dir(conn, tmp_path))
    assert results["naver_listings_20260928_0710.json"]["loaded"] is True
    assert "error" in results["naver_listings_bad.json"]
    assert listings.snap_date_of("2026-09-27T23:30:00Z") == "2026-09-28"


def test_load_dump_rejects_wrong_format(tmp_path):
    p = _write(tmp_path, dump={"format": 99, "complexes": []})
    with pytest.raises(listings.DumpError):
        listings.load_dump(p)


def test_bookmarklet_builds_and_parses():
    from tools import build_bookmarklet as bb
    js = bb.build_js()
    assert js.startswith("javascript:") and '"naver_id":121977' in js and "\n" not in js
    if shutil.which("node"):
        subprocess.run(["node", "--check", "-"], input=js[len("javascript:"):], text=True, check=True)
