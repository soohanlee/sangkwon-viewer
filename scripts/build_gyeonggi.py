"""경기도 31개 시군구 regions.json 항목 생성 + LAWD 코드 라이브 검증.

- SGIS 시군구 코드: scripts/_sgis_gyeonggi.json (addr/stage 로 받아둔 실측값)
- LAWD(법정동) 시군구 코드: 아래 LAWD 표 (store_info signguCd / molit LAWD_CD 용)
- 각 LAWD 코드를 상가정보 API(storeListInDong, 1행)로 호출해 totalCount 로 유효성 검증
출력: scripts/_gyeonggi_regions.json (검증 통과분), 콘솔에 검증 리포트
"""
from __future__ import annotations

import json
from pathlib import Path

from sangkwon.http import HttpClient
from sangkwon.settings import ApiKeys

ROOT = Path(__file__).resolve().parents[1]
SGIS_FILE = ROOT / "scripts" / "_sgis_gyeonggi.json"
OUT_FILE = ROOT / "scripts" / "_gyeonggi_regions.json"

STORE_API = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong"

# 시(영문 슬러그) - region 키
SLUG = {
    "수원시": "suwon", "성남시": "seongnam", "의정부시": "uijeongbu", "안양시": "anyang",
    "부천시": "bucheon", "광명시": "gwangmyeong", "평택시": "pyeongtaek", "동두천시": "dongducheon",
    "안산시": "ansan", "고양시": "goyang", "과천시": "gwacheon", "구리시": "guri",
    "남양주시": "namyangju", "오산시": "osan", "시흥시": "siheung", "군포시": "gunpo",
    "의왕시": "uiwang", "하남시": "hanam", "용인시": "yongin", "파주시": "paju",
    "이천시": "icheon", "안성시": "anseong", "김포시": "gimpo", "화성시": "hwaseong",
    "광주시": "gwangju_gg", "양주시": "yangju", "포천시": "pocheon", "여주시": "yeoju",
    "연천군": "yeoncheon", "가평군": "gapyeong", "양평군": "yangpyeong",
}

# 하위 행정구역(addr_name) -> LAWD 5자리. 부천은 시 단위 41190 으로 별도 처리.
LAWD = {
    "수원시 장안구": "41111", "수원시 권선구": "41113", "수원시 팔달구": "41115", "수원시 영통구": "41117",
    "성남시 수정구": "41131", "성남시 중원구": "41133", "성남시 분당구": "41135",
    "의정부시": "41150",
    "안양시 만안구": "41171", "안양시 동안구": "41173",
    "광명시": "41210", "평택시": "41220", "동두천시": "41250",
    "안산시 상록구": "41271", "안산시 단원구": "41273",
    "고양시 덕양구": "41281", "고양시 일산동구": "41285", "고양시 일산서구": "41287",
    "과천시": "41290", "구리시": "41310", "남양주시": "41360", "오산시": "41370",
    "시흥시": "41390", "군포시": "41410", "의왕시": "41430", "하남시": "41450",
    "용인시 처인구": "41461", "용인시 기흥구": "41463", "용인시 수지구": "41465",
    "파주시": "41480", "이천시": "41500", "안성시": "41550", "김포시": "41570",
    "광주시": "41610", "양주시": "41630", "포천시": "41650",
    "여주시": "41670", "연천군": "41800", "가평군": "41820", "양평군": "41830",
}
# 부천: 구 폐지(2016). 후보를 순서대로 검증해 첫 유효 코드 사용.
BUCHEON_CANDIDATES = [("41190", "부천시"), ("41192", "부천시 원미구"),
                      ("41194", "부천시 소사구"), ("41196", "부천시 오정구")]
# 화성: 2025 특례시 전환으로 구 신설(SGIS 에는 아직 단일). store_info/molit 용 4개 구.
HWASEONG_GU = [("41591", "화성시 만세구"), ("41593", "화성시 효행구"),
               ("41595", "화성시 병점구"), ("41597", "화성시 동탄구")]


def probe(http: HttpClient, key_code: str, service_key: str) -> int:
    """LAWD 코드로 상가 1건 조회 → totalCount 반환(-1=오류)."""
    try:
        payload = http.get_json(STORE_API, params={
            "serviceKey": service_key, "pageNo": 1, "numOfRows": 1,
            "divId": "signguCd", "key": key_code, "type": "json",
        })
        body = payload.get("body", {}) if isinstance(payload, dict) else {}
        return int(body.get("totalCount") or 0)
    except Exception as exc:  # noqa: BLE001
        print(f"    ! {key_code} 오류: {str(exc)[:80]}")
        return -1


def city_of(addr_name: str) -> str:
    return addr_name.split(" ")[0]


def main() -> None:
    keys = ApiKeys.from_env()
    sgis = json.loads(SGIS_FILE.read_text(encoding="utf-8"))

    # 시별로 SGIS 코드 그룹화
    by_city: dict[str, dict] = {}
    for row in sgis:
        name = row["addr_name"]
        city = city_of(name)
        slug = SLUG[city]
        e = by_city.setdefault(slug, {"name": f"경기도 {city}", "city": city,
                                      "sgis_codes": [], "sigungu": [], "_lawd_seen": set()})
        e["sgis_codes"].append(row["cd"])
        # LAWD (부천 제외)
        if city != "부천시":
            code = LAWD.get(name)
            if code and code not in e["_lawd_seen"]:
                e["sigungu"].append({"code": code, "name": name})
                e["_lawd_seen"].add(code)

    regions: dict[str, dict] = {}
    report = []
    with HttpClient(min_interval=0.25) as http:
        for slug, e in sorted(by_city.items()):
            sigungu = e["sigungu"]
            # 화성 특별처리: SGIS 단일이지만 store_info 는 신설 4개 구
            if e["city"] == "화성시":
                sigungu = [{"code": c, "name": n} for c, n in HWASEONG_GU]
            # 부천 특별처리: 후보 검증
            if e["city"] == "부천시":
                chosen = None
                for code, nm in BUCHEON_CANDIDATES:
                    tc = probe(http, code, keys.data_go_kr)
                    print(f"  [부천 후보] {code} {nm}: totalCount={tc}")
                    if tc > 0:
                        chosen = {"code": code, "name": "부천시" if code == "41190" else nm}
                        # 시 단위(41190)면 그것만, 아니면 3구 모두 추가 필요
                        break
                if chosen and chosen["code"] == "41190":
                    sigungu = [chosen]
                else:
                    # 시단위 실패 → 3개 구 모두 검증해 유효분만
                    sigungu = []
                    for code, nm in BUCHEON_CANDIDATES[1:]:
                        tc = probe(http, code, keys.data_go_kr)
                        if tc > 0:
                            sigungu.append({"code": code, "name": nm})

            total = 0
            ok_codes = []
            for sg in sigungu:
                tc = probe(http, sg["code"], keys.data_go_kr)
                status = "OK" if tc > 0 else ("EMPTY" if tc == 0 else "ERR")
                report.append((slug, sg["code"], sg["name"], tc, status))
                if tc > 0:
                    total += tc
                    ok_codes.append(sg)
            regions[slug] = {
                "name": e["name"],
                "sido_code": "41",
                "sgis_adm_cd": e["sgis_codes"][0],
                "sigungu": ok_codes,
                "sgis_codes": e["sgis_codes"],
                "adong_codes": [],
            }
            print(f"✓ {slug:12s} {e['name']:14s} sigungu={len(ok_codes)} sgis={len(e['sgis_codes'])} 상가합계≈{total:,}")

    OUT_FILE.write_text(json.dumps(regions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n총 {len(regions)}개 시군구 → {OUT_FILE}")
    bad = [r for r in report if r[4] != "OK"]
    if bad:
        print("\n⚠ 검증 실패/빈 코드:")
        for slug, code, nm, tc, st in bad:
            print(f"  {slug} {code} {nm} → {st}({tc})")
    else:
        print("\n✅ 모든 LAWD 코드 검증 통과")


if __name__ == "__main__":
    main()
