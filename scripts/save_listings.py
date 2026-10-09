"""북마클릿이 내려받은 naver_listings_*.json 을 저장소에 넣고 커밋·push (Mac, Python 3.9 이상).

    python3 scripts/save_listings.py               # ~/Downloads 에서 가장 최근 파일
    python3 scripts/save_listings.py 파일경로       # 특정 파일
    python3 scripts/save_listings.py --no-push      # 커밋만

- 파일 형식을 검사하고 data/listings/raw/ 로 옮긴 뒤, 로컬 DB(data/realestate.db)에도 적재해 요약을 보여준다.
- 커밋 대상은 raw JSON 파일뿐이다 (DB 파일은 커밋하지 않음 → 다른 곳에서 갱신되는 DB와 충돌 없음).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import json  # noqa: E402

from realestate import listings, naver_offers  # noqa: E402

RAW_DIR = ROOT / "data" / "listings" / "raw"
NAVER_CSV = ROOT / "data" / "listings" / "naver" / "naver_offers.csv"
DOWNLOADS = Path.home() / "Downloads"


def newest_download() -> Path | None:
    files = sorted(DOWNLOADS.glob("naver_listings_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main(argv: list) -> int:
    push = "--no-push" not in argv
    args = [a for a in argv if not a.startswith("--")]
    src = Path(args[0]).expanduser() if args else newest_download()
    if src is None or not src.exists():
        print(f"덤프 파일이 없습니다. {DOWNLOADS} 에 naver_listings_*.json 이 있는지 확인하세요.")
        return 1
    try:
        d = listings.load_dump(src)
    except listings.DumpError as e:
        print(f"형식 오류: {e}")
        return 1
    name = src.name.replace(" ", "").replace("(", "_").replace(")", "")   # 'naver_listings_..(1).json' 같은 이름 정리
    dst = RAW_DIR / name
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    # 매물 목록(articles)은 추적 CSV로 옮기고, 원본 덤프에서는 빼서 저장 (저장소 용량)
    if naver_offers.has_articles(d):
        print("── 네이버 매물 목록")
        naver_offers.update(NAVER_CSV, d)
    text = json.dumps(naver_offers.strip_articles(d), ensure_ascii=False, separators=(",", ":"))
    if dst.exists() and dst.read_text(encoding="utf-8") == text:
        print(f"이미 저장된 파일입니다: {dst.name}")
    else:
        dst.write_text(text, encoding="utf-8")
        print(f"저장: data/listings/raw/{dst.name}  (수집 시각 {d['captured_at']})")

    ok = sum(1 for c in d["complexes"] for r in c.get("responses", []) if r.get("ok"))
    fail = sum(1 for c in d["complexes"] for r in c.get("responses", []) if not r.get("ok"))
    print(f"응답 성공 {ok} / 실패 {fail} · 단지 {len(d['complexes'])}개")
    if fail and not ok:
        print("⚠ 모든 응답이 실패했습니다. 네이버페이 부동산 페이지를 새로고침한 뒤 북마클릿을 다시 눌러 보세요.")

    db_file = ROOT / "data" / "realestate.db"
    if db_file.exists():
        try:
            from realestate import db
            conn = db.connect(db_file)
            db.init_db(conn)
            r = listings.ingest_file(conn, dst)
            conn.close()
            if r["loaded"]:
                print(f"로컬 DB 적재: {r['snap_date']} 숫자 값 {r['metrics']:,}개")
        except Exception as e:  # noqa: BLE001 — DB 적재는 부가 기능, 실패해도 파일 커밋은 진행
            print(f"(로컬 DB 적재 건너뜀: {type(e).__name__}: {e})")

    paths = [str(dst.relative_to(ROOT))] + ([str(NAVER_CSV.relative_to(ROOT))] if NAVER_CSV.exists() else [])
    git("add", *paths)
    if not git("status", "--porcelain", "--", *paths):
        print("커밋할 변경이 없습니다.")
        return 0
    git("commit", "-q", "-m", f"네이버 매물 덤프 {d['captured_at'][:16]}")
    print("커밋 완료" + (", push 중..." if push else ""))
    if push:
        try:
            for attempt in range(3):   # 그사이 Actions 가 먼저 올렸으면 받아서 다시 push
                try:
                    git("push")
                    break
                except subprocess.CalledProcessError:
                    if attempt == 2:
                        raise
                    git("pull", "--rebase", "--autostash", "-q")
            print("push 완료")
        except subprocess.CalledProcessError as e:
            print(f"push 실패:\n{e.stderr.strip()}\n나중에 `git push` 를 다시 실행하세요.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
