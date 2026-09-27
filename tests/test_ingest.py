from realestate import db
from realestate.api.client import RtmsClient
from realestate.ingest import add_months, ingest_month, months_between, plan
from tests.test_client_security import FakeResp, FakeSession


def test_months():
    assert add_months("202312", 1) == "202401" and add_months("202401", -1) == "202312"
    m = months_between("202310", "202609")
    assert len(m) == 36 and m[0] == "202310" and m[-1] == "202609"


def test_plan_skips_done_except_recent(conn):
    for ym in ("202606", "202607", "202608"):
        db.set_fetch_log(conn, "trade", "11740", ym, "ok", 1, 1, "t")
    tasks = plan(conn, ["trade"], ["11740"], months_between("202606", "202609"), 3, "202609")
    # 202606: 완료 & 최근 3개월(07~09) 밖 → 건너뜀
    assert [t[2] for t in tasks] == ["202607", "202608", "202609"]
    assert len(plan(conn, ["trade"], ["11740"], ["202606"], 3, "202609", force=True)) == 1


def test_pagination_and_log(conn, fixture_text, fake_key):
    xml = fixture_text("trade_sample.xml")
    # 1페이지 2건 / 2페이지 1건, totalCount=3
    items = xml.split("<item>")
    head, its = items[0], ["<item>" + i for i in items[1:]]
    tail = "</items><numOfRows>2</numOfRows><pageNo>{}</pageNo><totalCount>3</totalCount></body></response>"
    p1 = head + its[0] + its[1].split("</items>")[0] + tail.format(1)
    p2 = head + its[2].split("</items>")[0] + tail.format(2)
    s = FakeSession([FakeResp(200, p1), FakeResp(200, p2)])
    c = RtmsClient(key=fake_key, session=s, sleep=lambda x: None, request_interval_sec=0)
    r = ingest_month(conn, c, "trade", "11740", "202508")
    assert r["status"] == "ok" and r["rows"] == 3 and s.calls == 2
    log = conn.execute("SELECT * FROM fetch_log").fetchone()
    assert log["status"] == "ok" and log["row_count"] == 3
