"""법정동별 고유 단지명·aptSeq 목록 (complexes.yaml 매칭 후보 확인용).

    python scripts/list_complex_names.py --umd 상일동 여수동
    python scripts/list_complex_names.py --sgg 41450 --like 더샵
"""
import argparse
import sqlite3

from realestate import config

SQL = """
SELECT sgg_cd, umd_nm, apt_seq, apt_nm, jibun, build_year,
       COUNT(*) AS n, SUM(is_canceled) AS canceled,
       MIN(exclu_use_ar) AS min_ar, MAX(exclu_use_ar) AS max_ar,
       MIN(deal_date) AS first_deal, MAX(deal_date) AS last_deal
FROM apt_trade
WHERE {where}
GROUP BY sgg_cd, umd_nm, apt_seq, apt_nm, jibun, build_year
ORDER BY sgg_cd, umd_nm, apt_nm, apt_seq
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--umd", nargs="*", default=[])
    ap.add_argument("--sgg", nargs="*", default=[])
    ap.add_argument("--like", nargs="*", default=[], help="단지명 부분 일치 (OR)")
    ap.add_argument("--db", default=str(config.db_path()))
    a = ap.parse_args()

    conds, params = [], []
    if a.umd:
        conds.append(f"umd_nm IN ({','.join('?' * len(a.umd))})"); params += a.umd
    if a.sgg:
        conds.append(f"sgg_cd IN ({','.join('?' * len(a.sgg))})"); params += a.sgg
    if a.like:
        conds.append("(" + " OR ".join("apt_nm LIKE ?" for _ in a.like) + ")"); params += [f"%{s}%" for s in a.like]
    conn = sqlite3.connect(a.db)
    rows = conn.execute(SQL.format(where=" AND ".join(conds) or "1=1"), params).fetchall()
    print("| sgg | 법정동 | aptSeq | 단지명 | 지번 | 준공 | 거래 | 해제 | 전용㎡ 범위 | 기간 |")
    print("|---|---|---|---|---|---|---:|---:|---|---|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} | "
              f"{r[8]:.2f}~{r[9]:.2f} | {r[10][:7]}~{r[11][:7]} |")


if __name__ == "__main__":
    main()
