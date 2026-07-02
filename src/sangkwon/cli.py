"""상권분석 수집기 CLI.

사용 예:
  sangkwon init-db
  sangkwon regions
  sangkwon doctor
  sangkwon collect store_info --region seongnam
  sangkwon collect molit --region seongnam --months 6
  sangkwon collect-all --region seongnam
  sangkwon export --region seongnam --format both
  sangkwon status
"""
from __future__ import annotations

import argparse
import sys

from . import db as db_mod
from .collectors import COLLECTORS
from .collectors.molit import MolitCollector, recent_months
from .export import export_csv, export_json
from .settings import ApiKeys, ensure_dirs, get_region, load_regions


def _build_collector(name: str, conn, keys: ApiKeys, args):
    cls = COLLECTORS[name]
    if cls is MolitCollector:
        deal_yms = None
        if getattr(args, "deal_ym", None):
            deal_yms = [s.strip() for s in args.deal_ym.split(",") if s.strip()]
        elif getattr(args, "months", None):
            deal_yms = recent_months(args.months)
        return MolitCollector(conn, keys, deal_yms=deal_yms, include_rent=getattr(args, "with_rent", False))
    from .collectors.store_info import StoreInfoCollector
    if cls is StoreInfoCollector:
        return StoreInfoCollector(conn, keys, max_pages=getattr(args, "max_pages", None))
    from .collectors.seoul_golmok import SeoulGolmokCollector
    if cls is SeoulGolmokCollector:
        return SeoulGolmokCollector(conn, keys, quarter=getattr(args, "quarter", None))
    return cls(conn, keys)


def cmd_init_db(args) -> int:
    ensure_dirs()
    path = db_mod.init_db()
    print(f"✓ DB 초기화 완료: {path}")
    return 0


def cmd_regions(args) -> int:
    regions = load_regions()
    if not regions:
        print("등록된 지역이 없습니다. config/regions.json 을 확인하세요.")
        return 1
    print("등록된 지역:")
    for key, r in regions.items():
        sgg = ", ".join(s.name for s in r.sigungu)
        adong = f", 행정동 {len(r.adong_codes)}개" if r.adong_codes else ""
        print(f"  - {key:12s} {r.name}  [{sgg}{adong}]")
    return 0


def cmd_doctor(args) -> int:
    keys = ApiKeys.from_env()
    print("API 키 설정 상태:")
    checks = [
        ("공공데이터포털(상가정보)", keys.data_go_kr),
        ("SGIS consumer_key", keys.sgis_key),
        ("SGIS consumer_secret", keys.sgis_secret),
        ("국토부 실거래가", keys.molit),
        ("소상공인365", keys.sbiz365),
    ]
    for label, val in checks:
        mark = "✓" if val else "✗"
        shown = (val[:6] + "…") if val else "(미설정)"
        print(f"  {mark} {label:22s} {shown}")
    missing = [lbl for lbl, v in checks if not v]
    if missing:
        print(f"\n미설정 {len(missing)}건. .env 에 키를 채우세요 (.env.example 참고).")
    return 0


def _collect_one(name: str, region_key: str, args) -> int:
    keys = ApiKeys.from_env()
    ensure_dirs()
    db_mod.init_db()
    region = get_region(region_key)
    conn = db_mod.connect()
    try:
        collector = _build_collector(name, conn, keys, args)
        missing = collector.missing_keys()
        if missing:
            print(f"✗ {name}: 필요한 키 누락 → {', '.join(missing)} (.env 확인)")
            return 2
        print(f"▶ [{name}] '{region.name}' 수집 시작…")
        result = collector.run(region)
        icon = {"success": "✓", "partial": "△", "error": "✗"}.get(result.status, "?")
        print(f"{icon} [{name}] {result.status} · {result.record_count}건 · raw {len(result.raw_paths)}개")
        if result.message:
            print(f"    ↳ {result.message}")
        return 0 if result.status != "error" else 1
    finally:
        conn.close()


def cmd_collect(args) -> int:
    if args.source not in COLLECTORS:
        print(f"알 수 없는 소스: {args.source}. 사용 가능: {', '.join(COLLECTORS)}")
        return 2
    return _collect_one(args.source, args.region, args)


def cmd_collect_all(args) -> int:
    rc = 0
    for name in COLLECTORS:
        rc |= _collect_one(name, args.region, args)
    return 0 if rc == 0 else 1


def cmd_export(args) -> int:
    ensure_dirs()
    db_mod.init_db()
    conn = db_mod.connect()
    try:
        region_key = args.region
        if args.format in ("json", "both"):
            p = export_json(conn, region_key)
            print(f"✓ JSON 내보내기: {p}")
        if args.format in ("csv", "both"):
            paths = export_csv(conn, region_key)
            print(f"✓ CSV 내보내기: {len(paths)}개 테이블 → {paths[0].parent if paths else '(데이터 없음)'}")
    finally:
        conn.close()
    return 0


def cmd_ping(args) -> int:
    """발급 키가 실제로 동작하는지 라이브로 점검."""
    from .http import HttpClient

    keys = ApiKeys.from_env()
    ok = True

    # 1) 공공데이터포털(상가정보) - 업종 대분류 목록 호출
    if keys.data_go_kr:
        url = "https://apis.data.go.kr/B553077/api/open/sdsc2/largeUpjongList"
        try:
            with HttpClient() as h:
                r = h.get(url, params={"serviceKey": keys.data_go_kr, "type": "json", "numOfRows": 1})
            if r.status_code == 200 and '"resultCode"' in r.text or '"items"' in r.text:
                print("✓ 공공데이터포털 상가정보: 키 정상 동작")
            else:
                ok = False
                print(f"✗ 공공데이터포털 상가정보: HTTP {r.status_code} · {r.text[:80].strip()}")
                print("    ↳ 401/Unauthorized 면 (1)활용신청 승인 여부 (2)키 반영 지연(최대 1~2시간) 확인")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"✗ 공공데이터포털 상가정보: {exc}")
    else:
        print("· 공공데이터포털 키 미설정")

    # 2) SGIS 인증
    if keys.sgis_key and keys.sgis_secret:
        from .collectors.sgis import SGIS_BASE
        try:
            with HttpClient() as h:
                data = h.get_json(
                    f"{SGIS_BASE}/auth/authentication.json",
                    params={"consumer_key": keys.sgis_key, "consumer_secret": keys.sgis_secret},
                )
            token = (data or {}).get("result", {}).get("accessToken")
            if token:
                print("✓ SGIS: 인증 성공 (accessToken 발급됨)")
            else:
                ok = False
                print(f"✗ SGIS: 인증 실패 · {data}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"✗ SGIS: {exc}")
    else:
        print("· SGIS 키 미설정")

    # 3) 서울 열린데이터광장
    if keys.seoul:
        from .collectors.seoul_golmok import BASE as SEOUL_BASE
        try:
            with HttpClient() as h:
                data = h.get_json(f"{SEOUL_BASE}/{keys.seoul}/json/VwsmTrdarFlpopQq/1/1/")
                body = data.get("VwsmTrdarFlpopQq", {})
                code = (body.get("RESULT") or {}).get("CODE", "")
            if code == "INFO-000":
                print("✓ 서울 골목상권: 키 정상 동작")
            else:
                ok = False
                print(f"✗ 서울 골목상권: {code} {(body.get('RESULT') or {}).get('MESSAGE')}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"✗ 서울 골목상권: {exc}")
    else:
        print("· 서울 키 미설정(sample 5건 제한으로 동작)")

    return 0 if ok else 1


def cmd_status(args) -> int:
    db_mod.init_db()
    conn = db_mod.connect()
    try:
        print("최근 수집 실행:")
        rows = conn.execute(
            "SELECT source, region_key, status, record_count, started_at, message "
            "FROM collection_runs ORDER BY id DESC LIMIT 15"
        ).fetchall()
        if not rows:
            print("  (아직 수집 이력이 없습니다. 'sangkwon collect-all --region <키>')")
        for r in rows:
            msg = f" · {r['message']}" if r["message"] else ""
            print(f"  [{r['started_at']}] {r['source']:11s} {r['region_key']:10s} {r['status']:8s} {r['record_count']:>6}건{msg}")
        print("\n테이블 행 수:")
        for t in ("regions", "demographics", "stores", "store_counts", "real_estate", "commercial_analysis"):
            n = conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
            print(f"  {t:20s} {n:>8}")
    finally:
        conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sangkwon", description="상권분석 데이터 수집기")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="SQLite 스키마 생성").set_defaults(func=cmd_init_db)
    sub.add_parser("regions", help="등록된 지역 목록").set_defaults(func=cmd_regions)
    sub.add_parser("doctor", help="API 키 설정 점검").set_defaults(func=cmd_doctor)
    sub.add_parser("status", help="수집 이력/행 수 확인").set_defaults(func=cmd_status)
    sub.add_parser("ping", help="발급 키 라이브 점검").set_defaults(func=cmd_ping)

    c = sub.add_parser("collect", help="단일 소스 수집")
    c.add_argument("source", choices=list(COLLECTORS), help="수집 소스")
    c.add_argument("--region", required=True, help="config/regions.json 의 지역 키")
    c.add_argument("--months", type=int, default=3, help="(molit) 최근 N개월 (기본 3)")
    c.add_argument("--deal-ym", help="(molit) 특정 연월 목록 예: 202601,202602")
    c.add_argument("--with-rent", action="store_true", help="(molit) 전월세 포함 시도 (상업용 전월세 공개 API 없음 - 보통 실패)")
    c.add_argument("--max-pages", type=int, help="(store_info) 시군구당 최대 페이지 제한(테스트용, 1페이지=1000건)")
    c.add_argument("--quarter", help="(seoul_golmok) 기준년분기 예: 20261 (생략 시 최신 자동탐색)")
    c.set_defaults(func=cmd_collect)

    ca = sub.add_parser("collect-all", help="모든 소스 수집")
    ca.add_argument("--region", required=True)
    ca.add_argument("--months", type=int, default=3)
    ca.add_argument("--deal-ym")
    ca.add_argument("--with-rent", action="store_true")
    ca.set_defaults(func=cmd_collect_all)

    e = sub.add_parser("export", help="JSON/CSV 내보내기")
    e.add_argument("--region", help="특정 지역만 (생략 시 전체)")
    e.add_argument("--format", choices=["json", "csv", "both"], default="both")
    e.set_defaults(func=cmd_export)

    return p


def _force_utf8_stdout() -> None:
    """Windows 콘솔(cp949)에서 ✓ 등 기호 출력 시 인코딩 오류 방지."""
    for stream in (sys.stdout, sys.stderr):
        reconfig = getattr(stream, "reconfigure", None)
        if reconfig:
            try:
                reconfig(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
