"""한국은행 ECOS 지표 → 웹앱 '시장 지표' 데이터.

- 월별 축(ecos.start ~ 최근)에 지표를 맞춘다. 인허가(연중 누계)는 월별로 풀고 12개월 합을 함께 만든다.
  주택관련대출은 잔액의 월 증가분(조원)을 함께 만든다 (돈이 집으로 얼마나 새로 들어가는지).
- 선행 관계: 지표의 3개월 변화 vs k개월 뒤 KB 서울 아파트 매매지수 3개월 변화(로그). 2013년부터라
  지역 실거래(3년)보다 표본이 길다. 3개월 변화끼리 겹치므로 실제 독립 표본은 더 적다 — 참고용.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

TARGET = "kb_seoul_apt"
DRIVERS = [   # (지표 id, 변화 방식, 설명)
    ("mort_rate", "diff", "주담대 금리 3개월 변화(%p)"),
    ("base_rate", "diff", "기준금리 3개월 변화(%p)"),
    ("csi_house", "diff", "주택가격전망CSI 3개월 변화"),
    ("loan_flow", "sum3", "주택관련대출 3개월 순증(조원)"),
    ("unsold_capital", "logdiff", "수도권 미분양 3개월 변화(%)"),
]
LAGS = list(range(0, 13))


def _r(v, nd=2):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), nd)


def load(path: Path, series: list[dict]) -> pd.DataFrame:
    """월 × 지표 표 (인덱스 'YYYY-MM'). 파생: permit_* 월별·12개월 합, loan_flow(조원)."""
    if not Path(path).exists():
        return pd.DataFrame()
    d = pd.read_csv(path, dtype={"month": str, "series_id": str})
    W = d.pivot_table(index="month", columns="series_id", values="value", aggfunc="last").sort_index()
    for s in series:
        if s.get("ytd") and s["id"] in W:
            ytd = W[s["id"]]
            yr = pd.Series(W.index.str[:4], index=W.index)
            prev = ytd.groupby(yr).shift(1)
            W[s["id"] + "_m"] = (ytd - prev.fillna(0)).where(ytd.notna())
            W[s["id"] + "_12m"] = W[s["id"] + "_m"].rolling(12, min_periods=12).sum()
    if "house_loan" in W:
        W["loan_flow"] = W["house_loan"].diff() / 1000.0
    return W


def _chg(x: pd.Series, how: str) -> pd.Series:
    if how == "diff":
        return x.diff(3)
    if how == "logdiff":
        return np.log(x).diff(3) * 100
    if how == "sum3":
        return x.rolling(3).sum()
    raise ValueError(how)


def lead_lags(W: pd.DataFrame) -> list[dict]:
    if W.empty or TARGET not in W:
        return []
    tgt = np.log(W[TARGET]).diff(3)
    out = []
    for sid, how, label in DRIVERS:
        if sid not in W:
            continue
        x = _chg(W[sid], how)
        rs, ns = [], []
        for k in LAGS:
            m = pd.concat([x, tgt.shift(-k)], axis=1).dropna()
            ok = len(m) >= 24 and m.iloc[:, 0].std() > 0
            rs.append(_r(m.corr().iloc[0, 1]) if ok else None)
            ns.append(int(len(m)))
        valid = [(abs(r), k) for r, k in zip(rs, LAGS) if r is not None]
        out.append({"id": sid, "label": label, "k": LAGS, "r": rs, "n": ns,
                    "best": max(valid)[1] if valid else None})
    return out


def build(path: Path, settings: dict) -> dict:
    cfg = settings.get("ecos") or {}
    series = cfg.get("series") or []
    W = load(path, series)
    if W.empty:
        return {}
    months = list(W.index)
    cols = {}
    for c in W.columns:
        cols[c] = [_r(v, 3) for v in W[c].tolist()]
    meta = {s["id"]: {"name": s["name"], "group": s.get("group"), "unit": s.get("unit") or ""} for s in series}
    last = {c: (W[c].last_valid_index() if W[c].notna().any() else None) for c in W.columns}
    return {"months": months, "v": cols, "meta": meta, "last": last, "ll": lead_lags(W)}
