"""경기도 신규 시군구 일괄 수집 (store_info · sgis · molit).

이미 DB 에 있는 gangnam, seongnam 은 건너뛴다. 소상공인365(키 없음)·서울골목상권(서울 전용)은 제외.
지역/소스별로 실패해도 다음으로 계속 진행하고, 끝에 요약을 출력한다.
"""
from __future__ import annotations

import sys
import time

from sangkwon import db as db_mod
from sangkwon.collectors.molit import MolitCollector, recent_months
from sangkwon.collectors.sgis import SgisCollector
from sangkwon.collectors.store_info import StoreInfoCollector
from sangkwon.settings import ApiKeys, ensure_dirs, get_region, load_regions

SKIP = {"gangnam", "seongnam"}
MONTHS = 3


def main() -> int:
    ensure_dirs()
    db_mod.init_db()
    keys = ApiKeys.from_env()
    regions = load_regions()
    targets = [k for k in regions if k not in SKIP]
    print(f"대상 {len(targets)}개 시군구: {', '.join(targets)}\n")

    summary = []
    for i, key in enumerate(targets, 1):
        region = get_region(key)
        print(f"━━━ [{i}/{len(targets)}] {region.name} ({key}) ━━━")
        conn = db_mod.connect()
        try:
            collectors = [
                ("store_info", StoreInfoCollector(conn, keys)),
                ("sgis", SgisCollector(conn, keys)),
                ("molit", MolitCollector(conn, keys, deal_yms=recent_months(MONTHS))),
            ]
            for name, col in collectors:
                missing = col.missing_keys()
                if missing:
                    print(f"  · {name}: 키 누락 {missing} → 건너뜀")
                    continue
                t0 = time.time()
                try:
                    res = col.run(region)
                    dt = time.time() - t0
                    print(f"  {('✓' if res.status!='error' else '✗')} {name}: {res.status} · {res.record_count:,}건 · {dt:.1f}s"
                          + (f" · {res.message}" if res.message else ""))
                    summary.append((key, name, res.status, res.record_count))
                except Exception as exc:  # noqa: BLE001
                    print(f"  ✗ {name}: 예외 {str(exc)[:120]}")
                    summary.append((key, name, "exception", 0))
        finally:
            conn.close()
        print()

    print("================ 요약 ================")
    by_src: dict[str, int] = {}
    for key, name, status, cnt in summary:
        by_src[name] = by_src.get(name, 0) + (cnt if status != "error" else 0)
    for name, total in by_src.items():
        print(f"  {name:12s} 누적 {total:,}건")
    fails = [s for s in summary if s[2] in ("error", "exception")]
    if fails:
        print(f"\n실패 {len(fails)}건:")
        for key, name, status, _ in fails:
            print(f"  {key} {name} → {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
