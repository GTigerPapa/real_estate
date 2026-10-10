"""Mac 매일 작업: 실거래 수집 → 아실 매물 목록 → 웹앱 데이터 → 커밋·push.

    python3 scripts/mac_daily.py              # launchd 가 매일 실행 (scripts/install_asil_offers.py 로 등록)
    python3 scripts/mac_daily.py --no-push    # 커밋·push 없이 수집·내보내기만

공공데이터포털(실거래)과 아실 매물 서버는 해외 IP를 막아 GitHub Actions(미국)에서는 받을 수 없다.
그래서 국내 Mac 이 매일 받는다.

- 실거래: python -m realestate.ingest (최근 3개월 재수집 + 빠진 달·새 시군구 백필). 키는 .env 의 DATA_GO_KR_KEY.
- 웹앱 데이터(web/data/app.json)는 Mac 이 새 DB로 만들어 커밋한다. DB(45MB)는 매월 1일·대량 백필 날만 커밋
  (저장소 용량 관리). Actions 가 저장소의 오래된 DB로 다시 내보내도 실거래 부분은 이 파일이 더 새 것이라 유지된다.
- 웹앱 데이터를 못 만들면(pandas 없음 등) 대신 DB를 커밋해 Actions 가 만들게 한다.
- 한 단계가 실패해도 나머지는 진행하고, 마지막에 종료 코드 1.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from realestate import asil_offers, config  # noqa: E402  (둘 다 표준 라이브러리만 사용)

DB_REL = "data/realestate.db"
APP_REL = "web/data/app.json"
OFFERS_REL = "data/listings/asil/asil_offers.csv"
NAVER_REL = "data/listings/naver/naver_offers.csv"
LOG_REL = "data/logs/mac_daily_last.log"   # 마지막 실행 기록 (원격에서 문제 확인용, 키는 로그에 남지 않음)
_LOG: list[str] = []


def say(msg: str = "") -> None:
    print(msg)
    _LOG.append(msg)
BACKFILL_TASKS = 40   # 수집 대상이 이보다 많으면(평소 3개 시군구 이상 × 3개월 × 2 = 24건 안팎) 백필로 보고 DB 커밋


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check)


def run_py(*args: str) -> tuple[int, str]:
    """이 저장소의 src 를 경로에 넣고 파이썬 실행 (pip install -e 없이도 동작). 출력은 그대로 보여 주고 반환."""
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONUNBUFFERED="1")
    p = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    say(out.rstrip())
    return p.returncode, out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mac 매일 작업 (실거래·아실 매물·웹앱 데이터)")
    ap.add_argument("--no-push", action="store_true", help="커밋·push 하지 않음")
    a = ap.parse_args(argv)
    now = datetime.now(config.KST)
    say(f"[{now:%Y-%m-%d %H:%M}] Mac 매일 작업 · python {sys.version.split()[0]} · .env {'있음' if (ROOT / '.env').exists() else '없음'}")
    problems = []

    if not a.no_push:  # 먼저 최신을 받아 두어야 Actions 가 만든 커밋과 충돌하지 않는다
        if (ROOT / ".git" / "rebase-merge").exists() or (ROOT / ".git" / "rebase-apply").exists():
            git("rebase", "--abort", check=False)   # 지난번 push 재시도가 충돌로 멈춰 있으면 풀고 시작
        r = git("pull", "--rebase", "-X", "theirs", "--autostash", "-q", check=False)
        if r.returncode:
            print(f"git pull 실패: {(r.stderr or r.stdout).strip()}")
            return 1

    # 1) 실거래
    say("── 실거래 수집")
    rc, out = run_py("-m", "realestate.ingest")
    m = re.search(r"대상 (\d+)건", out)
    tasks = int(m.group(1)) if m else 0
    if rc:
        problems.append("실거래 수집" + (" (패키지 설치 필요: pip3 install -r requirements.txt)" if "ModuleNotFoundError" in out else ""))

    # 2) 아실 매물 목록
    say("── 아실 매물 목록")
    failed = asil_offers.collect(config.load_complexes(), ROOT / OFFERS_REL, now.strftime("%Y-%m-%d"), log=say)
    if failed:
        problems.append("아실 매물 목록: " + ", ".join(failed))

    # 2-1) 네이버 매물 (크롬 자동 실행, settings.yaml naver_auto: false 면 건너뜀). 실패해도 나머지는 진행·종료 코드에 반영 안 함
    naver_note = "꺼짐"
    try:
        naver_on = bool(config.load_settings().get("naver_auto", True))
    except Exception:  # noqa: BLE001 — 설정을 못 읽으면 기본값(켜짐)
        naver_on = True
    if naver_on and sys.platform == "darwin":
        say("── 네이버 매물 (크롬 자동)")
        rc_nv, out_nv = run_py(str(ROOT / "scripts" / "naver_auto.py"))
        naver_note = "성공" if rc_nv == 0 else "실패"

    # 3) 웹앱 데이터
    say("── 웹앱 데이터")
    rc_web, _ = run_py(str(ROOT / "scripts" / "export_web.py"))
    if rc_web:
        problems.append("웹앱 데이터 생성")

    # DB는 실거래 수집이 성공했을 때만: 백필한 날·매월 1일, 또는 웹앱 데이터를 못 만들어 Actions 가 대신 만들어야 할 때
    commit_db = rc == 0 and (tasks > BACKFILL_TASKS or now.day == 1 or rc_web != 0)
    say(f"요약: 실거래 {'성공' if rc == 0 else '실패'}(대상 {tasks}건) · 매물 실패 {len(failed)}곳 · "
        f"네이버 {naver_note} · 웹앱 {'성공' if rc_web == 0 else '실패'} · DB 커밋 {commit_db}" + (f" · 문제: {' · '.join(problems)}" if problems else ""))
    log_path = ROOT / LOG_REL
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(_LOG)[-20000:] + "\n", encoding="utf-8")
    if a.no_push:
        print(f"커밋 생략 (--no-push) · DB 커밋 대상이었는지: {commit_db}")
    else:
        paths = [APP_REL, OFFERS_REL, LOG_REL] + ([NAVER_REL] if (ROOT / NAVER_REL).exists() else []) + ([DB_REL] if commit_db else [])
        git("add", *paths, check=False)
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            print("변경 없음")
        else:
            what = ("실거래·매물" if rc == 0 else "매물 · 실거래 실패") + (" + DB" if commit_db else "")
            git("commit", "-q", "-m", f"Mac 매일 갱신 {now:%Y-%m-%d %H:%M} KST ({what})")
            for _ in range(3):
                if git("push", "-q", check=False).returncode == 0:
                    print("push 완료" + (" (DB 포함)" if commit_db else ""))
                    break
                # 그사이 Actions 가 app.json 등을 먼저 올렸으면 받아서 다시 push. 생성 파일 충돌은 Mac 쪽(방금 만든 것)을 쓴다
                if git("pull", "--rebase", "-X", "theirs", "--autostash", "-q", check=False).returncode != 0:
                    git("rebase", "--abort", check=False)
            else:
                problems.append("push (나중에 git push 실행)")

    if problems:
        print("문제: " + " · ".join(problems))
        return 1
    print("완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
