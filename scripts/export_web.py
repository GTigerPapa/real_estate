"""web/data/app.json 생성 (모바일 웹앱 데이터).

    python scripts/export_web.py

저장소의 DB를 임시 사본으로 열어 data/listings/raw/ 의 네이버 덤프를 적재한 뒤 내보낸다
(원본 DB 파일은 건드리지 않음). GitHub Actions(.github/workflows/update.yml)가 매일·덤프 push 때 실행.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from realestate import config, db, listings, webexport  # noqa: E402

OUT = ROOT / "web" / "data" / "app.json"


def main() -> int:
    settings = config.load_settings()
    complexes = config.load_complexes()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "work.db"
        shutil.copy2(config.db_path(), work)
        conn = db.connect(work)
        db.init_db(conn)
        db.sync_config(conn, settings, complexes)
        loaded = [r for _, r in listings.ingest_dir(conn, ROOT / "data" / "listings" / "raw") if r.get("loaded")]
        payload = webexport.build_payload(conn, settings, complexes)
        conn.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else None
    # generated_at 만 다른 경우는 파일을 바꾸지 않음 (불필요한 커밋·배포 방지)
    def strip(t):
        d = json.loads(t)
        d.pop("generated_at", None)
        return d
    if old is not None and strip(old) == strip(text):
        print(f"변경 없음: {OUT.relative_to(ROOT)}")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"저장: {OUT.relative_to(ROOT)} ({len(text.encode()):,} bytes) · 실거래 {payload['data_through']} · "
          f"매물 {payload['listing_through']} · 덤프 적재 {len(loaded)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
