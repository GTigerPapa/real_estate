"""설정 로드: config/settings.yaml, config/complexes.yaml, .env."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DEFAULT_DB = DATA_DIR / "realestate.db"
KST = ZoneInfo("Asia/Seoul")


def load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv 없이도 .env 의 KEY=VALUE 줄은 읽는다 (Mac launchd 실행 등)
        p = ROOT / ".env"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        return
    load_dotenv(ROOT / ".env", override=False)


def load_settings(path: Path | None = None) -> dict:
    with open(path or CONFIG_DIR / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_complexes(path: Path | None = None) -> list[dict]:
    """complexes.yaml이 아직 없으면 빈 목록."""
    p = path or CONFIG_DIR / "complexes.yaml"
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("complexes", [])


def naver_parts(c: dict) -> list[tuple[int, str]]:
    """단지의 네이버 단지 번호 목록 [(번호, 구분 이름)].
    여러 단지를 한 단지로 묶은 경우(예: 장미마을 동부+코오롱) complexes.yaml 의 naver_parts 를 쓰고,
    아니면 naver_id 하나 (구분 이름은 빈 문자열)."""
    parts = c.get("naver_parts")
    if parts:
        return [(int(p["naver_id"]), str(p.get("label") or "")) for p in parts]
    return [(int(c["naver_id"]), "")] if c.get("naver_id") else []


def db_path() -> Path:
    return Path(os.environ.get("REALESTATE_DB", DEFAULT_DB))


def now_kst() -> datetime:
    return datetime.now(KST)


def now_iso() -> str:
    return now_kst().isoformat(timespec="seconds")
