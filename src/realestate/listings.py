"""네이버 매물 덤프(북마클릿 → data/listings/raw/*.json) 적재와 스냅샷 지표.

덤프 형식 (tools/bookmarklet_src.js 가 만든다, format=1):
{
  "format": 1, "captured_at": "2026-09-28T07:10:00+09:00", "page": "...",
  "complexes": [
    {"id": "godeok_xi", "naver_id": 121977, "name": "고덕자이",
     "responses": [{"key": "article_stats", "url": "...", "params": {...}, "status": 200,
                    "ok": true, "json": {...}}  # 실패 시 "text": "..."
    ]}
  ],
  "discovery": [...]   # 매물 목록 엔드포인트 후보 시도 결과 (첫 단지에서만)
}

응답 구조를 미리 알 수 없으므로 원문(listing_raw)과 모든 숫자 값(listing_metric, JSON 경로별)을 보존하고,
"매물 수"·"최저 호가"가 어느 경로인지는 settings.yaml listing_metrics 의 정규식으로 고른다.
표준 라이브러리 + PyYAML만 사용 (Mac Python 3.9에서 실행되는 scripts/save_listings.py 가 쓴다).
"""
from __future__ import annotations

import json
import re
import zlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
FORMAT = 1


class DumpError(ValueError):
    pass


def load_dump(path: Path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise DumpError(f"{Path(path).name}: JSON을 읽을 수 없음 ({type(e).__name__})") from None
    if not isinstance(d, dict) or d.get("format") != FORMAT or not isinstance(d.get("complexes"), list):
        raise DumpError(f"{Path(path).name}: 북마클릿 덤프 형식(format={FORMAT})이 아님")
    if not d.get("captured_at"):
        raise DumpError(f"{Path(path).name}: captured_at 없음")
    return d


def snap_date_of(captured_at: str) -> str:
    dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST).strftime("%Y-%m-%d")


def flatten_numbers(obj, prefix: str = "") -> list:
    """JSON의 숫자 리프를 [(경로, 값)]로. 불리언은 제외, 숫자 문자열('1,234')은 숫자로."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += flatten_numbers(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += flatten_numbers(v, f"{prefix}[{i}]")
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.append((prefix, float(obj)))
    elif isinstance(obj, str):
        s = obj.replace(",", "").strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            out.append((prefix, float(s)))
    return out


def ingest_file(conn, path: Path, now: str | None = None) -> dict:
    """덤프 파일 하나 적재. 이미 적재된 파일이면 건너뜀. {'loaded': bool, 'metrics': n, 'snap_date': ...}"""
    path = Path(path)
    if conn.execute("SELECT 1 FROM listing_raw WHERE file_name=?", (path.name,)).fetchone():
        return {"loaded": False, "metrics": 0, "snap_date": None}
    d = load_dump(path)
    snap = snap_date_of(d["captured_at"])
    now = now or datetime.now(KST).isoformat(timespec="seconds")
    rows = []
    for c in d["complexes"]:
        cid = c.get("id")
        for r in c.get("responses", []):
            if not (cid and r.get("ok") and isinstance(r.get("json"), (dict, list))):
                continue
            params = json.dumps(r.get("params") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for p, v in flatten_numbers(r["json"]):
                rows.append((snap, cid, r["key"], params, p, v, d["captured_at"]))
    with conn:
        conn.execute("INSERT INTO listing_raw (file_name, captured_at, snap_date, format, body, loaded_at) "
                     "VALUES (?,?,?,?,?,?)",
                     (path.name, d["captured_at"], snap, d.get("format"), zlib.compress(path.read_bytes(), 9), now))
        conn.executemany("INSERT OR REPLACE INTO listing_metric VALUES (?,?,?,?,?,?,?)", rows)
    return {"loaded": True, "metrics": len(rows), "snap_date": snap}


def ingest_dir(conn, raw_dir: Path) -> list:
    """폴더의 naver_listings_*.json 중 미적재 파일을 모두 적재. [(파일명, 결과)]"""
    results = []
    for p in sorted(Path(raw_dir).glob("naver_listings_*.json")):
        try:
            results.append((p.name, ingest_file(conn, p)))
        except DumpError as e:
            results.append((p.name, {"loaded": False, "error": str(e)}))
    return results


def raw_dir_signature(raw_dir: Path) -> tuple:
    """대시보드 캐시 키용: (파일명, 크기) 목록."""
    return tuple((p.name, p.stat().st_size) for p in sorted(Path(raw_dir).glob("naver_listings_*.json")))


# ───── 스냅샷 지표 ─────

def _pick_path(paths, patterns):
    for pat in patterns:
        rx = re.compile(pat)
        for p in paths:
            if rx.search(p):
                return p
    return None


def snapshot(conn, settings: dict):
    """settings['listing_metrics'] 규칙으로 listing_metric → DataFrame
    (snap_date, complex_id, metric, pyeong_type, value). pandas는 여기서만 사용."""
    import pandas as pd

    rules = settings.get("listing_metrics") or {}
    df = pd.read_sql_query("SELECT snap_date, complex_id, endpoint, params, path, value FROM listing_metric", conn)
    cols = ["snap_date", "complex_id", "metric", "pyeong_type", "value"]
    if df.empty or not rules:
        return pd.DataFrame(columns=cols)
    df["params_d"] = df["params"].map(lambda s: json.loads(s) if s else {})
    df["trade"] = df["params_d"].map(lambda p: p.get("tradeType"))
    df["pyeong_type"] = df["params_d"].map(lambda p: p.get("pyeongTypeNumber"))
    out = []
    for metric, rule in rules.items():
        sub = df[df["endpoint"] == rule["endpoint"]]
        if rule.get("trade") is not None:
            # trade 파라미터가 없는 엔드포인트(article_stats 등)는 경로에 거래유형이 들어있다고 보고 통과
            sub = sub[(sub["trade"] == rule["trade"]) | sub["trade"].isna()]
        if sub.empty:
            continue
        path = _pick_path(sorted(sub["path"].unique()), rule.get("paths", []))
        if path is None:
            continue
        hit = sub[sub["path"] == path]
        for r in hit.itertuples():
            out.append((r.snap_date, r.complex_id, metric, r.pyeong_type, r.value))
    return pd.DataFrame(out, columns=cols)


def available_paths(conn):
    """경로 확정용: 엔드포인트별 경로와 예시값 (대시보드 '경로 보기'에 표시)."""
    import pandas as pd

    return pd.read_sql_query(
        "SELECT endpoint, params, path, COUNT(DISTINCT snap_date) AS days, MIN(value) AS min_v, MAX(value) AS max_v "
        "FROM listing_metric GROUP BY endpoint, params, path ORDER BY endpoint, params, path", conn)
