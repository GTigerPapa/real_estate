from realestate import asil_offers as ao


def item(uid, deal="매매", amt="185,000", wrrnt="0", lease="0", posted="2026-09-28", dong="105", flr="저"):
    return {"mm_uid": uid, "DEALTYPE_NM": deal, "DEAL_AMT": amt, "WRRNT_AMT": wrrnt, "LEASE_AMT": lease,
            "BDONG_NM": dong, "CORES_FLR_CNT_NM": flr, "EXCLS_SPC": "59.93", "SPLY_SPC": "83.30",
            "FETR_DESC": " 로얄동층,  풀에어컨 ", "BRKG_NM": "OO공인중개사", "SVC_DATE_STRT": posted,
            "RPRST_TEL": "02-000-0000", "TEL_ADD": "010-0000-0000"}


def pages(items):
    """items 를 20건씩 나눠 주는 가짜 fetcher."""
    def f(bld, n):
        chunk = items[n * ao.PAGE:(n + 1) * ao.PAGE]
        return {"list_result": chunk, "next_page": (n + 1) * ao.PAGE < len(items)}
    return f


C = [{"id": "gx", "name": "고덕자이", "asil_id": "1"}, {"id": "ci", "name": "아이파크", "asil_id": "2"}]


def test_normalize_prices_and_no_phone():
    assert ao.normalize(item("1"), "gx")["price"] == "185000"
    j = ao.normalize(item("2", "전세", "0", "130,000"), "gx")
    assert (j["deal"], j["price"], j["rent"]) == ("jeonse", "130000", "")
    w = ao.normalize(item("3", "월세", "0", "30,000", "300"), "gx")
    assert (w["deal"], w["price"], w["rent"]) == ("wolse", "30000", "300")
    assert "010" not in str(ao.normalize(item("4"), "gx")) and ao.normalize(item("4"), "gx")["desc"] == "로얄동층, 풀에어컨"


def test_fetch_all_pages():
    items = [item(str(i)) for i in range(45)]
    assert len(ao.fetch_all("1", pages(items), pause=0)) == 45


def test_tracking_new_price_change_gone_and_failure(tmp_path):
    out = tmp_path / "o.csv"
    day1 = {"1": [item("a"), item("b")], "2": [item("c")]}
    ao.collect(C, out, "2026-09-29", fetcher=lambda b, n: {"list_result": day1[b] if n == 0 else [], "next_page": False},
               pause=0, log=lambda m: None)
    r = ao.read_csv(out)
    assert r["a"]["first_seen"] == "2026-09-29" and r["a"]["active"] == "1"

    # 다음날: a 가격 인하, b 내려감, d 신규 / 아이파크는 요청 실패 → c 는 그대로 유지
    day2 = {"1": [item("a", amt="180,000"), item("d", posted="2026-09-30")]}

    def f2(b, n):
        if b == "2":
            raise OSError("reset")
        return {"list_result": day2[b] if n == 0 else [], "next_page": False}
    failed = ao.collect(C, out, "2026-09-30", fetcher=f2, pause=0, log=lambda m: None)
    r = ao.read_csv(out)
    assert failed == ["ci"]
    assert (r["a"]["price"], r["a"]["prev_price"], r["a"]["price_changed"], r["a"]["first_seen"]) == \
        ("180000", "185000", "2026-09-30", "2026-09-29")
    assert r["b"]["active"] == "0" and r["b"]["last_seen"] == "2026-09-29"
    assert r["d"]["first_seen"] == "2026-09-30" and r["c"]["active"] == "1"


def test_prune_old_inactive():
    rows = {"x": {"uid": "x", "active": "0", "last_seen": "2026-01-01"},
            "y": {"uid": "y", "active": "0", "last_seen": "2026-09-01"}}
    ao.prune(rows, "2026-09-30")
    assert list(rows) == ["y"]
