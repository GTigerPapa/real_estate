"""API XML 응답 → dict, 그리고 DB 행으로 정규화."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field

OK_CODES = {"00", "000"}
NO_DATA_CODES = {"03"}


class ApiResponseError(Exception):
    """API가 오류 봉투(OpenAPI_ServiceResponse) 또는 비정상 resultCode를 반환."""

    def __init__(self, code: str | None, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass
class Parsed:
    result_code: str | None
    result_msg: str | None
    total_count: int
    page_no: int | None
    num_of_rows: int | None
    items: list[dict] = field(default_factory=list)


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    s = el.text.strip()
    return s or None


def _int_or_none(s: str | None) -> int | None:
    return int(s) if s not in (None, "") else None


def parse_response(xml_text: str) -> Parsed:
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as e:
        raise ApiResponseError(None, f"XML 파싱 실패: {e}") from None

    if root.tag == "OpenAPI_ServiceResponse":
        hdr = root.find("cmmMsgHeader")
        code = _text(hdr.find("returnReasonCode")) if hdr is not None else None
        msg = _text(hdr.find("errMsg")) if hdr is not None else None
        auth = _text(hdr.find("returnAuthMsg")) if hdr is not None else None
        raise ApiResponseError(code, " / ".join(x for x in (msg, auth) if x) or "알 수 없는 오류")

    code = _text(root.find("header/resultCode"))
    msg = _text(root.find("header/resultMsg"))
    if code not in OK_CODES and code not in NO_DATA_CODES:
        raise ApiResponseError(code, msg or "resultCode 비정상")

    body = root.find("body")
    items = []
    if body is not None and body.find("items") is not None:
        for it in body.find("items").findall("item"):
            items.append({c.tag: _text(c) for c in it})
    return Parsed(
        result_code=code,
        result_msg=msg,
        total_count=_int_or_none(_text(root.find("body/totalCount"))) or 0,
        page_no=_int_or_none(_text(root.find("body/pageNo"))),
        num_of_rows=_int_or_none(_text(root.find("body/numOfRows"))),
        items=items,
    )


# ───── 값 변환 ─────

def to_int_amount(s: str | None) -> int | None:
    """'103,000' → 103000 (만원)."""
    if s is None:
        return None
    s = s.replace(",", "").strip()
    return int(s) if s else None


def to_iso_date(s: str | None) -> str | None:
    """'26.05.07' / '2026.05.07' / '2026-05-07' / '20260507' → '2026-05-07'."""
    if not s:
        return None
    s = s.strip()
    m = re.fullmatch(r"(\d{2}|\d{4})[.\-/]?(\d{1,2})[.\-/]?(\d{1,2})", s)
    if not m:
        return None
    y, mo, d = m.groups()
    if len(y) == 2:
        y = "20" + y
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def deal_date(item: dict) -> str:
    return f"{int(item['dealYear']):04d}-{int(item['dealMonth']):02d}-{int(item['dealDay']):02d}"


def _floor(s: str | None) -> int:
    # 층 누락은 0으로 (UNIQUE 키에 NULL 불가)
    return int(s) if s not in (None, "") else 0


def normalize_trade(item: dict) -> dict:
    cdeal = (item.get("cdealType") or "").upper()
    return {
        "sgg_cd": item.get("sggCd") or "",
        "umd_cd": item.get("umdCd"),
        "umd_nm": item.get("umdNm"),
        "jibun": item.get("jibun"),
        "apt_seq": item.get("aptSeq") or "",
        "apt_nm": item.get("aptNm"),
        "apt_dong": item.get("aptDong") or "",
        "deal_date": deal_date(item),
        "exclu_use_ar": float(item["excluUseAr"]),
        "floor": _floor(item.get("floor")),
        "deal_amount": to_int_amount(item.get("dealAmount")),
        "dealing_gbn": item.get("dealingGbn"),
        "is_canceled": 1 if cdeal == "O" else 0,
        "cancel_date": to_iso_date(item.get("cdealDay")),
        "rgst_date": to_iso_date(item.get("rgstDate")),
        "buyer_gbn": item.get("buyerGbn"),
        "sler_gbn": item.get("slerGbn"),
        "agent_sgg_nm": item.get("estateAgentSggNm"),
        "build_year": _int_or_none(item.get("buildYear")),
    }


def normalize_rent(item: dict) -> dict:
    deposit = to_int_amount(item.get("deposit")) or 0
    monthly = to_int_amount(item.get("monthlyRent")) or 0
    return {
        "sgg_cd": item.get("sggCd") or "",
        "umd_cd": item.get("umdCd"),
        "umd_nm": item.get("umdNm"),
        "jibun": item.get("jibun"),
        "apt_seq": item.get("aptSeq") or "",
        "apt_nm": item.get("aptNm"),
        "deal_date": deal_date(item),
        "exclu_use_ar": float(item["excluUseAr"]),
        "floor": _floor(item.get("floor")),
        "deposit": deposit,
        "monthly_rent": monthly,
        "rent_type": "전세" if monthly == 0 else "월세",
        "contract_term": item.get("contractTerm") or "",
        "contract_type": item.get("contractType"),
        "use_rr_right": item.get("useRRRight"),
        "pre_deposit": to_int_amount(item.get("preDeposit")),
        "pre_monthly_rent": to_int_amount(item.get("preMonthlyRent")),
        "build_year": _int_or_none(item.get("buildYear")),
    }


TRADE_KEY = ("sgg_cd", "apt_seq", "deal_date", "exclu_use_ar", "floor", "deal_amount", "apt_dong")
RENT_KEY = ("sgg_cd", "apt_seq", "deal_date", "exclu_use_ar", "floor", "deposit", "monthly_rent", "contract_term")


def assign_dup_seq(rows: list[dict], key: tuple[str, ...]) -> list[dict]:
    """같은 월 응답 안에서 키가 완전히 같은 건에 1, 2, ... 순번 부여.

    동일 키 그룹 내에서는 나머지 필드로 정렬해 재수집 시에도 순번이 안정적이도록 한다.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in key)].append(r)
    for grp in groups.values():
        grp.sort(key=lambda r: tuple("" if v is None else str(v) for v in r.values()))
        for i, r in enumerate(grp, 1):
            r["dup_seq"] = i
    return rows
