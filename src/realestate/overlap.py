"""매물 × 가격 겹쳐 보기: 지역(시군구·법정동)·단지 단위로 매물 수와 실거래가를 같은 시간축에 맞추고,
매물 변화가 몇 달 뒤 가격 변화와 얼마나 같이 움직이는지(선행 상관)를 계산한다.

- 매물: 아실 일별 매물 수(같은 물건 1건). 지역 = asil_region_counts.csv, 단지 = asil_offer_counts.csv
- 가격: 전용 84㎡ 환산가 = ㎡당 가격 × 84 (만원). 평형이 섞인 지역 가격을 한 줄로 보기 위한 기준.
  월별 값은 그 달 포함 직전 3개월 거래를 모은 중앙값 (해제 제외, 직거래 포함 — 지역 전체 표본이라 영향 작음)
- 선행 상관: 매물(월평균 매매 매물)의 3개월 로그 변화 vs k개월 뒤 가격(3개월 중앙값)의 3개월 로그 변화.
  신고 지연이 남은 최근 2개월은 가격에서 뺀다. 3개월 변화끼리 겹쳐 계산하므로 표본이 실제보다 적은 셈 — 참고용.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

LAGS = list(range(0, 7))
REPORT_LAG_MONTHS = 2     # 최근 N개월 가격은 신고 기한(30일)이 남아 상관 계산에서 제외
MIN_PAIRS = 12


def _r(v, nd=0):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return int(round(v)) if nd == 0 else round(float(v), nd)


def weekly_listings(df: pd.DataFrame) -> dict:
    """일별 {date, sale, jeonse, wolse} → 주별(일요일 끝) 7일 평균 {d, s, r(전월세)}."""
    if df.empty:
        return {"d": [], "s": [], "r": []}
    d = df.assign(date=pd.to_datetime(df["date"])).set_index("date").sort_index()
    d["rent"] = d["jeonse"].astype(float) + d["wolse"].astype(float)
    w = d[["sale", "rent"]].astype(float).resample("W-SUN").mean().dropna()
    return {"d": [x.strftime("%Y-%m-%d") for x in w.index], "s": [_r(v, 1) for v in w["sale"]],
            "r": [_r(v, 1) for v in w["rent"]]}


def monthly_listings(df: pd.DataFrame, months: list[str]) -> list:
    if df.empty:
        return [None] * len(months)
    m = df.assign(ym=pd.to_datetime(df["date"]).dt.strftime("%Y-%m")).groupby("ym")["sale"].mean()
    return [_r(m.get(ym), 1) for ym in months]


def price84(trades: pd.DataFrame, months: list[str], window: int = 3) -> dict:
    """trades: deal_ym, deal_amount(만원), exclu_use_ar. 월별 3개월 창 ㎡당 중앙값 × 84 와 표본 수, 그 달 거래 수."""
    t = trades[trades["exclu_use_ar"] > 0].assign(ppm=lambda x: x["deal_amount"] / x["exclu_use_ar"])
    by = {ym: g["ppm"].to_numpy() for ym, g in t.groupby("deal_ym")}
    all_m = sorted(set(months) | set(by))
    idx = {ym: i for i, ym in enumerate(all_m)}
    v, n, vol = [], [], []
    for ym in months:
        i = idx[ym]
        pool = [by[m] for m in all_m[max(0, i - window + 1): i + 1] if m in by]
        arr = np.concatenate(pool) if pool else np.array([])
        v.append(_r(float(np.median(arr)) * 84) if len(arr) else None)
        n.append(int(len(arr)))
        vol.append(int(len(by.get(ym, []))))
    return {"v": v, "n": n, "vol": vol}


def lead_lag(lst: list, price: list, months: list[str], lags=LAGS, min_n: int = 3) -> dict:
    """lst·price 는 months 에 맞춘 월별 값. 매물 3개월 로그 변화 vs k개월 뒤 가격 3개월 로그 변화 상관."""
    L = pd.Series(lst, index=months, dtype=float)
    P = pd.Series(price, index=months, dtype=float)
    if REPORT_LAG_MONTHS:
        P.iloc[-REPORT_LAG_MONTHS:] = np.nan
    dl = np.log(L).diff(3)
    dp = np.log(P).diff(3)
    rs, ns = [], []
    for k in lags:
        m = pd.concat([dl, dp.shift(-k)], axis=1).dropna()
        if len(m) >= MIN_PAIRS and m.iloc[:, 0].std() > 0 and m.iloc[:, 1].std() > 0:
            rs.append(_r(m.corr().iloc[0, 1], 2))
        else:
            rs.append(None)
        ns.append(int(len(m)))
    valid = [(abs(r), k) for r, k in zip(rs, lags) if r is not None]
    best = max(valid)[1] if valid else None
    return {"k": list(lags), "r": rs, "n": ns, "best": best}


def region_trades(conn, sgg_cd: str, umd_nm: str | None = None) -> pd.DataFrame:
    q = ("SELECT substr(deal_date,1,7) AS deal_ym, deal_amount, exclu_use_ar FROM apt_trade "
         "WHERE sgg_cd=? AND is_canceled=0" + (" AND umd_nm=?" if umd_nm else ""))
    return pd.read_sql_query(q, conn, params=(sgg_cd, umd_nm) if umd_nm else (sgg_cd,))


def build(conn, settings: dict, complexes: list[dict], months: list[str],
          region_csv: Path, complex_csv: Path) -> dict:
    regions_out = []
    R = pd.read_csv(region_csv, dtype={"region_id": str, "area": str}) if Path(region_csv).exists() else pd.DataFrame()
    for r in settings.get("regions", []) or []:
        L = R[R["region_id"] == r["id"]] if not R.empty else pd.DataFrame()
        pr = price84(region_trades(conn, str(r["sgg_cd"]), r.get("umd_nm")), months)
        lm = monthly_listings(L, months)
        regions_out.append({"id": r["id"], "name": r["name"], "short": r.get("short") or r["name"],
                            "level": "dong" if r.get("umd_nm") else "sgg", "wk": weekly_listings(L),
                            "lst_m": lm, "p84": pr, "ll": lead_lag(lm, pr["v"], months)})
    C = pd.read_csv(complex_csv, dtype={"complex_id": str}) if Path(complex_csv).exists() else pd.DataFrame()
    cx_out = {}
    for c in complexes:
        L = C[C["complex_id"] == c["id"]] if not C.empty else pd.DataFrame()
        t = pd.read_sql_query("SELECT deal_ym, deal_amount, exclu_use_ar FROM v_trade WHERE complex_id=? AND is_canceled=0",
                              conn, params=(c["id"],))
        pr = price84(t, months)
        lm = monthly_listings(L, months)
        cx_out[c["id"]] = {"lst_m": lm, "p84": pr, "ll": lead_lag(lm, pr["v"], months)}
    return {"regions": regions_out, "complexes": cx_out}
