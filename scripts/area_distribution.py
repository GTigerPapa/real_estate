"""관심 단지별 전용면적 분포 (평형 구간 경계 확정용).

    python scripts/area_distribution.py            # 매매
    python scripts/area_distribution.py --rent     # 전월세
"""
import argparse

from realestate import config, db

SQL = """
SELECT c.name, t.exclu_use_ar AS ar, COUNT(*) AS n, SUM(t.is_canceled) AS canceled,
       MIN(t.deal_amount) AS min_amt, MAX(t.deal_amount) AS max_amt
FROM {table} t
JOIN {match} m ON m.{id_col} = t.id
JOIN complex c ON c.complex_id = m.complex_id
GROUP BY c.name, t.exclu_use_ar
ORDER BY c.name, t.exclu_use_ar
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rent", action="store_true")
    ap.add_argument("--db", default=str(config.db_path()))
    a = ap.parse_args()

    conn = db.connect(a.db)
    db.init_db(conn)
    db.sync_config(conn, config.load_settings(), config.load_complexes())
    if a.rent:
        sql = SQL.replace("SUM(t.is_canceled)", "0").replace("t.deal_amount", "t.deposit")
        rows = conn.execute(sql.format(table="apt_rent", match="v_rent_match", id_col="rent_id")).fetchall()
    else:
        rows = conn.execute(SQL.format(table="apt_trade", match="v_trade_match", id_col="trade_id")).fetchall()
    bands = conn.execute("SELECT band, min_ar, max_ar FROM size_band").fetchall()

    def band_of(ar):
        return next((b[0] for b in bands if b[1] <= ar < b[2]), "-")

    print("| 단지 | 전용㎡ | 건수 | 해제 | 금액 범위(만원) | 현 구간 |")
    print("|---|---:|---:|---:|---|---|")
    for r in rows:
        print(f"| {r['name']} | {r['ar']:.2f} | {r['n']} | {r['canceled']} | "
              f"{r['min_amt']:,}~{r['max_amt']:,} | {band_of(r['ar'])} |")


if __name__ == "__main__":
    main()
