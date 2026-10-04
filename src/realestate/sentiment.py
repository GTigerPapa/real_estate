"""심리 지표 수집: 네이버 데이터랩 검색량(주별), 네이버 카페·뉴스 글 수(일별), 주요 글(뉴스·카페·유튜브).

    python scripts/sentiment_collect.py      # GitHub Actions 가 매일 실행

- 네이버: NAVER API HUB (네이버 클라우드 플랫폼, 2026-07-31 개발자센터에서 이관). 키 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET.
- 유튜브: YouTube Data API v3. 키 YOUTUBE_API_KEY. 하루 약 101단위 사용 (무료 한도 10,000).
- 저장 (data/sentiment/):
    datalab_weekly.csv   week, series, value      매일 2016년부터 다시 받아 덮어씀 (데이터랩 값은 요청마다 다시 정규화됨)
    search_totals.csv    date, id, total           매일 1줄씩 (하루 새 글 수 = 오늘 − 어제)
    youtube_daily.csv    date, total_results       전날 올라온 부동산 영상 수 (유튜브 추정치)
    feed/latest.json     주요 글 (feed/YYYY-MM-DD.json 으로 30일 보관)
- 키 값은 URL·로그에 남기지 않는다. 원문 본문은 저장하지 않고 제목·링크·각 서비스가 주는 미리보기 문구만.
"""
from __future__ import annotations

import csv
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HUB = "https://naverapihub.apigw.ntruss.com"
YT = "https://www.googleapis.com/youtube/v3"
KST = timezone(timedelta(hours=9))


class ApiError(RuntimeError):
    pass


# ───── HTTP ─────

def _call(req, timeout: float = 30) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        raise ApiError(f"HTTP {e.code} {_mask(body)}") from None
    except Exception as e:  # noqa: BLE001 — 메시지에 URL(키 포함)이 들어갈 수 있어 타입명만
        raise ApiError(type(e).__name__) from None


def _mask(text: str) -> str:
    for k in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
        v = os.environ.get(k)
        if v:
            text = text.replace(v, "***")
    return text


class Naver:
    def __init__(self, cid: str | None = None, secret: str | None = None, call=_call):
        self.cid = (cid or os.environ.get("NAVER_CLIENT_ID") or "").strip()
        self.secret = (secret or os.environ.get("NAVER_CLIENT_SECRET") or "").strip()
        if not (self.cid and self.secret):
            raise ApiError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 없음")
        self.call = call

    def _h(self, json_body: bool = False) -> dict:
        h = {"X-NCP-APIGW-API-KEY-ID": self.cid, "X-NCP-APIGW-API-KEY": self.secret}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def datalab(self, groups: list[dict], start: str, end: str, unit: str = "week") -> dict:
        """groups: [{"groupName", "keywords"}] (최대 5). → {groupName: [(period, ratio)]}"""
        body = {"startDate": start, "endDate": end, "timeUnit": unit,
                "keywordGroups": [{"groupName": g["groupName"], "keywords": g["keywords"][:20]} for g in groups]}
        d = self.call(urllib.request.Request(HUB + "/search-trend/v1/search", data=json.dumps(body).encode(),
                                             headers=self._h(True), method="POST"))
        return {r["title"]: [(x["period"], float(x["ratio"])) for x in r.get("data", [])] for r in d.get("results", [])}

    def search(self, source: str, query: str, display: int = 10, sort: str = "date") -> dict:
        q = urllib.parse.urlencode({"query": query, "display": display, "sort": sort})
        return self.call(urllib.request.Request(f"{HUB}/search/v1/{source}?{q}", headers=self._h()))


class YouTube:
    def __init__(self, key: str | None = None, call=_call):
        self.key = (key or os.environ.get("YOUTUBE_API_KEY") or "").strip()
        if not self.key:
            raise ApiError("YOUTUBE_API_KEY 없음")
        self.call = call

    def search(self, q: str, after: datetime, before: datetime, n: int = 50) -> dict:
        p = {"part": "snippet", "q": q, "type": "video", "order": "viewCount", "maxResults": n,
             "regionCode": "KR", "relevanceLanguage": "ko",
             "publishedAfter": after.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "publishedBefore": before.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "key": self.key}
        return self.call(f"{YT}/search?{urllib.parse.urlencode(p)}")

    def views(self, ids: list[str]) -> dict:
        if not ids:
            return {}
        p = {"part": "statistics", "id": ",".join(ids), "key": self.key}
        d = self.call(f"{YT}/videos?{urllib.parse.urlencode(p)}")
        return {v["id"]: int((v.get("statistics") or {}).get("viewCount") or 0) for v in d.get("items", [])}


# ───── 텍스트 ─────

_TAG = re.compile(r"<[^>]+>")


def clean(s: str | None) -> str:
    return " ".join(html.unescape(_TAG.sub("", s or "")).split())


def _key(title: str) -> set:
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", title)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def similar(a: str, b: str, th: float = 0.5) -> bool:
    """제목 글자쌍 겹침(자카드) — 같은 사건을 여러 언론사가 쓴 기사 묶기용."""
    ka, kb = _key(a), _key(b)
    return bool(ka and kb) and len(ka & kb) / len(ka | kb) >= th


# ───── 수집 ─────

def collect_datalab(nv: Naver, cfg: dict, end: date) -> list[dict]:
    """→ [{week, series, value}]. series: <그룹 id> (묶음별 정규화), ratio_up / ratio_down (같은 요청 내 비교용)."""
    start, e = cfg.get("datalab_start", "2016-01-01"), end.isoformat()
    G = cfg["groups"]
    rows = []
    pair = cfg.get("ratio_pair") or []
    if len(pair) == 2:
        r = nv.datalab([{"groupName": gid, "keywords": G[gid]["keywords"]} for gid in pair], start, e)
        for gid in pair:
            rows += [{"week": p, "series": "ratio_" + gid, "value": v} for p, v in r.get(gid, [])]
    for gid, g in G.items():
        r = nv.datalab([{"groupName": gid, "keywords": g["keywords"]}], start, e)
        rows += [{"week": p, "series": gid, "value": v} for p, v in r.get(gid, [])]
    return rows


SOURCE = {"cafe": "cafearticle", "news": "news", "blog": "blog"}   # 설정 이름 → API HUB 경로


def collect_totals(nv: Naver, counts: list[dict]) -> dict:
    out = {}
    for c in counts:
        d = nv.search(SOURCE.get(c["source"], c["source"]), c["query"], display=1)
        out[c["id"]] = int(d.get("total") or 0)
    return out


def _is_ad(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def relevant(title: str, desc: str, topic: dict, F: dict) -> bool:
    """제목+요약에 부동산 단어가 하나 이상, 주제의 필수 단어(must)는 모두, 제외 단어는 하나도 없어야 함.
    네이버 카페·뉴스 검색은 '미사' → '터미사진', '고덕' → 평택 고덕 인테리어 같은 잡음이 많아서."""
    text = f"{title} {desc}"
    if _is_ad(text, F.get("ad_words") or []) or any(w in text for w in F.get("exclude_words") or []):
        return False
    # 부동산 단어와 주제 필수 단어는 '제목'에 있어야 함 (요약에만 스치듯 나오는 글은 대부분 다른 주제)
    if F.get("housing_words") and not any(w in title for w in F["housing_words"]):
        return False
    if any(w in text for w in topic.get("not") or []):
        return False
    return all(m in title for m in topic.get("must") or [])


def collect_feed(nv: Naver, yt: YouTube | None, cfg: dict, now: datetime, log=print) -> dict:
    F = cfg.get("feed") or {}
    per, cap = int(F.get("per_topic", 3)), int(F.get("max_items", 12))
    cutoff = now - timedelta(hours=int(F.get("news_hours", 48)))
    out = {"generated_at": now.isoformat(timespec="minutes"), "news": [], "cafe": [], "yt": []}

    for t in F.get("news") or []:
        try:
            items = nv.search("news", t["query"], display=50, sort="sim").get("items", [])
        except ApiError as e:
            log(f"뉴스 '{t['query']}': {e}")
            continue
        n = 0
        for it in items:
            title, desc = clean(it.get("title")), clean(it.get("description"))
            try:
                pub = parsedate_to_datetime(it.get("pubDate", ""))
            except (TypeError, ValueError):
                continue
            if pub < cutoff or not relevant(title, desc, t, F) or any(similar(title, x["t"]) for x in out["news"]):
                continue
            link = it.get("originallink") or it.get("link") or ""
            host = urllib.parse.urlparse(link).netloc.removeprefix("www.")
            out["news"].append({"t": title, "x": desc[:160], "u": it.get("link") or link, "s": host,
                                "d": pub.astimezone(KST).strftime("%m.%d %H:%M"), "ts": pub.isoformat(), "g": t["tag"]})
            n += 1
            if n >= per:
                break
    out["news"].sort(key=lambda x: x["ts"], reverse=True)
    out["news"] = out["news"][:cap]

    for t in F.get("cafe") or []:
        try:
            items = nv.search("cafearticle", t["query"], display=50, sort="date").get("items", [])
        except ApiError as e:
            log(f"카페 '{t['query']}': {e}")
            continue
        n = 0
        for it in items:
            title, desc = clean(it.get("title")), clean(it.get("description"))
            cafename = clean(it.get("cafename"))
            if (not relevant(title, desc, t, F) or any(w in cafename for w in F.get("exclude_cafes") or [])
                    or any(similar(title, x["t"], 0.6) for x in out["cafe"])):
                continue
            out["cafe"].append({"t": title, "x": desc[:160], "u": it.get("link") or "", "s": cafename, "g": t["tag"]})
            n += 1
            if n >= per:
                break
    out["cafe"] = out["cafe"][:cap]

    if yt:
        Y = cfg.get("youtube") or {}
        day0 = (now.astimezone(KST) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            d = yt.search(Y.get("query", "부동산|아파트|집값"), day0, day0 + timedelta(days=1))
            words = Y.get("title_words") or []
            items = [it for it in d.get("items", []) if (it.get("id") or {}).get("videoId")
                     and (not words or any(w in clean((it.get("snippet") or {}).get("title")) for w in words))
                     and not any(w in clean((it.get("snippet") or {}).get("title")) for w in Y.get("exclude_words") or [])]
            top = items[: int(Y.get("top", 5))]
            views = yt.views([it["id"]["videoId"] for it in top])
            for it in top:
                sn, vid = it.get("snippet") or {}, it["id"]["videoId"]
                pub = sn.get("publishedAt", "")
                out["yt"].append({"t": clean(sn.get("title")), "x": clean(sn.get("description"))[:160],
                                  "u": f"https://www.youtube.com/watch?v={vid}", "s": clean(sn.get("channelTitle")),
                                  "d": pub[5:10].replace("-", "."), "v": views.get(vid)})
            out["yt_day"] = day0.date().isoformat()
            out["yt_total"] = int((d.get("pageInfo") or {}).get("totalResults") or 0)
        except ApiError as e:
            log(f"유튜브: {e}")
    return out


# ───── 파일 ─────

def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    tmp.replace(path)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def upsert_daily(path: Path, fields: list[str], key: tuple, new_rows: list[dict]) -> None:
    rows = {tuple(r[k] for k in key): r for r in read_csv(path)}
    for r in new_rows:
        rows[tuple(str(r[k]) for k in key)] = {k: str(v) for k, v in r.items()}
    write_csv(path, fields, sorted(rows.values(), key=lambda r: tuple(r[k] for k in key)))


def prune_feed(dirpath: Path, keep_days: int, today: date) -> None:
    for p in dirpath.glob("????-??-??.json"):
        try:
            if (today - date.fromisoformat(p.stem)).days > keep_days:
                p.unlink()
        except ValueError:
            continue
