"""지표 계산: 월별·이동 중앙값, 전세가율. 평균 대신 중앙값, 항상 표본 수(n) 동반."""
from __future__ import annotations

import sqlite3

import pandas as pd

GROUP = ["complex_id", "complex_name", "size_band"]


def _in_target_bands(df: pd.DataFrame, conn: sqlite3.Connection) -> pd.DataFrame:
    """complex.target_bands에 포함된 평형만 (예: 센트럴타운 59형 제외)."""
    tb = pd.read_sql_query("SELECT complex_id, target_bands FROM complex", conn)
    allowed = {(r.complex_id, b) for r in tb.itertuples() for b in (r.target_bands or "").split(",") if b}
    keep = pd.Series([(c, b) in allowed for c, b in zip(df["complex_id"], df["size_band"])],
                     index=df.index, dtype=bool)
    return df[keep]


def load_trades(conn, include_canceled: bool = False, target_only: bool = True) -> pd.DataFrame:
    sql = "SELECT * FROM v_trade WHERE size_band IS NOT NULL"
    if not include_canceled:
        sql += " AND is_canceled = 0"
    df = pd.read_sql_query(sql, conn, parse_dates=["deal_date"])
    return _in_target_bands(df, conn) if target_only else df


def load_rents(conn, rent_type: str | None = "전세", target_only: bool = True) -> pd.DataFrame:
    sql = "SELECT * FROM v_rent WHERE size_band IS NOT NULL"
    params: tuple = ()
    if rent_type:
        sql += " AND rent_type = ?"
        params = (rent_type,)
    df = pd.read_sql_query(sql, conn, params=params, parse_dates=["deal_date"])
    return _in_target_bands(df, conn) if target_only else df


def month_range(start: str, end: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def window_median(df: pd.DataFrame, value: str, window: int = 1, center: bool = False,
                  months: list[str] | None = None) -> pd.DataFrame:
    """단지·평형·월별 중앙값과 n.

    window>1이면 개별 거래를 창(window개월)으로 모아 중앙값을 낸다 (월 중앙값들의 중앙값이 아님).
    center=False: [m-window+1, m] (후행), center=True: [m-k, m+k].
    거래가 없는 월은 median=NaN, n=0 으로 포함.
    """
    cols = GROUP + ["deal_ym", "median", "n"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    months = months or month_range(df["deal_ym"].min(), df["deal_ym"].max())
    idx = {m: i for i, m in enumerate(months)}
    lo_off, hi_off = ((window // 2, window // 2) if center else (window - 1, 0))
    out = []
    for key, g in df.groupby(GROUP):
        pos = g["deal_ym"].map(idx)
        vals = g[value].to_numpy()
        for m, i in idx.items():
            sel = vals[((pos >= i - lo_off) & (pos <= i + hi_off)).to_numpy()]
            out.append((*key, m, float(pd.Series(sel).median()) if len(sel) else float("nan"), len(sel)))
    return pd.DataFrame(out, columns=cols)


def jeonse_ratio(trades: pd.DataFrame, jeonse: pd.DataFrame, window: int = 1,
                 months: list[str] | None = None) -> pd.DataFrame:
    """전세가율 = 같은 단지·평형·월(창) 전세 보증금 중앙값 ÷ 매매가 중앙값."""
    if trades.empty or jeonse.empty:
        return pd.DataFrame(columns=GROUP + ["deal_ym", "trade_median", "trade_n",
                                             "jeonse_median", "jeonse_n", "ratio"])
    if months is None:
        lo = min(trades["deal_ym"].min(), jeonse["deal_ym"].min())
        hi = max(trades["deal_ym"].max(), jeonse["deal_ym"].max())
        months = month_range(lo, hi)
    t = window_median(trades, "deal_amount", window, months=months).rename(
        columns={"median": "trade_median", "n": "trade_n"})
    j = window_median(jeonse, "deposit", window, months=months).rename(
        columns={"median": "jeonse_median", "n": "jeonse_n"})
    m = t.merge(j, on=GROUP + ["deal_ym"], how="outer")
    m["ratio"] = m["jeonse_median"] / m["trade_median"]
    return m


def outliers(trades: pd.DataFrame, pct: float = 15, min_n: int = 3) -> pd.DataFrame:
    """같은 단지·평형 ±1개월(3개월 창) 중앙값 대비 |편차| ≥ pct% 인 거래 (해제 제외 기준)."""
    base = trades[trades["is_canceled"] == 0]
    ref = window_median(base, "deal_amount", window=3, center=True)
    ref = ref.rename(columns={"median": "ref_median", "n": "ref_n"})
    df = trades.merge(ref, on=GROUP + ["deal_ym"], how="left")
    df["dev_pct"] = (df["deal_amount"] / df["ref_median"] - 1) * 100
    hit = df[(df["ref_n"] >= min_n) & (df["dev_pct"].abs() >= pct)]
    return hit.sort_values("dev_pct")
