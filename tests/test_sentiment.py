import json
from datetime import datetime, timedelta, timezone

import pandas as pd

from realestate import mood, sentiment as st

KST = timezone(timedelta(hours=9))
CFG = {"groups": {"up": {"name": "상승", "keywords": ["집값 상승"]}, "down": {"name": "하락", "keywords": ["집값 하락"]}},
       "ratio_pair": ["up", "down"], "counts": [{"id": "cafe_sell", "source": "cafe", "query": "급매"}],
       "feed": {"news": [{"tag": "정책", "query": "부동산 대책"}], "cafe": [{"tag": "고덕", "query": "고덕 아파트"}],
                "per_topic": 2, "max_items": 5, "news_hours": 48, "ad_words": ["분양"],
                "housing_words": ["대책", "금리", "고덕", "아파트", "세안고", "이사"], "exclude_words": ["스페인"]},
       "youtube": {"query": "부동산", "top": 2}}


def test_clean_and_similar():
    assert st.clean("<b>집값</b> &quot;급등&quot;") == '집값 "급등"'
    assert st.similar("정부, 수도권 공급 대책 발표…착공 앞당겨", "정부 수도권 공급대책 발표 착공 앞당긴다")
    assert not st.similar("강남 급매 늘어", "하남 미사 신고가")


class FakeNaver:
    def __init__(self):
        self.calls = []

    def search(self, source, query, display=10, sort="date"):
        self.calls.append((source, query))
        if source == "news":
            now = datetime(2026, 10, 4, 9, 0, tzinfo=KST)
            fmt = lambda h: (now - timedelta(hours=h)).strftime("%a, %d %b %Y %H:%M:%S +0900")  # noqa: E731
            return {"items": [
                {"title": "<b>부동산 대책</b> 발표…공급 확대", "description": "요약", "link": "https://n.news/1", "originallink": "https://www.a.com/1", "pubDate": fmt(1)},
                {"title": "부동산 대책 발표, 공급 확대", "description": "같은 사건", "link": "https://n.news/2", "originallink": "https://b.com/2", "pubDate": fmt(2)},
                {"title": "신규 분양 단지 소개", "description": "광고", "link": "https://n.news/3", "pubDate": fmt(3)},
                {"title": "금리 인상 여파", "description": "요약2", "link": "https://n.news/4", "pubDate": fmt(5)},
                {"title": "오래된 기사 금리", "description": "", "link": "https://n.news/5", "pubDate": fmt(100)},
                {"title": "스페인 주택난 대책 시위", "description": "", "link": "https://n.news/6", "pubDate": fmt(1)}]}
        return {"total": 1234, "items": [{"title": "고덕 84 세안고", "description": "문의", "link": "https://cafe/1", "cafename": "카페A"},
                                         {"title": "고덕 이사 고민", "description": "내용", "link": "https://cafe/2", "cafename": "카페B"}]}


class FakeYT:
    def search(self, q, after, before, n=50):
        return {"pageInfo": {"totalResults": 1500},
                "items": [{"id": {"videoId": "a1"}, "snippet": {"title": "영상1", "description": "설명", "channelTitle": "채널", "publishedAt": "2026-10-03T10:00:00Z"}},
                          {"id": {"videoId": "b2"}, "snippet": {"title": "영상2", "description": "", "channelTitle": "채널2", "publishedAt": "2026-10-03T11:00:00Z"}}]}

    def views(self, ids):
        return {"a1": 1000, "b2": 500}


def test_collect_feed_filters_and_dedupes():
    f = st.collect_feed(FakeNaver(), FakeYT(), CFG, datetime(2026, 10, 4, 9, 0, tzinfo=KST))
    titles = [x["t"] for x in f["news"]]
    assert titles == ["부동산 대책 발표…공급 확대", "금리 인상 여파"]     # 같은 사건 1개, 광고·48시간 지난 기사 제외
    assert f["news"][0]["s"] == "a.com" and f["news"][0]["u"] == "https://n.news/1"
    assert [x["s"] for x in f["cafe"]] == ["카페A", "카페B"]
    assert f["yt"][0]["u"].endswith("v=a1") and f["yt"][0]["v"] == 1000 and f["yt_total"] == 1500 and f["yt_day"] == "2026-10-03"


def test_mood_build(tmp_path):
    base = tmp_path / "s"
    st.write_csv(base / "datalab_weekly.csv", ["week", "series", "value"],
                 [{"week": "2026-09-21", "series": "ratio_up", "value": 50}, {"week": "2026-09-21", "series": "ratio_down", "value": 25},
                  {"week": "2026-09-21", "series": "up", "value": 80}, {"week": "2026-09-21", "series": "down", "value": 40}])
    st.upsert_daily(base / "search_totals.csv", ["date", "id", "total"], ("date", "id"),
                    [{"date": "2026-10-03", "id": "cafe_sell", "total": 1000}])
    st.upsert_daily(base / "search_totals.csv", ["date", "id", "total"], ("date", "id"),
                    [{"date": "2026-10-04", "id": "cafe_sell", "total": 1060}])
    (base / "feed").mkdir()
    (base / "feed" / "latest.json").write_text(json.dumps({"news": [{"t": "a", "ts": "x"}], "cafe": [], "yt": []}), encoding="utf-8")
    m = mood.build(base, {"sentiment": CFG}, tmp_path / "none.csv")
    assert m["wk"]["greed"] == [2.0]
    assert m["daily"]["cafe_sell"] == [None, 60]
    assert "ts" not in m["feed"]["news"][0]
    json.dumps(m, allow_nan=False)
    assert pd.read_csv(base / "search_totals.csv").shape[0] == 2


def test_totals_use_hub_paths():
    nv = FakeNaver()
    st.collect_totals(nv, [{"id": "a", "source": "cafe", "query": "급매"}, {"id": "b", "source": "news", "query": "집값"}])
    assert nv.calls == [("cafearticle", "급매"), ("news", "집값")]


def test_relevant_must_and_not():
    F = {"housing_words": ["아파트"], "ad_words": ["인테리어"]}
    t = {"must": ["고덕"], "not": ["평택"]}
    assert st.relevant("고덕 아파트 매수 고민", "", t, F)
    assert not st.relevant("고덕 사진 모임", "아파트 단지 산책", t, F)          # 부동산 단어가 요약에만
    assert not st.relevant("평택 고덕 아파트", "", t, F)
    assert not st.relevant("고덕 아파트 인테리어 후기", "", t, F)
    assert not st.relevant("미사 아파트", "", t, F)
