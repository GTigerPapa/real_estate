import pytest

from realestate.api.parse import (TRADE_KEY, ApiResponseError, assign_dup_seq, normalize_rent,
                                  normalize_trade, parse_response, to_iso_date, to_int_amount)


def test_parse_trade(fixture_text):
    p = parse_response(fixture_text("trade_sample.xml"))
    assert p.result_code == "000" and p.total_count == 3 and len(p.items) == 3
    r = normalize_trade(p.items[0])
    assert r["deal_date"] == "2025-08-07"
    assert r["deal_amount"] == 150000
    assert r["exclu_use_ar"] == 84.97 and r["floor"] == 12
    assert r["rgst_date"] == "2025-10-01" and r["is_canceled"] == 0 and r["cancel_date"] is None
    c = normalize_trade(p.items[1])
    assert c["is_canceled"] == 1 and c["cancel_date"] == "2025-09-15"
    assert c["apt_dong"] == "" and c["agent_sgg_nm"] is None


def test_error_envelope(fixture_text):
    with pytest.raises(ApiResponseError) as ei:
        parse_response(fixture_text("error_key.xml"))
    assert ei.value.code == "30"


def test_value_conversions():
    assert to_int_amount("1,234") == 1234 and to_int_amount(" ") is None
    assert to_iso_date("26.05.07") == "2026-05-07"
    assert to_iso_date("2026-5-7") == "2026-05-07"
    assert to_iso_date(None) is None and to_iso_date("x") is None


def test_dup_seq(fixture_text):
    rows = [normalize_trade(i) for i in parse_response(fixture_text("trade_sample.xml")).items]
    assign_dup_seq(rows, TRADE_KEY)
    assert sorted(r["dup_seq"] for r in rows) == [1, 1, 2]


def test_rent_type():
    base = {"sggCd": "11740", "aptSeq": "s", "dealYear": "2025", "dealMonth": "1", "dealDay": "2",
            "excluUseAr": "84.9", "floor": "5", "deposit": "80,000"}
    assert normalize_rent({**base, "monthlyRent": "0"})["rent_type"] == "전세"
    r = normalize_rent({**base, "monthlyRent": "120", "contractTerm": "25.01~27.01"})
    assert r["rent_type"] == "월세" and r["monthly_rent"] == 120 and r["contract_term"] == "25.01~27.01"


def test_parse_rent_real_layout(fixture_text):
    # 실응답 구조: aptDong·umdCd 없음, 빈 값은 공백
    rows = [normalize_rent(i) for i in parse_response(fixture_text("rent_sample.xml")).items]
    new, renew, monthly = rows
    assert new["rent_type"] == "전세" and new["deposit"] == 90000 and new["contract_type"] == "신규"
    assert new["contract_term"] == "26.03~28.03" and new["pre_deposit"] is None and new["umd_cd"] is None
    assert renew["contract_type"] == "갱신" and renew["use_rr_right"] == "사용" and renew["pre_deposit"] == 70000
    assert monthly["rent_type"] == "월세" and monthly["monthly_rent"] == 250
    assert monthly["contract_type"] is None and monthly["contract_term"] == ""
