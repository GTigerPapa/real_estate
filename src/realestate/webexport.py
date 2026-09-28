"""모바일 웹앱(web/)이 읽는 데이터 파일(web/data/app.json) 생성.

대시보드와 같은 기준을 쓴다:
- 매매 중앙값: 해제·직거래 제외, 3개월 이동(직전 3개월 개별 거래 풀링)
- 전세 중앙값: 갱신 계약 제외(유형 미상 포함), 3개월 이동
- 전세가율: 같은 단지·평형 3개월 창 전세 중앙값 ÷ 매매 중앙값
- 네이버 매물: listing_metric 스냅샷 (settings.yaml listing_metrics 규칙, 단지 전체 기준) — 호가만 앱에서 사용
- 아실 매물: data/listings/asil/asil_offer_counts.csv 의 일별 매매·전세·월세 매물 수 (단지 전체, 중복 매물 1건)
금액 단위는 만원(실거래)·원(네이버 호가)을 앱에서 억으로 바꾸지 않도록 여기서 모두 '만원'으로 맞춘다.
"""
from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from . import config, listings, metrics

FORMAT = 1
MONTHS_SHOWN = 36


def _num(v, nd: int = 0):
    """NaN/None → None, 나머지는 반올림한 숫자 (JSON 직렬화용)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return int(round(f)) if nd == 0 else round(f, nd)


def _series(df: pd.DataFrame, months: list[str], value: str, n: str = "n", nd: int = 0) -> dict:
    d = df.set_index("deal_ym")
    return {"v": [_num(d[value].get(m), nd) if m in d.index else None for m in months],
            "n": [int(d[n].get(m, 0)) if m in d.index else 0 for m in months]}


ASIL_CSV = config.DATA_DIR / "listings" / "asil" / "asil_offer_counts.csv"
OFFERS_CSV = config.DATA_DIR / "listings" / "asil" / "asil_offers.csv"
RECENT_TRADES = 300   # 홈 '최근 실거래' 표에 싣는 건수 (전체 단지·전체 면적)
OFFERS_MAX = 400      # 홈 '매물' 표에 싣는 물건 수


def load_offers(path=OFFERS_CSV) -> dict:
    """아실 매물 추적 파일 → 현재 게시 중인 물건 목록.

    같은 물건(단지·유형·동·층·전용면적·가격)을 여러 중개사가 올린 건 1줄로 묶는다.
    reg: 가장 이른 게시일(=등록일에 가장 가까운 값), upd: 가장 최근 게시일(광고 갱신),
    seen: 이 추적에서 처음 본 날, chg/prev: 가격이 바뀐 날과 이전 가격.
    """
    from pathlib import Path
    p = Path(path)
    empty = {"items": [], "since": None, "through": None}
    if not p.exists():
        return empty
    df = pd.read_csv(p, dtype=str).fillna("")
    if df.empty:
        return empty
    since, through = df["first_seen"].min(), df["last_seen"].max()
    act = df[df["active"] == "1"].copy()
    items = []
    for key, g in act.groupby(["complex_id", "deal", "dong", "floor", "excl_area", "price", "rent"], sort=False):
        cid, deal, dong, floor, ar, price, rent = key
        posted = sorted(x for x in g["posted"] if x)
        chg = g[g["price_changed"] != ""].sort_values("price_changed")
        desc = next((x for x in g["desc"] if x), "")
        items.append({
            "c": cid, "t": deal, "p": int(price or 0), "r": int(rent) if rent else None,
            "dong": dong, "f": floor, "ar": _num(ar, 2) if ar else None,
            "reg": posted[0] if posted else g["first_seen"].min(), "upd": posted[-1] if posted else None,
            "seen": g["first_seen"].min(), "n": int(len(g)),
            "chg": chg["price_changed"].iloc[-1] if not chg.empty else None,
            "prev": int(chg["prev_price"].iloc[-1]) if not chg.empty and chg["prev_price"].iloc[-1] else None,
            "desc": desc[:60],
        })
    items.sort(key=lambda x: (x["reg"] or "", x["upd"] or "", x["seen"] or ""), reverse=True)
    return {"items": items[:OFFERS_MAX], "since": since, "through": through}


def recent_trades(conn, complexes: list[dict], limit: int = RECENT_TRADES) -> list:
    """관심 단지 전체(평형 구간 밖 면적 포함) 매매 실거래, 계약일 최신순. pub: 이 저장소가 처음 받은 날(≈공개일)."""
    ids = [c["id"] for c in complexes]
    if not ids:
        return []
    q = ("SELECT complex_id, deal_date, deal_amount, floor, apt_dong, exclu_use_ar, dealing_gbn, is_canceled, "
         "substr(first_seen_at, 1, 10) AS pub FROM v_trade WHERE complex_id IN (%s) "
         "ORDER BY deal_date DESC, first_seen_at DESC LIMIT ?" % ",".join("?" * len(ids)))
    rows = conn.execute(q, [*ids, limit]).fetchall()
    return [{"c": r[0], "d": r[1], "p": int(r[2]), "f": int(r[3]), "dong": (r[4] or "").removesuffix("동"),
             "ar": round(float(r[5]), 2),
             "t": "direct" if r[6] == "직거래" else "broker", "x": int(r[7]), "pub": r[8]} for r in rows]


def load_asil(path=ASIL_CSV) -> dict:
    """{complex_id: {"d": [날짜...], "s": [매매], "j": [전세], "w": [월세]}} (날짜 오름차순, 열 형식으로 용량 절약)."""
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return {}
    df = pd.read_csv(p, dtype={"date": str, "complex_id": str})
    out = {}
    for cid, g in df.sort_values("date").groupby("complex_id"):
        out[cid] = {"d": g["date"].tolist(), "s": [int(x) for x in g["sale"]],
                    "j": [int(x) for x in g["jeonse"]], "w": [int(x) for x in g["wolse"]]}
    return out


def build_payload(conn, settings: dict, complexes: list[dict], now: datetime | None = None,
                  asil_csv=ASIL_CSV, offers_csv=OFFERS_CSV) -> dict:
    now = now or config.now_kst()
    asil = load_asil(asil_csv)
    offers = load_offers(offers_csv)
    cap = int(settings.get("buy_cap_manwon", 140000))
    trades = metrics.load_trades(conn, include_canceled=True)
    rents = metrics.load_rents(conn, rent_type=None)

    last_ym = max(trades["deal_ym"].max() if not trades.empty else now.strftime("%Y-%m"),
                  rents["deal_ym"].max() if not rents.empty else "0000-00")
    months = metrics.month_range((pd.Period(last_ym) - (MONTHS_SHOWN - 1)).strftime("%Y-%m"), last_ym)
    lead = metrics.month_range((pd.Period(months[0]) - 2).strftime("%Y-%m"), months[-1])  # 3개월 창 선행분

    snap = listings.snapshot(conn, settings)
    out_complexes = []
    for idx, c in enumerate(complexes):
        cid = c["id"]
        bands_out = {}
        for band in [str(b) for b in c.get("bands", [])]:
            T = trades[(trades["complex_id"] == cid) & (trades["size_band"] == band)]
            R = rents[(rents["complex_id"] == cid) & (rents["size_band"] == band)]
            base = T[(T["is_canceled"] == 0) & (T["dealing_gbn"] != "직거래")]
            jeonse = R[(R["rent_type"] == "전세") & (R["contract_type"] != "갱신")]

            def trim(df):
                return df[df["deal_ym"].isin(months)]

            roll_t = trim(metrics.window_median(base, "deal_amount", 3, months=lead))
            roll_j = trim(metrics.window_median(jeonse, "deposit", 3, months=lead))
            ratio = trim(metrics.jeonse_ratio(base, jeonse, window=3, months=lead))
            rc = trim(metrics.rent_composition(R, lead)) if not R.empty else pd.DataFrame()

            Tm = T[T["deal_ym"].isin(months)]
            vol = {k: [int(((Tm["deal_ym"] == m) & mask).sum()) for m in months] for k, mask in {
                "broker": (Tm["is_canceled"] == 0) & (Tm["dealing_gbn"] != "직거래"),
                "direct": (Tm["is_canceled"] == 0) & (Tm["dealing_gbn"] == "직거래"),
                "canceled": Tm["is_canceled"] == 1,
            }.items()}

            deals = [{
                "d": r.deal_date.strftime("%Y-%m-%d"), "p": int(r.deal_amount), "f": int(r.floor),
                "dong": r.apt_dong or "", "ar": round(float(r.exclu_use_ar), 2),
                "t": "direct" if r.dealing_gbn == "직거래" else "broker", "x": int(r.is_canceled),
            } for r in Tm.sort_values("deal_date").itertuples()]

            # 요약: 거래가 있는 가장 최근 3개월 창
            valid = roll_t[roll_t["n"] > 0]
            summary = {"ym": None, "median": None, "n": 0, "yoy_pct": None, "vs_cap": None,
                       "jeonse": None, "jeonse_n": 0, "ratio": None, "last_deal": None}
            if not valid.empty:
                ref = valid.iloc[-1]
                ym, med = ref["deal_ym"], float(ref["median"])
                ago_ym = (pd.Period(ym) - 12).strftime("%Y-%m")
                ago = metrics.window_median(base, "deal_amount", 3, months=metrics.month_range(
                    (pd.Period(ago_ym) - 2).strftime("%Y-%m"), ago_ym)).tail(1)
                ago_med = float(ago["median"].iloc[0]) if not ago.empty and ago["n"].iloc[0] else None
                summary.update(ym=ym, median=_num(med), n=int(ref["n"]),
                               yoy_pct=_num((med / ago_med - 1) * 100, 1) if ago_med else None,
                               vs_cap=_num(med - cap))
            jv = roll_j[roll_j["n"] > 0]
            if not jv.empty:
                summary.update(jeonse=_num(jv.iloc[-1]["median"]), jeonse_n=int(jv.iloc[-1]["n"]))
            rv = ratio.dropna(subset=["ratio"])
            if not rv.empty:
                summary["ratio"] = _num(rv.iloc[-1]["ratio"] * 100, 1)
            ok = T[T["is_canceled"] == 0].sort_values("deal_date")
            if not ok.empty:
                r = ok.iloc[-1]
                summary["last_deal"] = {"d": r["deal_date"].strftime("%Y-%m-%d"), "p": int(r["deal_amount"]),
                                        "f": int(r["floor"])}

            bands_out[band] = {
                "summary": summary,
                "trade_3m": _series(roll_t, months, "median"),
                "jeonse_3m": _series(roll_j, months, "median"),
                "ratio_3m": {"v": [_num(ratio.set_index("deal_ym")["ratio"].get(m) * 100, 1)
                                   if m in set(ratio["deal_ym"]) and pd.notna(ratio.set_index("deal_ym")["ratio"].get(m))
                                   else None for m in months]},
                "volume": vol,
                "renew_ratio_3m": ({"v": [_num(x * 100, 0) if (pd.notna(x) and n >= 5) else None
                                          for x, n in zip(rc.set_index("deal_ym")["renew_ratio"].reindex(months),
                                                          rc.set_index("deal_ym")["renew_n"].reindex(months).fillna(0))]}
                                   if not rc.empty else {"v": [None] * len(months)}),
                "deals": deals,
            }

        # 네이버 매물 (단지 전체 기준). 호가는 원 → 만원
        L = snap[snap["complex_id"] == cid] if not snap.empty else snap
        lst = []
        if not L.empty:
            L = L[L["pyeong_type"].isna() | (L["pyeong_type"] == 0)]
            piv = L.pivot_table(index="snap_date", columns="metric", values="value", aggfunc="last").sort_index()
            for d, row in piv.iterrows():
                def g(k, won=False):
                    v = row.get(k)
                    return None if v is None or pd.isna(v) else int(round(v / 10000)) if won else int(v)
                lst.append({"d": d, "sale": g("sale_count"), "lease": g("lease_count"), "wolse": g("wolse_count"),
                            "sale_min": g("sale_min_ask", True), "sale_max": g("sale_max_ask", True),
                            "lease_min": g("lease_min_ask", True)})

        out_complexes.append({"id": cid, "name": c["name"], "short": c.get("short") or c["name"], "slot": idx, "bands": [str(b) for b in c.get("bands", [])],
                              "area": f"{c['umd_nm']}", "b": bands_out, "listings": lst,
                              "asil": asil.get(cid, {"d": [], "s": [], "j": [], "w": []})})

    return {
        "format": FORMAT,
        "generated_at": now.isoformat(timespec="minutes"),
        "data_through": trades["deal_date"].max().strftime("%Y-%m-%d") if not trades.empty else None,
        "listing_through": max((x["d"] for c in out_complexes for x in c["listings"]), default=None),
        "asil_through": max((c["asil"]["d"][-1] for c in out_complexes if c["asil"]["d"]), default=None),
        "cap": cap,
        "months": months,
        "bands": [str(b["band"]) for b in settings.get("size_bands", [])],
        "complexes": out_complexes,
        "trades_recent": recent_trades(conn, complexes),
        # 최초 백필 날짜: 이 날 받은 거래는 '새로 공개'로 표시하지 않는다
        "trades_since": (conn.execute("SELECT substr(min(first_seen_at), 1, 10) FROM apt_trade").fetchone() or [None])[0],
        "offers": offers["items"],
        "offers_since": offers["since"],
        "offers_through": offers["through"],
    }
