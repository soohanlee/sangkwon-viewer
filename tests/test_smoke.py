"""키 없이 정규화/적재 로직을 검증하는 스모크 테스트.

실제 API 응답을 모사한 샘플 페이로드를 파서에 직접 흘려 DB 적재가 되는지 확인한다.
실행: uv run python -m tests.test_smoke
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from sangkwon import db as db_mod
from sangkwon.collectors.base import CollectResult
from sangkwon.collectors.molit import MolitCollector
from sangkwon.collectors.store_info import StoreInfoCollector
from sangkwon.settings import ApiKeys, Region, Sigungu

REGION = Region(
    key="testcity",
    name="테스트시",
    sido_code="41",
    sgis_adm_cd="41131",
    sigungu=[Sigungu(code="41131", name="테스트구")],
    adong_codes=["4113151500"],
)

STORE_ITEMS = [
    {
        "bizesId": "MA01", "bizesNm": "행복카페", "indsLclsCd": "Q", "indsLclsNm": "음식",
        "indsMclsCd": "Q12", "indsMclsNm": "비알코올", "indsSclsCd": "Q12A01", "indsSclsNm": "카페",
        "adongCd": "4113151500", "adongNm": "신흥동", "ldongCd": "4113110100",
        "rdnmAdr": "성남대로 1", "lon": "127.1", "lat": "37.44",
    },
    {
        "bizesId": "MA02", "bizesNm": "분식왕", "indsLclsCd": "Q", "indsLclsNm": "음식",
        "indsMclsCd": "Q11", "indsMclsNm": "한식", "indsSclsCd": "Q11A02", "indsSclsNm": "분식",
        "adongCd": "4113151500", "adongNm": "신흥동", "ldongCd": "4113110100",
        "rdnmAdr": "성남대로 2", "lon": "127.2", "lat": "37.45",
    },
]

MOLIT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header>
<body><items>
  <item><건물명>샘플빌딩</건물명><법정동>신흥동</법정동><건물면적>84.5</건물면적>
        <층>3</층><거래금액>120,000</거래금액><건축년도>2005</건축년도><건물주용도>제2종근린생활시설</건물주용도></item>
</items><numOfRows>1000</numOfRows><pageNo>1</pageNo><totalCount>1</totalCount></body></response>"""


def main() -> int:
    conn = db_mod.connect(":memory:")
    conn.executescript(db_mod.SCHEMA)
    keys = ApiKeys()

    # 1) 상가정보 적재 + 업종집계
    si = StoreInfoCollector(conn, keys)
    for it in STORE_ITEMS:
        si._upsert_store(REGION, it)
    conn.commit()
    si._aggregate_counts(REGION)
    stores = conn.execute("SELECT COUNT(*) c FROM stores").fetchone()["c"]
    counts = conn.execute(
        "SELECT inds_cls_cd, store_count FROM store_counts WHERE level='lcls'"
    ).fetchall()
    assert stores == 2, stores
    assert counts[0]["inds_cls_cd"] == "Q" and counts[0]["store_count"] == 2, dict(counts[0])
    print(f"✓ store_info: stores={stores}, 업종 Q 점포수={counts[0]['store_count']}")

    # 2) 국토부 XML 파싱 + 적재
    mc = MolitCollector(conn, keys)
    root = ET.fromstring(MOLIT_XML)
    mc._check_header(root)
    for item in root.findall(".//items/item"):
        mc._insert(REGION, item, "41131", "202601", "trade")
    conn.commit()
    row = conn.execute(
        "SELECT building_nm, use_area, deal_amount, trade_type FROM real_estate"
    ).fetchone()
    assert row["building_nm"] == "샘플빌딩", dict(row)
    assert row["use_area"] == 84.5, dict(row)
    assert row["deal_amount"] == 120000, dict(row)  # 콤마 제거 확인
    print(f"✓ molit: {row['building_nm']} {row['use_area']}㎡ {row['deal_amount']}만원 ({row['trade_type']})")

    # 3) 내보내기 동작
    from sangkwon.export import DATA_TABLES
    assert "stores" in DATA_TABLES and "real_estate" in DATA_TABLES
    print("✓ export 테이블 매핑 정상")

    print("\n🎉 스모크 테스트 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
