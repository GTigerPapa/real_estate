"""공공데이터포털 실거래 API 클라이언트.

키 보안 원칙
- 키는 os.environ["DATA_GO_KR_KEY"]에서만 읽는다.
- requests 예외는 URL(키 포함)이 담길 수 있으므로 메시지를 버리고 예외 타입명만 남겨 재발생한다(`from None`).
- 로깅 핸들러에 키 마스킹 필터를 건다 (urllib3 DEBUG 로그의 URL 포함).
"""
from __future__ import annotations

import logging
import os
import random
import time
import traceback
from dataclasses import dataclass
from urllib.parse import quote, quote_plus

import requests

from .parse import ApiResponseError, Parsed, parse_response

ENDPOINTS = {
    "trade": "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "rent": "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
}
KEY_ENV = "DATA_GO_KR_KEY"
MASK = "***"
# 재시도해볼 만한 게이트웨이 오류 코드 (APPLICATION_ERROR, HTTP_ERROR, SERVICE_TIME_OUT)
RETRYABLE_GATEWAY_CODES = {"1", "01", "4", "04", "5", "05"}

log = logging.getLogger(__name__)


# 재시도해도 소용없는 오류: 접근거부, 일일한도 초과, 미등록/만료 키, 미등록 IP
FATAL_GATEWAY_CODES = {"20", "22", "30", "31", "32"}


class ApiError(Exception):
    """URL·키가 포함되지 않은 메시지만 담는 예외. fatal이면 같은 API의 남은 호출도 무의미.
    unreachable: 재시도가 모두 연결 단계에서 실패(서버에 닿지 않음) → 다른 API 호출도 무의미."""

    def __init__(self, message: str, fatal: bool = False, unreachable: bool = False):
        super().__init__(message)
        self.fatal = fatal or unreachable
        self.unreachable = unreachable


def get_service_key() -> str:
    key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError(f"{KEY_ENV} 환경변수가 설정되지 않았습니다 (.env.example 참고)")
    return key


def key_variants(key: str) -> list[str]:
    """원문·URL 인코딩 형태 모두 (긴 것부터 치환)."""
    vs = {key, quote(key, safe=""), quote_plus(key), quote(key)}
    return sorted((v for v in vs if v), key=len, reverse=True)


def mask_secret(text: str, key: str | None = None) -> str:
    key = key if key is not None else os.environ.get(KEY_ENV)
    if not key or not text:
        return text
    for v in key_variants(key):
        text = text.replace(v, MASK)
    return text


class KeyMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        key = os.environ.get(KEY_ENV)
        if not key:
            return True
        msg = record.getMessage()
        masked = mask_secret(msg, key)
        if masked != msg:
            record.msg, record.args = masked, None
        if record.exc_info and not record.exc_text:
            record.exc_text = "".join(traceback.format_exception(*record.exc_info)).rstrip()
        if record.exc_text:
            record.exc_text = mask_secret(record.exc_text, key)
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """루트 로거 설정 + 모든 핸들러에 키 마스킹 필터."""
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    for h in root.handlers:
        if not any(isinstance(f, KeyMaskingFilter) for f in h.filters):
            h.addFilter(KeyMaskingFilter())


@dataclass
class Page:
    page_no: int
    body: str          # XML 원문
    parsed: Parsed


class RtmsClient:
    def __init__(
        self,
        key: str | None = None,
        num_of_rows: int = 1000,
        request_interval_sec: float = 0.3,
        timeout_sec: float = 30,
        max_retries: int = 4,
        backoff_base_sec: float = 1.0,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ):
        self._key = key or get_service_key()
        self.num_of_rows = num_of_rows
        self.interval = request_interval_sec
        self.timeout = timeout_sec
        self.max_retries = max_retries
        self.backoff = backoff_base_sec
        self.session = session or requests.Session()
        self._sleep = sleep
        self._last_call = 0.0
        self.calls = 0

    @classmethod
    def from_settings(cls, settings: dict, **kw) -> "RtmsClient":
        a = settings.get("api", {})
        return cls(
            num_of_rows=a.get("num_of_rows", 1000),
            request_interval_sec=a.get("request_interval_sec", 0.3),
            timeout_sec=a.get("timeout_sec", 30),
            max_retries=a.get("max_retries", 4),
            backoff_base_sec=a.get("backoff_base_sec", 1.0),
            **kw,
        )

    def __repr__(self) -> str:  # 키 노출 방지
        return f"RtmsClient(num_of_rows={self.num_of_rows})"

    def _throttle(self) -> None:
        wait = self.interval - (time.monotonic() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = time.monotonic()

    def fetch_page(self, api: str, lawd_cd: str, deal_ymd: str, page_no: int) -> Page:
        ctx = f"{api} {lawd_cd} {deal_ymd} p{page_no}"
        params = {
            "serviceKey": self._key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ymd,
            "pageNo": page_no,
            "numOfRows": self.num_of_rows,
        }
        last_err = ""
        conn_fail = 0   # 연결 자체가 안 된 횟수 (ConnectTimeout·ConnectionError)
        for attempt in range(self.max_retries + 1):
            if attempt:
                delay = self.backoff * 2 ** (attempt - 1) + random.uniform(0, 0.5)
                log.warning("%s 재시도 %d/%d (%.1fs 후): %s", ctx, attempt, self.max_retries, delay, last_err)
                self._sleep(delay)
            self._throttle()
            self.calls += 1
            try:
                # 연결은 10초 안에 안 되면 포기 (막힌 네트워크에서 오래 매달리지 않게), 응답 대기는 설정값
                resp = self.session.get(ENDPOINTS[api], params=params, timeout=(min(10, self.timeout), self.timeout))
            except requests.RequestException as e:
                # str(e)에는 URL이 들어갈 수 있으므로 타입명만 사용
                last_err = type(e).__name__
                if isinstance(e, (requests.ConnectTimeout, requests.ConnectionError)) and not isinstance(e, requests.ReadTimeout):
                    conn_fail += 1
                continue

            text = mask_secret(resp.content.decode("utf-8", errors="replace"), self._key)
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"HTTP {resp.status_code}"
                continue
            try:
                parsed = parse_response(text)
            except ApiResponseError as e:
                if e.code in RETRYABLE_GATEWAY_CODES:
                    last_err = f"API {e}"
                    continue
                raise ApiError(f"{ctx}: HTTP {resp.status_code} API 오류 {e}",
                               fatal=e.code in FATAL_GATEWAY_CODES) from None
            if resp.status_code != 200:
                raise ApiError(f"{ctx}: HTTP {resp.status_code}")
            return Page(page_no=page_no, body=text, parsed=parsed)

        unreachable = conn_fail == self.max_retries + 1
        raise ApiError(f"{ctx}: {self.max_retries}회 재시도 후 실패 ({last_err})"
                       + (" — 서버에 연결되지 않음 (공공데이터포털은 해외 IP 접속이 막힐 수 있음)" if unreachable else ""),
                       unreachable=unreachable)

    def fetch_month(self, api: str, lawd_cd: str, deal_ymd: str) -> list[Page]:
        """해당 월 전체 페이지. totalCount만큼 모일 때까지 페이지를 넘긴다."""
        pages: list[Page] = []
        got = 0
        page_no = 1
        while True:
            p = self.fetch_page(api, lawd_cd, deal_ymd, page_no)
            pages.append(p)
            got += len(p.parsed.items)
            if not p.parsed.items or got >= p.parsed.total_count:
                break
            page_no += 1
        return pages
