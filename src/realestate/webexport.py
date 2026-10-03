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
import re
from datetime import datetime

import pandas as pd

from . import config, listings, metrics, overlap

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
REGION_CSV = config.DATA_DIR / "listings" / "asil" / "asil_region_counts.csv"
OFFERS_CSV = config.DATA_DIR / "listings" / "asil" / "asil_offers.csv"
RECENT_TRADES = 600   # 홈 '최근 실거래' 표에 싣는 건수 (전체 단지·전체 면적, 앱에서 평형으로 거름)
OFFERS_MAX = 400      # 홈 '매물' 표에 싣는 물건 수


def band_of(ar, size_bands) -> str | None:
    """전용면적 → 평형 구간 이름 (settings.yaml size_bands, [min, max)). 구간 밖이면 None."""
    try:
        a = float(ar)
    except (TypeError, ValueError):
        return None
    for b in size_bands or []:
        if float(b["min"]) <= a < float(b["max"]):
            return str(b["band"])
    return None


# 매물 설명(중개사가 쓴 문구)으로 세안고 / 입주 가능을 가린다. 아실 원본에 임대 여부·입주가능일 같은 칸은 없다
# (2026-10-04 원본 항목 확인). 언급이 없는 매물이 절반 넘어서 '세안고 수'는 하한값으로 봐야 한다.
_TENANT = re.compile(r"세\s*(?:안고|끼고|낀)|세안\b|세안\s*매매|전세\s*(?:안고|끼고|승계|낀)|세입자\s*(?:있|승계|거주)|임대\s*(?:중|승계)"
                     r"|월세\s*(?:안고|끼고)|임차인|갭\s*투자")
_MOVEIN = re.compile(r"즉시\s*입주|즉입|공실|바로\s*입주|입주\s*가능|입주\s*매매|정상\s*입주|주인\s*거주|실입주|입주\s*협의")


def tenant_kind(*descs: str) -> str | None:
    """'t' = 세안고, 'm' = 입주 가능(실입주), None = 언급 없음. 같은 물건의 설명 중 하나라도 세안고면 세안고."""
    text = " ".join(d for d in descs if d)
    if _TENANT.search(text):
        return "t"
    if _MOVEIN.search(text):
        return "m"
    return None


def offer_band_counts(path=OFFERS_CSV, size_bands=None) -> dict:
    """아실 매물 추적 파일 → 단지·평형별 일별 매물 수 {cid: {band: {"d","s","j","w"}}}.

    아실 일별 매물 수(asil_offer_counts.csv)는 단지 전체 값만 준다(면적 조건 무시). 그래서 평형별 추이는
    매물 목록 추적(first_seen~last_seen)으로 직접 센다. 같은 물건(유형·동·층·전용·가격)은 1개. 추적 시작일부터 쌓인다.
    """
    from datetime import date, timedelta
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return {}
    df = pd.read_csv(p, dtype=str).fillna("")
    if df.empty:
        return {}
    df["band"] = [band_of(a, size_bands) for a in df["excl_area"]]
    df = df[df["band"].notna() & (df["first_seen"] != "") & (df["last_seen"] != "")]
    d0, d1 = date.fromisoformat(df["first_seen"].min()), date.fromisoformat(df["last_seen"].max())
    days = [(d0 + timedelta(n)).isoformat() for n in range((d1 - d0).days + 1)]
    key = df["deal"] + "|" + df["dong"] + "|" + df["floor"] + "|" + df["excl_area"] + "|" + df["price"] + "|" + df["rent"]
    df = df.assign(key=key)
    # 같은 물건(key)의 설명을 모두 모아 세안고 여부를 정한다
    kinds = {k: tenant_kind(*g["desc"]) for k, g in df.groupby("key")}
    df["ten"] = df["key"].map(kinds)
    out = {}
    for (cid, band), g in df.groupby(["complex_id", "band"]):
        ser = {"d": days, "s": [], "j": [], "w": [], "st": [], "sm": []}
        for day in days:
            on = g[(g["first_seen"] <= day) & (g["last_seen"] >= day)]
            for deal, k in (("sale", "s"), ("jeonse", "j"), ("wolse", "w")):
                ser[k].append(int(on.loc[on["deal"] == deal, "key"].nunique()))
            sale = on[on["deal"] == "sale"]
            ser["st"].append(int(sale.loc[sale["ten"] == "t", "key"].nunique()))   # 매매 중 세안고
            ser["sm"].append(int(sale.loc[sale["ten"] == "m", "key"].nunique()))   # 매매 중 입주 가능
        out.setdefault(cid, {})[str(band)] = ser
    return out


def load_offers(path=OFFERS_CSV, size_bands=None) -> dict:
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
            "c": cid, "t": deal, "p": int(price or 0), "r": int(rent) if rent else None, "b": band_of(ar, size_bands),
            "dong": dong, "f": floor, "ar": _num(ar, 2) if ar else None,
            "reg": posted[0] if posted else g["first_seen"].min(), "upd": posted[-1] if posted else None,
            "seen": g["first_seen"].min(), "n": int(len(g)),
            "chg": chg["price_changed"].iloc[-1] if not chg.empty else None,
            "prev": int(chg["prev_price"].iloc[-1]) if not chg.empty and chg["prev_price"].iloc[-1] else None,
            "desc": desc[:60],
            "ten": tenant_kind(*g["desc"]),   # t 세안고 · m 입주 가능 · None 언급 없음 (설명 문구 기준)
        })
    items.sort(key=lambda x: (x["reg"] or "", x["upd"] or "", x["seen"] or ""), reverse=True)
    return {"items": items[:OFFERS_MAX], "since": since, "through": through}


def recent_trades(conn, complexes: list[dict], limit: int = RECENT_TRADES) -> list:
    """관심 단지 전체(평형 구간 밖 면적 포함) 매매 실거래, 계약일 최신순. pub: 이 저장소가 처음 받은 날(≈공개일)."""
    ids = [c["id"] for c in complexes]
    if not ids:
        return []
    q = ("SELECT complex_id, deal_date, deal_amount, floor, apt_dong, exclu_use_ar, dealing_gbn, is_canceled, "
         "substr(first_seen_at, 1, 10) AS pub, size_band FROM v_trade WHERE complex_id IN (%s) "
         "ORDER BY deal_date DESC, first_seen_at DESC LIMIT ?" % ",".join("?" * len(ids)))
    rows = conn.execute(q, [*ids, limit]).fetchall()
    return [{"c": r[0], "d": r[1], "p": int(r[2]), "f": int(r[3]), "dong": (r[4] or "").removesuffix("동"),
             "ar": round(float(r[5]), 2),
             "t": "direct" if r[6] == "직거래" else "broker", "x": int(r[7]), "pub": r[8], "b": r[9]} for r in rows]


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
                  asil_csv=ASIL_CSV, offers_csv=OFFERS_CSV, region_csv=REGION_CSV) -> dict:
    now = now or config.now_kst()
    asil = load_asil(asil_csv)
    offers = load_offers(offers_csv, settings.get("size_bands"))
    band_counts = offer_band_counts(offers_csv, settings.get("size_bands"))
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
                              "asil": asil.get(cid, {"d": [], "s": [], "j": [], "w": []}),
                              # 평형별 일별 매물 수 (아실 매물 목록 추적에서 계산, 추적 시작일부터)
                              "asil_b": {b: band_counts.get(cid, {}).get(b, {"d": [], "s": [], "j": [], "w": []})
                                         for b in [str(x) for x in c.get("bands", [])]}})

    return {
        "format": FORMAT,
        "generated_at": now.isoformat(timespec="minutes"),
        "data_through": trades["deal_date"].max().strftime("%Y-%m-%d") if not trades.empty else None,
        # 실거래를 마지막으로 받은 시각 (DB fetch_log). 더 새 실거래를 담은 app.json 을 덮어쓰지 않는 데 쓴다
        "trades_fetched_at": (conn.execute("SELECT max(fetched_at) FROM fetch_log WHERE status='ok'").fetchone() or [None])[0],
        "listing_through": max((x["d"] for c in out_complexes for x in c["listings"]), default=None),
        "asil_through": max((c["asil"]["d"][-1] for c in out_complexes if c["asil"]["d"]), default=None),
        "cap": cap,
        "months": months,
        "bands": [str(b["band"]) for b in settings.get("size_bands", [])],
        "complexes": out_complexes,
        "trades_recent": recent_trades(conn, complexes),
        # 최초 백필 날짜: 이 날 받은 거래는 '새로 공개'로 표시하지 않는다
        "trades_since": (conn.execute("SELECT substr(min(first_seen_at), 1, 10) FROM apt_trade").fetchone() or [None])[0],
        # 매물 × 가격 (지역·단지): 같은 months 축의 월별 매물·84㎡ 환산가, 주별 매물, 선행 상관
        "overlap": overlap.build(conn, settings, complexes, months, region_csv, asil_csv),
        "offers": offers["items"],
        "offers_since": offers["since"],
        "offers_through": offers["through"],
    }


# 실거래에서 나오는 항목. 공공데이터포털은 해외(GitHub Actions)에서 막혀 실거래는 국내 Mac이 받는다.
# Mac은 매일 app.json 을 새로 만들지만 DB는 매월만 커밋하므로, Actions 가 저장소의 (오래된) DB로 다시 내보내면
# 실거래가 뒤로 돌아간다. 그래서 기존 app.json 의 실거래가 더 새 것이면 그 부분은 그대로 둔다.
TRADE_TOP = ("data_through", "trades_fetched_at", "months", "trades_recent", "trades_since", "overlap")


def keep_newer_trades(new: dict, old: dict | None) -> bool:
    """old 의 실거래 수집 시각이 더 늦으면 new 의 실거래 부분을 old 것으로 바꾼다. 바꿨으면 True.

    단지별 평형 데이터(b)는 old 에 있는 단지·평형만 옮긴다 (새로 추가한 단지·평형은 DB 값 유지 — 그 경우 months 가
    어긋날 수 있어, 같은 months 일 때만 섞는다)."""
    if not old or not old.get("trades_fetched_at"):
        return False
    if (new.get("trades_fetched_at") or "") >= old["trades_fetched_at"]:
        return False
    same_months = old.get("months") == new.get("months")
    for k in TRADE_TOP:
        if k in old:
            new[k] = old[k]
    olds = {c["id"]: c for c in old.get("complexes", [])}
    for c in new.get("complexes", []):
        o = olds.get(c["id"])
        if not o:
            continue
        for band in c["bands"]:
            if band in o.get("b", {}):
                c["b"][band] = o["b"][band]
            elif not same_months:   # 새 평형인데 기간 축이 달라졌으면 비워 둔다 (다음 Mac 갱신 때 채워짐)
                c["b"][band] = _empty_band(len(new["months"]))
    return True


def _empty_band(n: int) -> dict:
    none = {"v": [None] * n, "n": [0] * n}
    return {"summary": {"ym": None, "median": None, "n": 0, "yoy_pct": None, "vs_cap": None, "jeonse": None,
                        "jeonse_n": 0, "ratio": None, "last_deal": None},
            "trade_3m": none, "jeonse_3m": none, "ratio_3m": {"v": [None] * n},
            "volume": {"broker": [0] * n, "direct": [0] * n, "canceled": [0] * n},
            "renew_ratio_3m": {"v": [None] * n}, "deals": []}
