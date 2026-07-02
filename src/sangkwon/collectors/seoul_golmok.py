"""서울 열린데이터광장 - 골목상권 분석서비스 (상권 축: 유동인구·추정매출·점포·폐업률).

소상공인365가 공개 API를 제공하지 않아, 서울 지역은 이 서비스로 상권 축을 채운다.
데이터 단위는 '상권코드(TRDAR_CD)' 이며, 상권영역(TbgisTrdarRelm)에 자치구/행정동 코드가
함께 있어 다른 소스(행정동 기준)와 조인할 수 있다.

호출형식: http://openapi.seoul.go.kr:8088/{인증키}/json/{서비스명}/{시작}/{끝}/[기준년분기]
  - 인증키 없으면 'sample' (최대 5건 제한, 테스트용)
  - 한 번에 최대 1000건, 기준년분기(STDR_YYQU_CD)를 뒤에 붙이면 서버측 분기 필터

서비스명(실측 확인):
  TbgisTrdarRelm    상권영역(좌표·자치구·행정동)   - 자치구 필터용 마스터
  VwsmTrdarFlpopQq  길단위 유동인구              - TOT_FLPOP_CO
  VwsmTrdarSelngQq  추정매출(상권×업종)          - THSMON_SELNG_AMT/CO
  VwsmTrdarStorQq   점포(상권×업종)             - STOR_CO, CLSBIZ_STOR_CO(폐업), OPBIZ_STOR_CO(개업)
"""
from __future__ import annotations

from collections import defaultdict

from ..http import ApiError, HttpClient
from ..settings import Region
from ..util import clean, now_iso, save_raw, to_float
from .base import BaseCollector, CollectResult

BASE = "http://openapi.seoul.go.kr:8088"
PAGE = 1000
SAMPLE_PAGE = 5  # sample 키 제한
AREA = "TbgisTrdarRelm"
FLPOP = "VwsmTrdarFlpopQq"
SELNG = "VwsmTrdarSelngQq"
STOR = "VwsmTrdarStorQq"
# 최신 분기 자동탐색 후보(내림차순). 데이터는 분기말 +2개월 후 갱신.
QUARTER_CANDIDATES = [
    "20261", "20254", "20253", "20252", "20251",
    "20244", "20243", "20242", "20241",
]


class SeoulGolmokCollector(BaseCollector):
    source = "seoul_golmok"
    required_keys = ("seoul",)

    def __init__(self, conn, keys, *, quarter: str | None = None):
        super().__init__(conn, keys)
        self.quarter = quarter

    def missing_keys(self) -> list[str]:
        # 키가 없어도 sample 로 동작 가능하므로 누락으로 막지 않는다.
        return []

    @property
    def _key(self) -> str:
        return self.keys.seoul or "sample"

    @property
    def _page(self) -> int:
        return PAGE if self.keys.seoul else SAMPLE_PAGE

    def collect(self, region: Region, http: HttpClient, result: CollectResult) -> None:
        signgu_codes = {s.code for s in region.sigungu}
        if not signgu_codes:
            result.status = "error"
            result.message = "시군구 코드가 없습니다."
            return

        # 1) 상권영역 마스터 → 대상 자치구 상권만 추림
        area_rows = self._fetch_all(http, AREA)
        result.raw_paths.append(str(save_raw(self.source, region.key, "area", area_rows[:50])))
        targets: dict[str, dict] = {}
        for r in area_rows:
            if clean(r.get("SIGNGU_CD")) in signgu_codes:
                targets[clean(r.get("TRDAR_CD"))] = r
        if not targets:
            result.status = "error"
            result.message = (
                "대상 자치구의 상권을 찾지 못했습니다. 서울 자치구만 지원합니다"
                f"(요청 자치구코드: {sorted(signgu_codes)}). sample 키는 5건 제한이라 비어있을 수 있음."
            )
            return
        self._upsert_areas(region, targets.values())

        quarter = self.quarter or self._detect_quarter(http)
        if not quarter:
            result.status = "partial"
            result.message = "최신 분기를 찾지 못해 상권영역만 적재했습니다."
            result.record_count = len(targets)
            return

        stamp = now_iso()
        n = len(targets)

        # 2) 유동인구
        n += self._load_simple(http, FLPOP, quarter, targets, region, stamp, "유동인구", "TOT_FLPOP_CO", "명")
        # 3) 추정매출 (상권×업종 → 상권 합계)
        n += self._load_aggregate(
            http, SELNG, quarter, targets, region, stamp,
            [("추정매출", "THSMON_SELNG_AMT", "원"), ("추정매출건수", "THSMON_SELNG_CO", "건")],
        )
        # 4) 점포/폐업 (상권×업종 → 상권 합계 + 폐업률 파생)
        n += self._load_stores(http, STOR, quarter, targets, region, stamp)

        result.record_count = n
        result.message = f"기준분기 {quarter}, 대상 상권 {len(targets)}개"
        self.conn.commit()

    # ------------------------------------------------------------------
    def _url(self, service: str, start: int, end: int, quarter: str | None) -> str:
        tail = f"/{quarter}" if quarter else ""
        return f"{BASE}/{self._key}/json/{service}/{start}/{end}{tail}"

    def _fetch_all(self, http: HttpClient, service: str, quarter: str | None = None) -> list[dict]:
        rows: list[dict] = []
        start = 1
        while True:
            end = start + self._page - 1
            payload = http.get_json(self._url(service, start, end, quarter))
            body = payload.get(service) if isinstance(payload, dict) else None
            if not isinstance(body, dict):
                # sample 5건 초과 요청 등 에러 응답
                raise ApiError(f"{service} 응답 이상: {str(payload)[:200]}")
            code = (body.get("RESULT") or {}).get("CODE", "")
            if code and code not in ("INFO-000",):
                raise ApiError(f"{service} 오류: {code} {(body.get('RESULT') or {}).get('MESSAGE')}")
            batch = body.get("row") or []
            rows.extend(batch)
            total = int(body.get("list_total_count") or 0)
            if not self.keys.seoul:  # sample 키는 1페이지(5건)로 종료
                break
            if end >= total or not batch:
                break
            start += self._page
        return rows

    def _detect_quarter(self, http: HttpClient) -> str | None:
        for q in QUARTER_CANDIDATES:
            try:
                payload = http.get_json(self._url(FLPOP, 1, 1, q))
                body = payload.get(FLPOP, {})
                if int(body.get("list_total_count") or 0) > 0:
                    return q
            except ApiError:
                continue
        return None

    def _upsert_areas(self, region: Region, rows) -> None:
        for r in rows:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO trdar_area
                    (trdar_cd, trdar_nm, trdar_se_nm, signgu_cd, signgu_nm,
                     adstrd_cd, adstrd_nm, x, y, region_key, collected_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    clean(r.get("TRDAR_CD")), clean(r.get("TRDAR_CD_NM")), clean(r.get("TRDAR_SE_CD_NM")),
                    clean(r.get("SIGNGU_CD")), clean(r.get("SIGNGU_CD_NM")),
                    clean(r.get("ADSTRD_CD")), clean(r.get("ADSTRD_CD_NM")),
                    to_float(r.get("XCNTS_VALUE")), to_float(r.get("YDNTS_VALUE")),
                    region.key, now_iso(),
                ),
            )
        self.conn.commit()

    def _insert_indicator(self, trdar_cd, indicator, period, value, unit, region, stamp) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO commercial_analysis
                (adm_cd, indicator, period, value, unit, region_key, collected_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (trdar_cd, indicator, period, value, unit, region.key, stamp),
        )

    def _load_simple(self, http, service, quarter, targets, region, stamp, indicator, field, unit) -> int:
        rows = self._fetch_all(http, service, quarter)
        n = 0
        for r in rows:
            cd = clean(r.get("TRDAR_CD"))
            if cd in targets:
                self._insert_indicator(cd, indicator, quarter, to_float(r.get(field)), unit, region, stamp)
                n += 1
        self.conn.commit()
        return n

    def _load_aggregate(self, http, service, quarter, targets, region, stamp, specs) -> int:
        rows = self._fetch_all(http, service, quarter)
        agg: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for r in rows:
            cd = clean(r.get("TRDAR_CD"))
            if cd not in targets:
                continue
            for indicator, field, _unit in specs:
                v = to_float(r.get(field))
                if v is not None:
                    agg[cd][indicator] += v
        n = 0
        for cd, vals in agg.items():
            for indicator, _field, unit in specs:
                self._insert_indicator(cd, indicator, quarter, vals.get(indicator), unit, region, stamp)
                n += 1
        self.conn.commit()
        return n

    def _load_stores(self, http, service, quarter, targets, region, stamp) -> int:
        rows = self._fetch_all(http, service, quarter)
        agg: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for r in rows:
            cd = clean(r.get("TRDAR_CD"))
            if cd not in targets:
                continue
            agg[cd]["점포수"] += to_float(r.get("STOR_CO")) or 0
            agg[cd]["폐업점포수"] += to_float(r.get("CLSBIZ_STOR_CO")) or 0
            agg[cd]["개업점포수"] += to_float(r.get("OPBIZ_STOR_CO")) or 0
            agg[cd]["프랜차이즈점포수"] += to_float(r.get("FRC_STOR_CO")) or 0
        n = 0
        for cd, v in agg.items():
            self._insert_indicator(cd, "점포수", quarter, v["점포수"], "개", region, stamp)
            self._insert_indicator(cd, "폐업점포수", quarter, v["폐업점포수"], "개", region, stamp)
            self._insert_indicator(cd, "개업점포수", quarter, v["개업점포수"], "개", region, stamp)
            self._insert_indicator(cd, "프랜차이즈점포수", quarter, v["프랜차이즈점포수"], "개", region, stamp)
            clsbiz_rt = (v["폐업점포수"] / v["점포수"] * 100) if v["점포수"] else None
            self._insert_indicator(cd, "폐업률", quarter, clsbiz_rt, "%", region, stamp)
            n += 5
        self.conn.commit()
        return n
