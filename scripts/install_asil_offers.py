"""아실 매물 목록 수집(scripts/asil_offers.py --commit)을 Mac launchd 에 등록/해제.

    python3 scripts/install_asil_offers.py                # 매일 07:13 (Mac 시간대 기준)
    python3 scripts/install_asil_offers.py --time 20:47   # 시각 변경
    python3 scripts/install_asil_offers.py --status       # 등록 상태·최근 로그
    python3 scripts/install_asil_offers.py --uninstall    # 해제
    python3 scripts/install_asil_offers.py --run-now      # 등록된 작업을 지금 한 번 실행

- 정한 시각에 Mac이 잠자고 있었다면 깨어난 직후 한 번 실행된다. 전원이 꺼져 있던 날은 건너뛴다.
- push 는 이 Mac의 git 인증(키체인)을 쓴다. 터미널에서 git push 가 되면 된다.
- 로그: ~/Library/Logs/real_estate/asil_offers.log
"""
from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = "com.gtigerpapa.realestate.asil-offers"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = Path.home() / "Library" / "Logs" / "real_estate" / "asil_offers.log"


def domain() -> str:
    return f"gui/{os.getuid()}"


def launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def install(hour: int, minute: int) -> int:
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    launchctl("bootout", domain(), str(PLIST))
    with PLIST.open("wb") as f:
        plistlib.dump({
            "Label": LABEL,
            "ProgramArguments": [sys.executable, str(ROOT / "scripts" / "asil_offers.py"), "--commit"],
            "WorkingDirectory": str(ROOT),
            "StartCalendarInterval": {"Hour": hour, "Minute": minute},
            "StandardOutPath": str(LOG), "StandardErrorPath": str(LOG),
            "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                                     "PYTHONUNBUFFERED": "1", "LANG": "ko_KR.UTF-8"},
        }, f)
    r = launchctl("bootstrap", domain(), str(PLIST))
    if r.returncode:
        print(f"등록 실패: {(r.stderr or r.stdout).strip()}")
        return 1
    print(f"등록 완료: 매일 {hour:02d}:{minute:02d} · 로그 {LOG}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="아실 매물 목록 수집 launchd 등록")
    ap.add_argument("--time", default="07:13")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--uninstall", action="store_true")
    g.add_argument("--status", action="store_true")
    g.add_argument("--run-now", action="store_true")
    a = ap.parse_args(argv)
    if sys.platform != "darwin":
        print("Mac 전용입니다.")
        return 1
    if a.uninstall:
        launchctl("bootout", domain(), str(PLIST))
        PLIST.unlink(missing_ok=True)
        print("해제 완료")
        return 0
    if a.run_now:
        r = launchctl("kickstart", "-p", f"{domain()}/{LABEL}")
        print("실행 시작 — 로그: " + str(LOG) if r.returncode == 0 else f"실행 실패: {(r.stderr or r.stdout).strip()}")
        return r.returncode
    if a.status:
        r = launchctl("print", f"{domain()}/{LABEL}")
        print("등록됨" if r.returncode == 0 else "등록 안 됨")
        for line in r.stdout.splitlines():
            if line.strip().startswith(("state =", "last exit code", "runs =")):
                print("  " + line.strip())
        if LOG.exists():
            print("\n최근 로그:\n" + "\n".join(LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]))
        return 0
    hh, mm = (int(x) for x in a.time.split(":"))
    return install(hh, mm)


if __name__ == "__main__":
    sys.exit(main())
