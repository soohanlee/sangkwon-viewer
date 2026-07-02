"""서울 골목상권 수집기 offline 검증 (키 불필요).

_fetch_all 을 실제 응답 필드 구조의 가짜 데이터로 대체해 collect() 전체를 돌리고,
trdar_area 적재·자치구 필터·매출 집계·폐업률 파생을 검증한다.
실행: uv run python -m tests.test_seoul
"""
from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from sangkwon import db as db_mod
from sangkwon.collectors.base import CollectResult
from sangkwon.collectors.seoul_golmok import AREA, FLPOP, SELNG, STOR, SeoulGolmokCollector
from sangkwon.settings import ApiKeys, Region, Sigungu

REGION = Region(
    key="gangnam", name="서울 강남구", sido_code="11", sgis_adm_cd="11230",
    sigungu=[Sigungu(code="11680", name="강남구")],
)

# 실제 API 필드명을 그대로 사용한 가짜 응답
AREA_ROWS = [
    {"TRDAR_CD": "3001491", "TRDAR_CD_NM": "강남역", "TRDAR_SE_CD_NM": "발달상권",
     "SIGNGU_CD": "11680", "SIGNGU_CD_NM": "강남구", "ADSTRD_CD": "11680640",
     "ADSTRD_CD_NM": "역삼1동", "XCNTS_VALUE": "200000", "YDNTS_VALUE": "440000"},
    {"TRDAR_CD": "3110055", "TRDAR_CD_NM": "황학동", "TRDAR_SE_CD_NM": "골목상권",
     "SIGNGU_CD": "11140", "SIGNGU_CD_NM": "중구", "ADSTRD_CD": "11140670",
     "ADSTRD_CD_NM": "황학동", "XCNTS_VALUE": "201642", "YDNTS_VALUE": "452260"},  # 강남 아님 → 제외
]
FLPOP_ROWS = [{"TRDAR_CD": "3001491", "TOT_FLPOP_CO": 700000.0}]
SELNG_ROWS = [  # 강남역 상권의 2개 업종
    {"TRDAR_CD": "3001491", "THSMON_SELNG_AMT": 100.0, "THSMON_SELNG_CO": 10.0},
    {"TRDAR_CD": "3001491", "THSMON_SELNG_AMT": 200.0, "THSMON_SELNG_CO": 20.0},
]
STOR_ROWS = [
    {"TRDAR_CD": "3001491", "STOR_CO": 50.0, "CLSBIZ_STOR_CO": 5.0, "OPBIZ_STOR_CO": 3.0, "FRC_STOR_CO": 2.0},
    {"TRDAR_CD": "3001491", "STOR_CO": 50.0, "CLSBIZ_STOR_CO": 5.0, "OPBIZ_STOR_CO": 1.0, "FRC_STOR_CO": 0.0},
]


def main() -> int:
    conn = db_mod.connect(":memory:")
    conn.executescript(db_mod.SCHEMA)

    col = SeoulGolmokCollector(conn, ApiKeys(seoul="dummy"), quarter="20261")

    fake = {AREA: AREA_ROWS, FLPOP: FLPOP_ROWS, SELNG: SELNG_ROWS, STOR: STOR_ROWS}
    col._fetch_all = lambda http, service, quarter=None: fake[service]  # type: ignore

    result = CollectResult(source=col.source, region_key=REGION.key)
    col.collect(REGION, None, result)

    # 1) 자치구 필터: 강남(11680) 상권만, 중구는 제외
    areas = conn.execute("SELECT trdar_cd, trdar_nm, adstrd_nm FROM trdar_area").fetchall()
    assert len(areas) == 1 and areas[0]["trdar_nm"] == "강남역", [dict(a) for a in areas]
    print(f"✓ 자치구 필터: 강남 상권 1개만 적재({areas[0]['trdar_nm']}/{areas[0]['adstrd_nm']}), 중구 제외")

    def val(ind):
        r = conn.execute("SELECT value FROM commercial_analysis WHERE indicator=?", (ind,)).fetchone()
        return r["value"] if r else None

    assert val("유동인구") == 700000.0
    assert val("추정매출") == 300.0, val("추정매출")          # 100+200
    assert val("추정매출건수") == 30.0
    assert val("점포수") == 100.0                            # 50+50
    assert val("폐업점포수") == 10.0
    assert val("폐업률") == 10.0, val("폐업률")               # 10/100*100
    print(f"✓ 지표: 유동인구 {val('유동인구'):.0f}명, 추정매출 합계 {val('추정매출'):.0f}, "
          f"점포 {val('점포수'):.0f}개, 폐업률 {val('폐업률'):.0f}%")

    print(f"\n🎉 서울 골목상권 수집기 검증 통과 (status={result.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
