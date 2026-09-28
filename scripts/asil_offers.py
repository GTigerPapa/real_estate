"""아실 매물 목록 수집 → data/listings/asil/asil_offers.csv (국내 PC 전용: 아실 매물 서버가 해외 접속을 끊음)

    python3 scripts/asil_offers.py             # 수집만
    python3 scripts/asil_offers.py --commit    # 수집 후 git pull --rebase → 커밋 → push (Mac launchd 가 매일 실행)

단지 목록은 config/complexes.yaml 의 asil_id (아실 단지 번호, 네이버 번호와 다름).
단지당 20건씩 끝까지(보통 3~12회) 요청, 요청 간 1.5초. push 되면 GitHub Actions 가 웹앱 데이터를 다시 만든다.
등록: python3 scripts/install_asil_offers.py
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from realestate import asil_offers, config  # noqa: E402

OUT = ROOT / "data" / "listings" / "asil" / "asil_offers.csv"
REL = str(OUT.relative_to(ROOT))


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="아실 매물 목록 수집")
    ap.add_argument("--commit", action="store_true", help="수집 결과를 커밋하고 push")
    a = ap.parse_args(argv)
    now = datetime.now(config.KST)
    today = now.strftime("%Y-%m-%d")
    print(f"[{now:%Y-%m-%d %H:%M}] 아실 매물 목록 수집")

    if a.commit:  # 먼저 최신을 받아 두어야 Actions 가 만든 커밋과 충돌하지 않는다
        r = git("pull", "--rebase", "--autostash", "-q", check=False)
        if r.returncode:
            print(f"git pull 실패: {(r.stderr or r.stdout).strip()}")
            return 1

    failed = asil_offers.collect(config.load_complexes(), OUT, today)
    print(f"저장: {REL}")

    if a.commit:
        git("add", REL)
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            print("변경 없음")
        else:
            git("commit", "-q", "-m", f"아실 매물 목록 {now:%Y-%m-%d %H:%M} KST")
            for _ in range(3):
                if git("push", "-q", check=False).returncode == 0:
                    print("push 완료")
                    break
                git("pull", "--rebase", "-q", check=False)
            else:
                print("push 실패 — 나중에 git push 를 실행하세요")
                return 1
    if failed:
        print(f"실패 단지: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
