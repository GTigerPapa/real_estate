"""심리 데이터(data/sentiment/) → 웹앱 '시장 > 심리' 데이터.

- 주별 검색량: 묶음별(각 묶음 최댓값=100) + 탐욕/공포 = '상승 기대' ÷ '하락 기대' (같은 요청이라 비교 가능)
- 하루 새 글 수: 검색 결과 총수의 전일 대비 증가 (음수·공백은 비움)
- 선행 관계: 검색 지표(월평균)의 3개월 로그 변화 vs k개월 뒤 KB 서울 아파트 매매지수 3개월 로그 변화 (2016년~)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import macro

LAGS = list(range(0, 13))
LL_SERIES = [("greed", "탐욕/공포 비율"), ("sell", "급매 검색"), ("buy", "매수 행동 검색"), ("down", "하락 기대 검색")]


def _r(v, nd=2):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), nd)


def weekly(path: Path, groups: dict) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame()
    d = pd.read_csv(path, dtype={"week": str, "series": str})
    W = d.pivot_table(index="week", columns="series", values="value", aggfunc="last").sort_index()
    if {"ratio_up", "ratio_down"} <= set(W.columns):
        W["greed"] = W["ratio_up"] / W["ratio_down"].where(W["ratio_down"] > 0)
    return W


def daily_counts(path: Path, ids: list[str]) -> dict:
    if not Path(path).exists():
        return {"d": [], **{i: [] for i in ids}}
    d = pd.read_csv(path, dtype={"date": str, "id": str})
    P = d.pivot_table(index="date", columns="id", values="total", aggfunc="last").sort_index()
    idx = pd.date_range(P.index.min(), P.index.max(), freq="D").strftime("%Y-%m-%d") if len(P) else []
    P = P.reindex(idx)
    out = {"d": list(idx)}
    for i in ids:
        if i in P:
            diff = P[i].diff()
            out[i] = [None if (pd.isna(v) or v < 0) else int(v) for v in diff]
        else:
            out[i] = [None] * len(idx)
    return out


def lead_lags(W: pd.DataFrame, macro_W: pd.DataFrame) -> list[dict]:
    if W.empty or macro_W.empty or macro.TARGET not in macro_W:
        return []
    Wm = W.copy()
    Wm.index = pd.to_datetime(Wm.index).strftime("%Y-%m")
    M = Wm.groupby(level=0).mean()
    tgt = np.log(macro_W[macro.TARGET]).diff(3)
    out = []
    for sid, label in LL_SERIES:
        if sid not in M:
            continue
        x = np.log(M[sid].where(M[sid] > 0)).diff(3).reindex(macro_W.index)
        rs, ns = [], []
        for k in LAGS:
            m = pd.concat([x, tgt.shift(-k)], axis=1).dropna()
            ok = len(m) >= 24 and m.iloc[:, 0].std() > 0
            rs.append(_r(m.corr().iloc[0, 1]) if ok else None)
            ns.append(int(len(m)))
        valid = [(abs(r), k) for r, k in zip(rs, LAGS) if r is not None]
        out.append({"id": sid, "label": label, "k": LAGS, "r": rs, "n": ns, "best": max(valid)[1] if valid else None})
    return out


def build(base: Path, settings: dict, ecos_csv: Path) -> dict:
    cfg = settings.get("sentiment") or {}
    groups = cfg.get("groups") or {}
    W = weekly(base / "datalab_weekly.csv", groups)
    counts = [c["id"] for c in cfg.get("counts") or []]
    daily = daily_counts(base / "search_totals.csv", counts)
    yt = pd.read_csv(base / "youtube_daily.csv", dtype={"date": str}) if (base / "youtube_daily.csv").exists() else pd.DataFrame()
    ytw = pd.read_csv(base / "youtube_weekly.csv", dtype={"week": str}) if (base / "youtube_weekly.csv").exists() else pd.DataFrame()
    if not yt.empty:
        yt = yt.sort_values("date")
    if not ytw.empty:
        ytw = ytw.sort_values("week")
    feed = {}
    fp = base / "feed" / "latest.json"
    if fp.exists():
        feed = json.loads(fp.read_text(encoding="utf-8"))
        for it in feed.get("news", []):
            it.pop("ts", None)
    if W.empty and not feed and not daily["d"]:
        return {}
    wk = {"d": list(W.index)} if not W.empty else {"d": []}
    for c in list(groups) + ["greed"]:
        if c in W:
            wk[c] = [_r(v, 3) for v in W[c].tolist()]
    MW = macro.load(ecos_csv, (settings.get("ecos") or {}).get("series") or [])
    return {
        "groups": {k: {"name": g["name"], "kw": g["keywords"]} for k, g in groups.items()},
        "wk": wk,
        "daily": daily,
        "counts": {c["id"]: {"source": c["source"], "query": c["query"]} for c in cfg.get("counts") or []},
        "yt": {"d": yt["date"].tolist(), "n": [int(x) for x in yt["total_results"]]} if not yt.empty else {"d": [], "n": []},
        # 주 단위 백필(월요일 시작, 7일 합계) — 하루 단위 구간 이전 1년치
        "ytw": {"d": ytw["week"].tolist(), "n": [int(x) for x in ytw["total_results"]]} if not ytw.empty else {"d": [], "n": []},
        "feed": feed,
        "ll": lead_lags(W, MW),
    }
