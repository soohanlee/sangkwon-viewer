"""통계청 SGIS 오픈API - 인구/가구/소득 (수요 축).

인증 흐름: consumer_key + consumer_secret 로 accessToken 발급 후 각 통계 API 호출.
  인증:   https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.json
  인구:   https://sgisapi.kostat.go.kr/OpenAPI3/stats/population.json
  가구:   https://sgisapi.kostat.go.kr/OpenAPI3/stats/household.json
  행정코드: https://sgisapi.kostat.go.kr/OpenAPI3/addr/stage.json

주의: SGIS 행정구역코드(adm_cd)는 통계청 자체 코드 체계로, 공공데이터포털 상가정보 API 가
쓰는 행안부 행정동코드(10자리)와 다를 수 있다. 두 소스를 조인할 때는 행정동명 기준 매핑을
함께 확인하라. (README 의 '코드 체계' 절 참고)
"""
from __future__ import annotations

from ..http import ApiError, HttpClient
from ..settings import ApiKeys, Region
from ..util import save_raw, to_float, to_int
from .base import BaseCollector, CollectResult

SGIS_BASE = "https://sgisapi.kostat.go.kr/OpenAPI3"
# 통계 기준연도: 최신 가용 연도로 조정 가능 (env 로 덮어쓰기)
import os

YEAR = os.getenv("SGIS_STAT_YEAR", "2022")


class SgisClient:
    """SGIS 토큰 발급 및 통계 호출 래퍼."""

    def __init__(self, http: HttpClient, keys: ApiKeys):
        self.http = http
        self.keys = keys
        self._token: str | None = None

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = self._authenticate()
        return self._token

    def _authenticate(self) -> str:
        data = self.http.get_json(
            f"{SGIS_BASE}/auth/authentication.json",
            params={
                "consumer_key": self.keys.sgis_key,
                "consumer_secret": self.keys.sgis_secret,
            },
        )
        result = (data or {}).get("result") or {}
        token = result.get("accessToken")
        if not token:
            raise ApiError(f"SGIS 인증 실패: {data}")
        return token

    def population(self, adm_cd: str, *, low_search: int = 1) -> list[dict]:
        return self._stats("population", adm_cd, low_search)

    def household(self, adm_cd: str, *, low_search: int = 1) -> list[dict]:
        return self._stats("household", adm_cd, low_search)

    def _stats(self, kind: str, adm_cd: str, low_search: int) -> list[dict]:
        data = self.http.get_json(
            f"{SGIS_BASE}/stats/{kind}.json",
            params={
                "accessToken": self.token,
                "year": YEAR,
                "adm_cd": adm_cd,
                "low_search": low_search,
            },
        )
        if str((data or {}).get("errCd", "0")) not in ("0", "00"):
            raise ApiError(f"SGIS {kind} 오류: {data.get('errCd')} {data.get('errMsg')}")
        return (data or {}).get("result") or []

    def adong_codes_under(self, sgg_code: str) -> list[str]:
        """시군구 코드 하위 행정동(읍면동) SGIS 코드 목록."""
        data = self.http.get_json(
            f"{SGIS_BASE}/addr/stage.json",
            params={"accessToken": self.token, "cd": sgg_code},
        )
        return [row["cd"] for row in (data or {}).get("result", []) if row.get("cd")]


class SgisCollector(BaseCollector):
    source = "sgis"
    required_keys = ("sgis_key", "sgis_secret")

    def collect(self, region: Region, http: HttpClient, result: CollectResult) -> None:
        client = SgisClient(http, self.keys)
        sgis_codes = region.sgis_codes
        if not sgis_codes:
            result.status = "error"
            result.message = (
                "SGIS 시군구 코드(sgis_codes)가 없습니다. SGIS 코드는 행안부 코드와 달라 "
                "addr/stage API 로 조회해 regions.json 에 채워야 합니다. (README 코드 체계 참고)"
            )
            return
        count = 0
        for code in sgis_codes:
            count += self._collect_sigungu(region, client, result, code)
        result.record_count = count
        self.conn.commit()

    def _collect_sigungu(
        self, region: Region, client: SgisClient, result: CollectResult, sgg_code: str
    ) -> int:
        from ..util import clean, now_iso

        pop = client.population(sgg_code, low_search=1)
        hh = client.household(sgg_code, low_search=1)
        result.raw_paths.append(str(save_raw(self.source, region.key, f"pop_{sgg_code}", pop)))
        result.raw_paths.append(str(save_raw(self.source, region.key, f"hh_{sgg_code}", hh)))

        hh_by_cd = {row.get("adm_cd"): row for row in hh}
        stamp = now_iso()
        n = 0
        for row in pop:
            adm_cd = clean(row.get("adm_cd"))
            if not adm_cd:
                continue
            hrow = hh_by_cd.get(row.get("adm_cd"), {})
            self.conn.execute(
                """
                INSERT OR REPLACE INTO demographics
                    (adm_cd, year, population, households, avg_age, region_key, collected_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    adm_cd,
                    int(YEAR),
                    to_int(row.get("population") or row.get("tot_ppltn")),
                    to_int(hrow.get("household_cnt") or hrow.get("tot_family")),
                    to_float(row.get("avg_age")),
                    region.key,
                    stamp,
                ),
            )
            # 행정동 마스터에도 등록
            self.conn.execute(
                """
                INSERT OR REPLACE INTO regions
                    (adm_cd, adm_nm, sigungu, region_key, lon, lat, collected_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    adm_cd,
                    clean(row.get("adm_nm")),
                    sgg_code,
                    region.key,
                    to_float(row.get("x")),
                    to_float(row.get("y")),
                    stamp,
                ),
            )
            n += 1
        return n
