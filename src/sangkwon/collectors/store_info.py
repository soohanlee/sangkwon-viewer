"""공공데이터포털 - 소상공인시장진흥공단 상가(상권)정보 (15012005 / 15083033).

경쟁 축 데이터: 시군구 단위 개별 상가업소 목록과 업종별 점포수 집계.

API: 상가업소조회 서비스 (sdsc2)
  베이스: https://apis.data.go.kr/B553077/api/open/sdsc2
  엔드포인트: storeListInDong  (divId=signguCd, key=<시군구코드 5자리>)
  인증: data.go.kr 서비스키
  응답: { header:{resultCode,resultMsg}, body:{items:[...], totalCount, numOfRows, pageNo} }

regions.json 의 sigungu[].code(시군구코드)로 시군구 전체 점포를 조회한다. 각 레코드의
adongCd(행정동코드)로 업종별 점포수를 집계하므로 행정동 코드를 따로 채울 필요가 없다.
"""
from __future__ import annotations

import os

from ..http import ApiError, HttpClient
from ..settings import Region
from ..util import clean, save_raw, to_float
from .base import BaseCollector, CollectResult

BASE = os.getenv(
    "STORE_INFO_BASE_URL",
    "https://apis.data.go.kr/B553077/api/open/sdsc2",
)
ENDPOINT = "storeListInDong"
NUM_OF_ROWS = 1000


class StoreInfoCollector(BaseCollector):
    source = "store_info"
    required_keys = ("data_go_kr",)

    def __init__(self, conn, keys, *, max_pages: int | None = None):
        super().__init__(conn, keys)
        self.max_pages = max_pages  # 시군구당 최대 페이지(테스트용 제한). None=전체

    def collect(self, region: Region, http: HttpClient, result: CollectResult) -> None:
        if not region.sigungu:
            result.status = "error"
            result.message = "시군구 코드(sigungu)가 없습니다. regions.json 을 확인하세요."
            return

        total = 0
        for sgg in region.sigungu:
            total += self._collect_signgu(region, http, result, sgg.code)

        self._aggregate_counts(region)
        result.record_count = total

    # ------------------------------------------------------------------
    def _collect_signgu(
        self, region: Region, http: HttpClient, result: CollectResult, signgu_cd: str
    ) -> int:
        page = 1
        fetched = 0
        while True:
            params = {
                "serviceKey": self.keys.data_go_kr,
                "pageNo": page,
                "numOfRows": NUM_OF_ROWS,
                "divId": "signguCd",
                "key": signgu_cd,
                "type": "json",
            }
            payload = http.get_json(f"{BASE}/{ENDPOINT}", params=params)
            self._check_header(payload, signgu_cd)
            body = payload.get("body", {}) if isinstance(payload, dict) else {}
            items = body.get("items") or []
            if isinstance(items, dict):  # 단건일 때 dict 로 오는 경우 방어
                items = [items]
            if page == 1:
                result.raw_paths.append(
                    str(save_raw(self.source, region.key, f"signgu_{signgu_cd}", payload))
                )
            for it in items:
                self._upsert_store(region, it)
                fetched += 1

            total_count = int(body.get("totalCount") or 0)
            if page * NUM_OF_ROWS >= total_count or not items:
                break
            if self.max_pages and page >= self.max_pages:
                result.status = "partial"
                result.message = f"max_pages={self.max_pages} 제한으로 일부만 수집(시군구 {signgu_cd})"
                break
            page += 1
        self.conn.commit()
        return fetched

    def _upsert_store(self, region: Region, it: dict) -> None:
        from ..util import now_iso

        self.conn.execute(
            """
            INSERT OR REPLACE INTO stores (
                bizes_id, bizes_nm, branch_nm,
                inds_lcls_cd, inds_lcls_nm, inds_mcls_cd, inds_mcls_nm,
                inds_scls_cd, inds_scls_nm,
                adong_cd, adong_nm, ldong_cd, road_addr, lon, lat,
                region_key, collected_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                clean(it.get("bizesId")),
                clean(it.get("bizesNm")),
                clean(it.get("brchNm")),
                clean(it.get("indsLclsCd")),
                clean(it.get("indsLclsNm")),
                clean(it.get("indsMclsCd")),
                clean(it.get("indsMclsNm")),
                clean(it.get("indsSclsCd")),
                clean(it.get("indsSclsNm")),
                clean(it.get("adongCd")),
                clean(it.get("adongNm")),
                clean(it.get("ldongCd")),
                clean(it.get("rdnmAdr")),
                to_float(it.get("lon")),
                to_float(it.get("lat")),
                region.key,
                now_iso(),
            ),
        )

    def _aggregate_counts(self, region: Region) -> None:
        """방금 수집한 stores 를 업종 레벨별로 집계해 store_counts 에 적재."""
        from ..util import now_iso

        stamp = now_iso()
        levels = [
            ("lcls", "inds_lcls_cd", "inds_lcls_nm"),
            ("mcls", "inds_mcls_cd", "inds_mcls_nm"),
            ("scls", "inds_scls_cd", "inds_scls_nm"),
        ]
        for level, cd_col, nm_col in levels:
            rows = self.conn.execute(
                f"""
                SELECT adong_cd, {cd_col} AS cd, {nm_col} AS nm, COUNT(*) AS cnt
                FROM stores
                WHERE region_key = ? AND adong_cd IS NOT NULL AND {cd_col} IS NOT NULL
                  AND collected_at = (SELECT MAX(collected_at) FROM stores WHERE region_key = ?)
                GROUP BY adong_cd, {cd_col}, {nm_col}
                """,
                (region.key, region.key),
            ).fetchall()
            for r in rows:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO store_counts
                        (adm_cd, inds_cls_cd, inds_cls_nm, level, store_count, region_key, collected_at)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (r["adong_cd"], r["cd"], r["nm"], level, r["cnt"], region.key, stamp),
                )
        self.conn.commit()

    # ------------------------------------------------------------------
    def _check_header(self, payload: object, signgu_cd: str) -> None:
        if not isinstance(payload, dict):
            raise ApiError(f"예상치 못한 응답형식 (시군구 {signgu_cd}): {str(payload)[:200]}")
        header = payload.get("header") or {}
        code = str(header.get("resultCode", "")).strip()
        if code and code not in ("00", "0"):
            raise ApiError(
                f"상가정보 API 오류 (시군구 {signgu_cd}): {code} {header.get('resultMsg')}"
            )
