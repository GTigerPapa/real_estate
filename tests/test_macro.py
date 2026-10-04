import json

from realestate import ecos, macro

SERIES = [{"id": "permit_seoul", "name": "인허가", "stat": "901Y105", "item": "SEO", "ytd": True},
          {"id": "house_loan", "name": "대출", "stat": "151Y005", "item": "11100A0"},
          {"id": "csi_house", "name": "CSI", "stat": "511Y002", "item": "FMFB", "item2": "99988"}]


def test_url_has_item2_and_no_key_in_error():
    s = SERIES[2]
    assert ecos.url("KEY", s, "201301", "202609").endswith("/511Y002/M/201301/202609/FMFB/99988")

    def boom(*a, **k):
        raise OSError("https://ecos.bok.or.kr/api/StatisticSearch/SECRETKEY/...")
    try:
        ecos.fetch_series("SECRETKEY", s, "201301", "202609", opener=boom)
    except ecos.EcosError as e:
        assert "SECRETKEY" not in str(e)


def test_collect_and_derived(tmp_path):
    data = {"permit_seoul": [("2025-11", 100), ("2025-12", 150), ("2026-01", 10), ("2026-02", 30)],
            "house_loan": [("2025-11", 1000), ("2025-12", 3500), ("2026-01", 4500), ("2026-02", 4000)],
            "csi_house": [("2025-11", 110), ("2025-12", 120), ("2026-01", 125), ("2026-02", 125)]}
    out = tmp_path / "ecos.csv"
    failed = ecos.collect(SERIES, out, "202511", "202602", key="k", fetcher=lambda key, s, a, b: data[s["id"]],
                          pause=0, log=lambda *_: None)
    assert failed == []
    W = macro.load(out, SERIES)
    assert W["permit_seoul_m"].tolist() == [100, 50, 10, 20]      # 연중 누계 → 월별 (1월은 그대로)
    assert W["loan_flow"].round(1).tolist()[1:] == [2.5, 1.0, -0.5]  # 십억원 잔액 → 조원 순증
    m = macro.build(out, {"ecos": {"series": SERIES}})
    assert m["months"] == ["2025-11", "2025-12", "2026-01", "2026-02"]
    json.dumps(m, allow_nan=False)
