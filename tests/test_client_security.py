"""키 미노출 테스트: 예외 메시지·트레이스백·로그·DB 원문 어디에도 키가 없어야 한다."""
import logging
import traceback
from urllib.parse import quote_plus

import pytest
import requests

from realestate import db
from realestate.api.client import ApiError, KeyMaskingFilter, RtmsClient, key_variants, mask_secret
from realestate.ingest import ingest_month


class FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.content = text.encode("utf-8")


class FakeSession:
    """requests가 실제로 만드는 것처럼 URL(키 포함)을 예외 메시지에 넣는다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        full = f"{url}?serviceKey={quote_plus(params['serviceKey'])}&LAWD_CD={params['LAWD_CD']}"
        r = self.responses.pop(0)
        if r == "conn":
            raise requests.ConnectionError(f"HTTPSConnectionPool: Max retries exceeded with url: {full}")
        if r == "timeout":
            raise requests.ReadTimeout(f"Read timed out. url={full}")
        return r


def _client(session, key):
    return RtmsClient(key=key, session=session, sleep=lambda s: None, request_interval_sec=0, max_retries=2)


def _assert_no_key(text, key):
    for v in key_variants(key):
        assert v not in text, "키가 노출됨"


def test_network_error_hides_key(fake_key):
    c = _client(FakeSession(["conn", "timeout", "conn"]), fake_key)
    with pytest.raises(ApiError) as ei:
        c.fetch_page("trade", "11740", "202508", 1)
    _assert_no_key(str(ei.value), fake_key)
    tb = "".join(traceback.format_exception(ei.type, ei.value, ei.tb))
    _assert_no_key(tb, fake_key)
    assert ei.value.__cause__ is None and ei.value.__context__ is None  # 원 예외(URL 포함) 체인 없음


def test_retry_then_success(fake_key, fixture_text):
    s = FakeSession(["conn", FakeResp(503, ""), FakeResp(200, fixture_text("trade_sample.xml"))])
    page = _client(s, fake_key).fetch_page("trade", "11740", "202508", 1)
    assert s.calls == 3 and len(page.parsed.items) == 3


def test_auth_error_is_fatal_no_retry(fake_key, fixture_text):
    s = FakeSession([FakeResp(403, fixture_text("error_key.xml"))])
    with pytest.raises(ApiError) as ei:
        _client(s, fake_key).fetch_page("rent", "11740", "202508", 1)
    assert ei.value.fatal and s.calls == 1
    _assert_no_key(str(ei.value), fake_key)


def test_logging_filter_masks(fake_key, caplog):
    logger = logging.getLogger("test.mask")
    caplog.handler.addFilter(KeyMaskingFilter())
    with caplog.at_level(logging.DEBUG):
        logger.debug("GET /x?serviceKey=%s", quote_plus(fake_key))
        try:
            raise ValueError(f"boom {fake_key}")
        except ValueError:
            logger.exception("err")
    _assert_no_key(caplog.text, fake_key)
    assert "***" in caplog.text


def test_mask_secret_variants(fake_key):
    for v in key_variants(fake_key):
        assert mask_secret(f"a{v}b", fake_key) == "a***b"


def test_repr_hides_key(fake_key):
    _assert_no_key(repr(_client(FakeSession([]), fake_key)), fake_key)


def test_db_has_no_key_even_if_echoed(fake_key, fixture_text, conn):
    # 서버가 응답에 키를 되돌려줘도 원문 저장 전에 마스킹
    xml = fixture_text("trade_sample.xml").replace("<resultMsg>OK", f"<resultMsg>OK {fake_key}")
    ingest_month(conn, _client(FakeSession([FakeResp(200, xml)]), fake_key), "trade", "11740", "202508")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(raw_response)")]
    assert not any("url" in c.lower() for c in cols)
    for (blob,) in conn.execute("SELECT body FROM raw_response WHERE body IS NOT NULL"):
        _assert_no_key(db.decompress(blob), fake_key)
    for (err,) in conn.execute("SELECT COALESCE(error,'') FROM fetch_log"):
        _assert_no_key(err, fake_key)


def test_unreachable_server_is_marked(fake_key):
    # 재시도가 모두 연결 단계 실패면 unreachable (다른 API 호출도 멈추게), 읽기 타임아웃이 섞이면 아님
    c = _client(FakeSession(["conn", "conn", "conn"]), fake_key)
    with pytest.raises(ApiError) as ei:
        c.fetch_page("trade", "11740", "202508", 1)
    assert ei.value.unreachable and ei.value.fatal
    _assert_no_key(str(ei.value), fake_key)
    c = _client(FakeSession(["conn", "timeout", "conn"]), fake_key)
    with pytest.raises(ApiError) as ei:
        c.fetch_page("trade", "11740", "202508", 1)
    assert not ei.value.unreachable
