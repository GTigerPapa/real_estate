import math

import pandas as pd

from realestate import db, metrics, validate


def _df(rows, value="deal_amount"):
    df = pd.DataFrame(rows, columns=["deal_ym", value])
    df["complex_id"], df["complex_name"], df["size_band"] = "x", "X", "84"
    df["is_canceled"] = 0
    df["deal_date"] = pd.to_datetime(df["deal_ym"] + "-15")
    return df


def test_window_median_pools_deals_not_medians():
    df = _df([("2025-01", 100), ("2025-02", 200), ("2025-02", 210), ("2025-02", 220), ("2025-04", 400)])
    m1 = metrics.window_median(df, "deal_amount").set_index("deal_ym")
    assert m1.loc["2025-02", "median"] == 210 and m1.loc["2025-02", "n"] == 3
    assert m1.loc["2025-03", "n"] == 0 and math.isnan(m1.loc["2025-03", "median"])
    m3 = metrics.window_median(df, "deal_amount", window=3).set_index("deal_ym")
    # 2025-03 후행 3개월 = 01~03: [100,200,210,220] → 205
    assert m3.loc["2025-03", "median"] == 205 and m3.loc["2025-03", "n"] == 4
    c3 = metrics.window_median(df, "deal_amount", window=3, center=True).set_index("deal_ym")
    assert c3.loc["2025-03", "n"] == 4  # 02~04


def test_jeonse_ratio():
    t = _df([("2025-01", 100000), ("2025-01", 120000)])
    j = _df([("2025-01", 55000)], value="deposit")
    r = metrics.jeonse_ratio(t, j).iloc[0]
    assert r["trade_median"] == 110000 and r["jeonse_n"] == 1 and r["ratio"] == 0.5


def test_outliers():
    df = _df([("2025-01", 100), ("2025-01", 102), ("2025-01", 98), ("2025-01", 70)])
    df["id"] = range(len(df))
    o = metrics.outliers(df, pct=15, min_n=3)
    assert list(o["deal_amount"]) == [70]


def test_report_smoke(conn, fixture_text):
    from tests.test_db import _rows
    db.upsert_rows(conn, "apt_trade", _rows(fixture_text("trade_sample.xml")), "t")
    db.sync_config(conn, {"size_bands": [{"band": "59", "min": 57, "max": 62}, {"band": "84", "min": 82, "max": 87}]},
                   [{"id": "x", "name": "테스트", "sgg_cd": "11740", "umd_nm": "상일동",
                     "apt_seq": ["11740-9999"], "bands": [59, 84]}])
    text = validate.build_report(conn, {})
    assert "매매 3건 (해제 1)" in text and "테스트 59" in text


def test_loaders_keep_columns_when_empty(conn):
    db.sync_config(conn, {"size_bands": [{"band": "84", "min": 82, "max": 87}]},
                   [{"id": "x", "name": "X", "sgg_cd": "11740", "umd_nm": "상일동", "apt_seq": ["s"], "bands": [84]}])
    r = metrics.load_rents(conn, rent_type=None)
    assert r.empty and {"complex_id", "size_band", "deal_ym", "deposit"} <= set(r.columns)


def test_rent_composition():
    df = pd.DataFrame({
        "deal_ym": ["2025-01", "2025-01", "2025-02", "2025-02", "2025-03"],
        "rent_type": ["전세", "전세", "전세", "월세", "월세"],
        "contract_type": ["신규", "갱신", None, "신규", "갱신"],
    })
    df["complex_id"], df["complex_name"], df["size_band"] = "x", "X", "84"
    rc = metrics.rent_composition(df, ["2025-01", "2025-02", "2025-03"]).set_index("deal_ym")
    assert rc.loc["2025-01", ["new_jeonse", "renew_jeonse", "wolse"]].tolist() == [1, 1, 0]
    assert rc.loc["2025-02", "new_jeonse"] == 1  # 유형 미상은 신규로
    # 3개월 풀링: 전세 3건 중 갱신 1건, 전월세 5건 중 월세 2건
    assert abs(rc.loc["2025-03", "renew_ratio"] - 1 / 3) < 1e-9 and rc.loc["2025-03", "renew_n"] == 3
    assert abs(rc.loc["2025-03", "wolse_share"] - 2 / 5) < 1e-9
