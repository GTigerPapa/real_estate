import numpy as np
import pandas as pd

from realestate import overlap


def test_price84_pools_three_months():
    months = ["2026-01", "2026-02", "2026-03"]
    t = pd.DataFrame({"deal_ym": ["2026-01", "2026-02", "2026-03", "2026-03"],
                      "deal_amount": [84000, 168000, 84000, 84000], "exclu_use_ar": [84, 84, 42, 84]})
    p = overlap.price84(t, months)
    assert p["vol"] == [1, 1, 2]
    assert p["v"][0] == 84000 and p["n"][2] == 4          # 3월: 1·2·3월 4건 풀링, ㎡당 1000·2000·2000·1000 → 중앙값 1500 × 84
    assert p["v"][2] == 126000


def test_lead_lag_finds_negative_lag():
    rng = np.random.default_rng(0)
    months = [f"{2023 + (i // 12)}-{i % 12 + 1:02d}" for i in range(40)]
    lst = 100 * np.exp(np.cumsum(rng.normal(0, 0.08, 40)))
    # 가격은 3개월 전 매물 변화의 반대 방향
    price = [None] * 3 + list(1000 * np.exp(-0.5 * np.log(lst[:-3] / lst[0])))
    ll = overlap.lead_lag(list(lst), price, months)
    assert ll["best"] == 3 and ll["r"][3] < -0.9
    assert ll["n"][0] >= overlap.MIN_PAIRS


def test_weekly_listings():
    d = pd.DataFrame({"date": ["2026-09-28", "2026-09-29", "2026-09-30"], "sale": [10, 12, 14],
                      "jeonse": [1, 1, 1], "wolse": [0, 1, 2]})
    w = overlap.weekly_listings(d)
    assert w["d"] == ["2026-10-04"] and w["s"] == [12.0] and w["r"] == [2.0]
