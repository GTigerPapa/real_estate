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


def load_feed(feed_dir: Path, F: dict) -> dict:
    """최근 keep_days 일의 날짜별 '주요 글'(feed/YYYY-MM-DD.json)을 합친다. 같은 링크는 처음 실린 날 하나로.
    글마다 day(실린 날)를 붙이고, 예전 주제 이름은 tag_map 으로 새 주제에 맞춘다. 화면에서 '오늘/7일'로 거른다."""
    feed_dir = Path(feed_dir)
    files = sorted(p for p in feed_dir.glob("????-??-??.json")) if feed_dir.exists() else []
    if not files and (feed_dir / "latest.json").exists():
        files = [feed_dir / "latest.json"]
    files = files[-int(F.get("keep_days", 7)):]
    tmap = F.get("tag_map") or {}
    out = {"news": [], "cafe": [], "yt": []}
    seen = set()
    latest = {}
    for fp in reversed(files):   # 최신 날짜부터 → 같은 글은 최신 목록 기준으로 남기되 day 는 가장 이른 날로
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except ValueError:
            continue
        latest = latest or d
        day = fp.stem if fp.stem[:4].isdigit() else str(d.get("generated_at", ""))[:10]
        for kind in ("news", "cafe", "yt"):
            for it in d.get(kind, []):
                key = it.get("u") or it.get("t")
                it = {k: v for k, v in it.items() if k != "ts"}
                if it.get("g") in tmap:
                    it["g"] = tmap[it["g"]]
                if kind != "yt" and it.get("x"):
                    it["x"] = it["x"][:110]
                if key in seen:
                    for x in out[kind]:   # 더 이른 날에도 실렸던 글 → 처음 실린 날로
                        if (x.get("u") or x.get("t")) == key:
                            x["day"] = day
                            break
                    continue
                seen.add(key)
                it["day"] = day
                out[kind].append(it)
    if not latest:
        return {}
    out["generated_at"] = latest.get("generated_at")
    out["latest_day"] = files[-1].stem if files[-1].stem[:4].isdigit() else str(latest.get("generated_at", ""))[:10]
    order = {k: i for i, k in enumerate(["정책·대출", "금리", "현장", "경매", "공급", "교통", "단지", "하락 근거"])}
    out["tags"] = sorted({it["g"] for k in ("news", "cafe") for it in out[k] if it.get("g")}, key=lambda t: order.get(t, 99))
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
    feed = load_feed(base / "feed", cfg.get("feed") or {})
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
