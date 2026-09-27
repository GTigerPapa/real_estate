"""SQLite 연결, 스키마 초기화, UPSERT, 설정 동기화."""
from __future__ import annotations

import hashlib
import sqlite3
import zlib
from importlib import resources
from pathlib import Path

from .api.parse import RENT_KEY, TRADE_KEY

TABLE_KEYS = {
    "apt_trade": TRADE_KEY + ("dup_seq",),
    "apt_rent": RENT_KEY + ("dup_seq",),
}


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    sql = resources.files("realestate").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


# ───── raw / fetch_log ─────

def compress(body: str) -> bytes:
    return zlib.compress(body.encode("utf-8"), 9)


def decompress(blob: bytes) -> str:
    return zlib.decompress(blob).decode("utf-8")


def insert_raw(conn, api, lawd_cd, deal_ymd, page_no, fetched_at, result_code, total_count, body: str) -> bool:
    """원문 저장. 직전 동일 페이지와 내용이 같으면 body=NULL로 이력만 남긴다. 새 원문이면 True."""
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    prev = conn.execute(
        "SELECT body_sha256 FROM raw_response WHERE api=? AND lawd_cd=? AND deal_ymd=? AND page_no=? "
        "ORDER BY id DESC LIMIT 1",
        (api, lawd_cd, deal_ymd, page_no),
    ).fetchone()
    changed = prev is None or prev[0] != digest
    conn.execute(
        "INSERT INTO raw_response (api, lawd_cd, deal_ymd, page_no, fetched_at, result_code, total_count, "
        "body_sha256, body) VALUES (?,?,?,?,?,?,?,?,?)",
        (api, lawd_cd, deal_ymd, page_no, fetched_at, result_code, total_count, digest,
         compress(body) if changed else None),
    )
    return changed


def raw_body(conn, raw_id: int) -> str | None:
    """body가 NULL이면 같은 해시의 원문을 찾아 반환."""
    row = conn.execute("SELECT body, body_sha256 FROM raw_response WHERE id=?", (raw_id,)).fetchone()
    if row is None:
        return None
    if row["body"] is not None:
        return decompress(row["body"])
    src = conn.execute(
        "SELECT body FROM raw_response WHERE body_sha256=? AND body IS NOT NULL LIMIT 1", (row["body_sha256"],)
    ).fetchone()
    return decompress(src[0]) if src else None


def set_fetch_log(conn, api, lawd_cd, deal_ymd, status, total_count, row_count, fetched_at, error=None) -> None:
    conn.execute(
        "INSERT INTO fetch_log (api, lawd_cd, deal_ymd, status, total_count, row_count, fetched_at, error) "
        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(api, lawd_cd, deal_ymd) DO UPDATE SET "
        "status=excluded.status, total_count=excluded.total_count, row_count=excluded.row_count, "
        "fetched_at=excluded.fetched_at, error=excluded.error",
        (api, lawd_cd, deal_ymd, status, total_count, row_count, fetched_at, error),
    )


def fetch_status(conn, api, lawd_cd, deal_ymd) -> str | None:
    row = conn.execute(
        "SELECT status FROM fetch_log WHERE api=? AND lawd_cd=? AND deal_ymd=?", (api, lawd_cd, deal_ymd)
    ).fetchone()
    return row[0] if row else None


# ───── 거래 UPSERT ─────

def upsert_rows(conn, table: str, rows: list[dict], seen_at: str) -> tuple[int, int]:
    """(신규, 갱신) 건수. 키가 같으면 해제 여부 등 나머지 컬럼과 last_seen_at 갱신."""
    if not rows:
        return 0, 0
    keys = TABLE_KEYS[table]
    cols = list(rows[0].keys())
    upd = [c for c in cols if c not in keys]
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}, first_seen_at, last_seen_at) "
        f"VALUES ({', '.join('?' * len(cols))}, ?, ?) "
        f"ON CONFLICT({', '.join(keys)}) DO UPDATE SET "
        + ", ".join(f"{c}=excluded.{c}" for c in upd)
        + ", last_seen_at=excluded.last_seen_at"
    )
    before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.executemany(sql, [[r[c] for c in cols] + [seen_at, seen_at] for r in rows])
    after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    new = after - before
    return new, len(rows) - new


# ───── 설정 동기화 ─────

def sync_size_bands(conn, bands: list[dict]) -> None:
    conn.execute("DELETE FROM size_band")
    conn.executemany(
        "INSERT INTO size_band (band, min_ar, max_ar) VALUES (?,?,?)",
        [(str(b["band"]), float(b["min"]), float(b["max"])) for b in bands],
    )


def sync_complexes(conn, complexes: list[dict]) -> None:
    """complexes.yaml → complex, complex_key (전체 교체)."""
    conn.execute("DELETE FROM complex_key")
    conn.execute("DELETE FROM complex")
    for c in complexes:
        conn.execute(
            "INSERT INTO complex (complex_id, name, sgg_cd, umd_nm, target_bands) VALUES (?,?,?,?,?)",
            (c["id"], c["name"], str(c["sgg_cd"]), c["umd_nm"], ",".join(str(b) for b in c.get("bands", []))),
        )
        for seq in c.get("apt_seq", []) or []:
            conn.execute("INSERT INTO complex_key (complex_id, apt_seq) VALUES (?,?)", (c["id"], str(seq)))
        for fb in c.get("fallback", []) or []:
            conn.execute(
                "INSERT INTO complex_key (complex_id, umd_nm, jibun, apt_nm) VALUES (?,?,?,?)",
                (c["id"], fb.get("umd_nm", c["umd_nm"]), str(fb["jibun"]), fb["apt_nm"]),
            )


def sync_config(conn, settings: dict, complexes: list[dict]) -> None:
    sync_size_bands(conn, settings.get("size_bands", []))
    sync_complexes(conn, complexes)
    conn.commit()
