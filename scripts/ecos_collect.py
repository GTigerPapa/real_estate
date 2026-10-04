"""한국은행 ECOS 월별 지표 수집 → data/macro/ecos_monthly.csv (GitHub Actions 가 매일 실행, 키 = ECOS_KEY)."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from realestate import config, ecos  # noqa: E402

OUT = ROOT / "data" / "macro" / "ecos_monthly.csv"


def main() -> int:
    config.load_dotenv_if_present()
    cfg = config.load_settings().get("ecos") or {}
    series = cfg.get("series") or []
    end = datetime.now(config.KST).strftime("%Y%m")
    print(f"ECOS 지표 {len(series)}개 · {cfg.get('start')}~{end}")
    try:
        failed = ecos.collect(series, OUT, str(cfg.get("start", "201301")), end)
    except ecos.EcosError as e:
        print(e)
        return 1
    print(f"저장: {OUT.relative_to(ROOT)}" + (f" · 실패 {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
