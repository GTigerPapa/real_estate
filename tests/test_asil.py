from datetime import date

from realestate import asil

SAMPLE = (
    "\r\nchartData.length = 0; listData.length = 0; "
    'chartData[0] = {"Date":"26/9/1","VM":51,"VJ":2,"VW":2};'
    'listData[2] = {"Date":"26/09/01","VM":51,"VJ":2,"VW":2,"gVM":"","gVJ":"","gVW":"","gTotal":""};'
    'chartData[1] = {"Date":"26/9/2","VM":52,"VJ":2,"VW":2};'
    'listData[1] = {"Date":"26/09/02","VM":52,"VJ":2,"VW":2,"gVM":"","gVJ":"","gVW":"","gTotal":""};'
    'listData[0] = {"Date":"26/09/03","VM":53,"VJ":3,"VW":2,"gVM":"2","gVJ":"1","gVW":"","gTotal":"3"};'
)
COMPLEXES = [{"id": "godeok_xi", "name": "고덕자이", "naver_id": 121977},
             {"id": "misa", "name": "미사", "naver_id": 111028}]


def test_parse_uses_list_rows_only_and_sorts():
    rows = asil.parse(SAMPLE)
    assert [r["date"] for r in rows] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert rows[-1] == {"date": "2026-09-03", "sale": 53, "jeonse": 3, "wolse": 2}


def test_parse_empty_response():
    assert asil.parse("\r\n") == []


def test_build_url_has_complex_and_range():
    u = asil.build_url(121977, date(2023, 9, 1), date(2026, 9, 1))
    assert "apt=121977" in u and "sY=2023" in u and "sM=9" in u and "eY=2026" in u


def test_collect_merges_overwrites_and_reports_failures(tmp_path):
    out = tmp_path / "a.csv"
    calls = []

    def fake(nid, s, e):
        calls.append(nid)
        return SAMPLE if nid == 121977 else "\r\n"

    failed = asil.collect(COMPLEXES, out, date(2026, 9, 1), date(2026, 9, 1), fetcher=fake, pause=0, log=lambda m: None)
    assert failed == ["misa"] and calls == [121977, 111028]
    rows = asil.read_csv(out)
    assert len(rows) == 3
    assert rows[("2026-09-03", "godeok_xi")]["total"] == "58"

    # 다시 받으면 과거 값이 바뀐 경우 덮어쓰고, 행이 늘지 않는다
    changed = SAMPLE.replace('"26/09/03","VM":53', '"26/09/03","VM":60')
    asil.collect(COMPLEXES[:1], out, date(2026, 9, 1), date(2026, 9, 1),
                 fetcher=lambda *_: changed, pause=0, log=lambda m: None)
    rows = asil.read_csv(out)
    assert len(rows) == 3 and rows[("2026-09-03", "godeok_xi")]["sale"] == "60"
    assert out.read_text(encoding="utf-8").splitlines()[0] == ",".join(asil.FIELDS)
