"""데이터 검증 리포트: 건수표, 이상치, 국토부 공개시스템 대조용 샘플.

    python -m realestate.validate                 # 마크다운 출력
    python -m realestate.validate --out report.md
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from . import config, db, metrics


def _md(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(없음)_\n"
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |")
    return "\n".join(lines) + "\n"


def count_table(trades: pd.DataFrame, rents: pd.DataFrame) -> pd.DataFrame:
    """단지·평형 × 월: '매매(해제)/전세·월세' 문자열."""
    if trades.empty:
        return pd.DataFrame()
    t = trades.assign(col=trades["complex_name"] + " " + trades["size_band"])
    ok = t[t["is_canceled"] == 0].pivot_table(index="deal_ym", columns="col", values="id",
                                              aggfunc="count", fill_value=0)
    cx = t[t["is_canceled"] == 1].pivot_table(index="deal_ym", columns="col", values="id",
                                              aggfunc="count", fill_value=0)
    ok, cx = ok.align(cx, fill_value=0)
    cell = ok.astype(int).astype(str) + cx.map(lambda v: f"({int(v)})" if v else "")
    if not rents.empty:
        r = rents.assign(col=rents["complex_name"] + " " + rents["size_band"])
        rp = r.pivot_table(index="deal_ym", columns="col", values="id", aggfunc="count", fill_value=0)
        cell, rp = cell.align(rp, fill_value=0)
        cell = cell.astype(str) + " / " + rp.astype(int).astype(str)
    cell = cell.sort_index()
    total_ok = ok.sum().astype(int).astype(str) + cx.sum().map(lambda v: f"({int(v)})" if v else "")
    cell.loc["합계"] = total_ok.reindex(cell.columns).fillna("0")
    return cell.reset_index().rename(columns={"deal_ym": "월"})


def samples(trades: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    """단지별 최근 정상 거래 1건 + 최근 해제 거래 1건 (동 정보 있는 건 우선)."""
    t = trades.assign(has_dong=trades["apt_dong"] != "").sort_values(
        ["has_dong", "deal_date"], ascending=[False, False])
    picks = [g.iloc[0] for _, g in t[t["is_canceled"] == 0].groupby("complex_id", sort=False)]
    canceled = t[t["is_canceled"] == 1].sort_values("deal_date", ascending=False)
    if not canceled.empty:
        picks.append(canceled.iloc[0])
    df = pd.DataFrame(picks).head(k)
    return pd.DataFrame({
        "단지": df["complex_name"], "데이터상 단지명": df["apt_nm"], "평형": df["size_band"],
        "전용㎡": df["exclu_use_ar"], "계약일": df["deal_date"].dt.strftime("%Y-%m-%d"),
        "동": df["apt_dong"], "층": df["floor"], "금액(만원)": df["deal_amount"].map("{:,}".format),
        "거래유형": df["dealing_gbn"], "해제": df["is_canceled"].map({0: "", 1: "O"}),
        "해제일": df["cancel_date"],
    })


def outlier_table(trades: pd.DataFrame, pct: float, min_n: int) -> pd.DataFrame:
    o = metrics.outliers(trades, pct, min_n)
    return pd.DataFrame({
        "단지": o["complex_name"], "평형": o["size_band"], "계약일": o["deal_date"].dt.strftime("%Y-%m-%d"),
        "전용㎡": o["exclu_use_ar"], "층": o["floor"], "금액(만원)": o["deal_amount"].map("{:,}".format),
        "기준 중앙값": o["ref_median"].map("{:,.0f}".format), "n": o["ref_n"],
        "편차%": o["dev_pct"].map("{:+.1f}".format), "거래유형": o["dealing_gbn"],
        "해제": o["is_canceled"].map({0: "", 1: "O"}),
    })


def build_report(conn, settings: dict) -> str:
    v = settings.get("validate", {})
    pct, min_n = v.get("outlier_pct", 15), v.get("outlier_min_n", 3)
    trades = metrics.load_trades(conn, include_canceled=True)
    rents = metrics.load_rents(conn, rent_type=None)
    parts = [
        "# 검증 리포트\n",
        f"매매 {len(trades):,}건 (해제 {int(trades['is_canceled'].sum()):,}) · 전월세 {len(rents):,}건\n",
        "## 1. 단지·평형·월별 건수\n",
        "셀: `매매 정상건(해제건)`" + (" / 전월세" if not rents.empty else "") + "\n",
        _md(count_table(trades, rents)),
        f"## 2. 이상치 (±1개월 중앙값 대비 ±{pct}% 이상, 창 표본 {min_n}건 이상)\n",
        _md(outlier_table(trades, pct, min_n)),
        "## 3. 국토부 실거래가 공개시스템 대조용 샘플\n",
        "rt.molit.go.kr → 아파트 매매 → 단지 검색 후 계약일·층·금액 확인\n\n",
        _md(samples(trades)),
    ]
    return "\n".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--db", default=str(config.db_path()))
    a = ap.parse_args(argv)
    settings = config.load_settings()
    conn = db.connect(a.db)
    db.init_db(conn)
    db.sync_config(conn, settings, config.load_complexes())
    text = build_report(conn, settings)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
