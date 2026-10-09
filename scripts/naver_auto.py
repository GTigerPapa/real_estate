"""네이버 매물 자동 수집 (iMac): 사용자의 크롬을 AppleScript로 조종해 북마클릿과 같은 코드를 실행한다.

    python3 scripts/naver_auto.py            # 수집 → 저장소 반영(save_listings) → 커밋 (push 안 함)
    python3 scripts/naver_auto.py --push     # 커밋 후 push 까지

- 네이버페이 부동산은 자동화 브라우저·서버 요청을 막는다. 그래서 평소 쓰는 크롬 창 하나를 열어
  fin.land.naver.com 에서 북마클릿 코드(tools/bookmarklet.txt)를 실행하고, 결과를 페이지에서 직접 읽어
  (예약 작업은 macOS가 다운로드 폴더 접근을 막으므로) 처리한 뒤 창을 닫는다.
- 처음 한 번 필요한 설정:
  1) 크롬 메뉴 보기 → 개발자 정보 → 'Apple Events의 자바스크립트 허용' 체크
  2) 처음 실행 때 macOS가 '…이(가) Google Chrome을 제어하려고 합니다' 를 물으면 '허용'
- 요청 간격은 북마클릿과 같게 0.4초, 하루 한 번(mac_daily)만 돈다.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://fin.land.naver.com/"
TIMEOUT = 15 * 60


class AutoError(RuntimeError):
    pass


def osa(script: str, timeout: float = 60, raw: bool = False) -> str:
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        err = (p.stderr or p.stdout).strip()
        if "JavaScript" in err or "자바스크립트" in err or "-1743" in err or "not allowed" in err.lower():
            raise AutoError("크롬 설정 필요: 보기 → 개발자 정보 → 'Apple Events의 자바스크립트 허용' 체크, "
                            "macOS 제어 허용 창이 뜨면 '허용' (" + err[:160] + ")")
        raise AutoError(err[:300])
    if raw:   # 결과 조각: 앞뒤 공백도 데이터이므로 osascript가 붙인 마지막 줄바꿈만 뗀다
        return p.stdout[:-1] if p.stdout.endswith("\n") else p.stdout
    return p.stdout.strip()


def collect(log=print) -> Path:
    if sys.platform != "darwin":
        raise AutoError("macOS 에서만 실행")
    js = (ROOT / "tools" / "bookmarklet.txt").read_text(encoding="utf-8").strip()
    js = "window.__RE_AUTO=true;window.__RE_DONE=undefined;" + js.removeprefix("javascript:")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
        js_path = f.name
    started = time.time()
    # 새 창을 열어 네이버 부동산으로 → 로딩 대기
    win = osa(f'''tell application "Google Chrome"
  set w to make new window
  set URL of active tab of w to "{URL}"
  return id of w
end tell''')
    tab = f'active tab of (first window whose id is {win})'
    try:
        for _ in range(60):
            time.sleep(1)
            if osa(f'tell application "Google Chrome" to return loading of {tab}') == "false":
                break
        time.sleep(4)
        osa(f'''set js to read (POSIX file "{js_path}") as «class utf8»
tell application "Google Chrome" to execute {tab} javascript js''')
        log("크롬에서 수집 시작")
        name = ""
        while time.time() - started < TIMEOUT:
            time.sleep(10)
            name = osa(f'tell application "Google Chrome" to execute {tab} javascript "String(window.__RE_DONE || \'\')"')
            if name:
                break
        if not name:
            raise AutoError("시간 초과 (15분)")
        if not name.startswith("naver_listings_"):
            raise AutoError(f"수집 실패: {name}")
        # 결과 JSON 을 페이지에서 조각조각 읽어 임시 파일로 (예약 작업은 macOS가 다운로드 폴더 접근을 막음)
        n = int(osa(f'tell application "Google Chrome" to execute {tab} javascript "String((window.__RE_JSON || \'\').length)"') or 0)
        if not n:
            raise AutoError("수집 결과가 비어 있음")
        parts, step = [], 400_000
        for i in range(0, n, step):
            parts.append(osa(f'tell application "Google Chrome" to execute {tab} javascript '
                             f'"window.__RE_JSON.substring({i}, {i + step})"', timeout=120, raw=True))
        text = "".join(parts)
        try:
            json.loads(text)
        except ValueError:
            raise AutoError(f"결과를 온전히 읽지 못함 ({len(text):,}/{n:,}자)") from None
        out = Path(tempfile.gettempdir()) / name
        out.write_text(text, encoding="utf-8")
        log(f"수집 완료: {name} ({n:,}자, {int(time.time() - started)}초)")
        return out
    finally:
        try:
            osa(f'tell application "Google Chrome" to close (first window whose id is {win})')
        except AutoError:
            pass
        Path(js_path).unlink(missing_ok=True)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        path = collect()
    except (AutoError, subprocess.TimeoutExpired) as e:
        print(f"네이버 자동 수집 실패: {e}")
        return 1
    sys.path.insert(0, str(ROOT / "scripts"))
    import save_listings  # noqa: E402
    return save_listings.main([str(path)] + ([] if "--push" in argv else ["--no-push"]))


if __name__ == "__main__":
    sys.exit(main())
