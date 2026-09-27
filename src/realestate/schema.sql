-- 실거래 추적 DB 스키마 (SQLite). 모든 문장은 멱등(IF NOT EXISTS).

-- API 원문 응답. 재수집 이력 보존. 요청 URL(키 포함)은 저장하지 않는다.
-- body: zlib 압축 XML. 같은 (api, lawd_cd, deal_ymd, page_no)의 직전 원문과 해시가 같으면 NULL(중복 저장 방지).
CREATE TABLE IF NOT EXISTS raw_response (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    api          TEXT    NOT NULL,             -- 'trade' | 'rent'
    lawd_cd      TEXT    NOT NULL,
    deal_ymd     TEXT    NOT NULL,             -- YYYYMM
    page_no      INTEGER NOT NULL,
    fetched_at   TEXT    NOT NULL,             -- ISO8601 (KST)
    result_code  TEXT,
    total_count  INTEGER,
    body_sha256  TEXT    NOT NULL,
    body         BLOB
);
CREATE INDEX IF NOT EXISTS ix_raw_response_key
    ON raw_response (api, lawd_cd, deal_ymd, page_no, id);

-- 월 단위 수집 상태. 완료(ok)된 월은 건너뛰되 최근 N개월은 매번 재수집.
CREATE TABLE IF NOT EXISTS fetch_log (
    api          TEXT    NOT NULL,
    lawd_cd      TEXT    NOT NULL,
    deal_ymd     TEXT    NOT NULL,
    status       TEXT    NOT NULL,             -- 'ok' | 'error'
    total_count  INTEGER,
    row_count    INTEGER,
    fetched_at   TEXT    NOT NULL,
    error        TEXT,
    PRIMARY KEY (api, lawd_cd, deal_ymd)
);

-- 매매 실거래 (시군구 전체). 키 텍스트 컬럼은 NULL 대신 '' (UNIQUE 동작 보장).
CREATE TABLE IF NOT EXISTS apt_trade (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sgg_cd        TEXT    NOT NULL,
    umd_cd        TEXT,
    umd_nm        TEXT,
    jibun         TEXT,
    apt_seq       TEXT    NOT NULL DEFAULT '',
    apt_nm        TEXT,
    apt_dong      TEXT    NOT NULL DEFAULT '',
    deal_date     TEXT    NOT NULL,            -- YYYY-MM-DD
    exclu_use_ar  REAL    NOT NULL,
    floor         INTEGER NOT NULL,
    deal_amount   INTEGER NOT NULL,            -- 만원
    dealing_gbn   TEXT,                        -- 중개거래 | 직거래
    is_canceled   INTEGER NOT NULL DEFAULT 0,
    cancel_date   TEXT,
    rgst_date     TEXT,
    buyer_gbn     TEXT,
    sler_gbn      TEXT,
    agent_sgg_nm  TEXT,
    build_year    INTEGER,
    dup_seq       INTEGER NOT NULL DEFAULT 1,  -- 같은 월 응답 내 완전 동일 조건 건의 순번
    first_seen_at TEXT    NOT NULL,
    last_seen_at  TEXT    NOT NULL,
    UNIQUE (sgg_cd, apt_seq, deal_date, exclu_use_ar, floor, deal_amount, apt_dong, dup_seq)
);
CREATE INDEX IF NOT EXISTS ix_apt_trade_apt ON apt_trade (apt_seq, deal_date);
CREATE INDEX IF NOT EXISTS ix_apt_trade_loc ON apt_trade (sgg_cd, umd_nm, jibun);

-- 전월세 실거래 (시군구 전체).
CREATE TABLE IF NOT EXISTS apt_rent (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    sgg_cd           TEXT    NOT NULL,
    umd_cd           TEXT,
    umd_nm           TEXT,
    jibun            TEXT,
    apt_seq          TEXT    NOT NULL DEFAULT '',
    apt_nm           TEXT,
    deal_date        TEXT    NOT NULL,
    exclu_use_ar     REAL    NOT NULL,
    floor            INTEGER NOT NULL,
    deposit          INTEGER NOT NULL,         -- 만원
    monthly_rent     INTEGER NOT NULL,         -- 만원
    rent_type        TEXT    NOT NULL,         -- 전세 | 월세
    contract_term    TEXT    NOT NULL DEFAULT '',
    contract_type    TEXT,                     -- 신규 | 갱신
    use_rr_right     TEXT,                     -- 갱신요구권 사용 여부
    pre_deposit      INTEGER,
    pre_monthly_rent INTEGER,
    build_year       INTEGER,
    dup_seq          INTEGER NOT NULL DEFAULT 1,
    first_seen_at    TEXT    NOT NULL,
    last_seen_at     TEXT    NOT NULL,
    UNIQUE (sgg_cd, apt_seq, deal_date, exclu_use_ar, floor, deposit, monthly_rent, contract_term, dup_seq)
);
CREATE INDEX IF NOT EXISTS ix_apt_rent_apt ON apt_rent (apt_seq, deal_date);
CREATE INDEX IF NOT EXISTS ix_apt_rent_loc ON apt_rent (sgg_cd, umd_nm, jibun);

-- 관심 단지 (config/complexes.yaml에서 동기화)
CREATE TABLE IF NOT EXISTS complex (
    complex_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,                -- 표시명
    sgg_cd       TEXT NOT NULL,
    umd_nm       TEXT NOT NULL,
    target_bands TEXT                          -- 쉼표 구분, 예: '59,74,84'
);
-- 매칭 키: apt_seq 우선, 보조로 (umd_nm, jibun, apt_nm)
CREATE TABLE IF NOT EXISTS complex_key (
    complex_id TEXT NOT NULL REFERENCES complex (complex_id) ON DELETE CASCADE,
    apt_seq    TEXT,
    umd_nm     TEXT,
    jibun      TEXT,
    apt_nm     TEXT
);

-- 평형 구간 (config/settings.yaml에서 동기화). [min_ar, max_ar)
CREATE TABLE IF NOT EXISTS size_band (
    band   TEXT PRIMARY KEY,
    min_ar REAL NOT NULL,
    max_ar REAL NOT NULL
);

DROP VIEW IF EXISTS v_trade_match;
CREATE VIEW v_trade_match AS
SELECT DISTINCT t.id AS trade_id, k.complex_id
FROM apt_trade t
JOIN complex c      ON c.sgg_cd = t.sgg_cd
JOIN complex_key k  ON k.complex_id = c.complex_id
WHERE (k.apt_seq IS NOT NULL AND k.apt_seq = t.apt_seq)
   OR (k.apt_seq IS NULL AND k.umd_nm = t.umd_nm AND k.jibun = t.jibun AND k.apt_nm = t.apt_nm);

DROP VIEW IF EXISTS v_rent_match;
CREATE VIEW v_rent_match AS
SELECT DISTINCT r.id AS rent_id, k.complex_id
FROM apt_rent r
JOIN complex c      ON c.sgg_cd = r.sgg_cd
JOIN complex_key k  ON k.complex_id = c.complex_id
WHERE (k.apt_seq IS NOT NULL AND k.apt_seq = r.apt_seq)
   OR (k.apt_seq IS NULL AND k.umd_nm = r.umd_nm AND k.jibun = r.jibun AND k.apt_nm = r.apt_nm);

-- 관심 단지 거래 + 평형 구간 (구간 밖 면적은 size_band NULL)
DROP VIEW IF EXISTS v_trade;
CREATE VIEW v_trade AS
SELECT t.*, c.complex_id, c.name AS complex_name, b.band AS size_band,
       substr(t.deal_date, 1, 7) AS deal_ym
FROM apt_trade t
JOIN v_trade_match m ON m.trade_id = t.id
JOIN complex c       ON c.complex_id = m.complex_id
LEFT JOIN size_band b ON t.exclu_use_ar >= b.min_ar AND t.exclu_use_ar < b.max_ar;

DROP VIEW IF EXISTS v_rent;
CREATE VIEW v_rent AS
SELECT r.*, c.complex_id, c.name AS complex_name, b.band AS size_band,
       substr(r.deal_date, 1, 7) AS deal_ym
FROM apt_rent r
JOIN v_rent_match m  ON m.rent_id = r.id
JOIN complex c       ON c.complex_id = m.complex_id
LEFT JOIN size_band b ON r.exclu_use_ar >= b.min_ar AND r.exclu_use_ar < b.max_ar;

-- ───── 2~4단계 설계 (아직 미사용) ─────
-- listing_snapshot(snap_date, complex_id, size_band, listing_count, min_ask, jeonse_listing_count, source,
--                  PRIMARY KEY(snap_date, complex_id, size_band, source))
-- interest_rate(date, series_code, value, PRIMARY KEY(date, series_code))
-- news_summary(url UNIQUE, published_at, title, summary, complex_id NULL, tags, model)
-- report_log(report_date, kind, channel, status, sent_at, content_hash, payload)
