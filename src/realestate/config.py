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
    except ImportError:
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


def db_path() -> Path:
    return Path(os.environ.get("REALESTATE_DB", DEFAULT_DB))


def now_kst() -> datetime:
    return datetime.now(KST)


def now_iso() -> str:
    return now_kst().isoformat(timespec="seconds")
