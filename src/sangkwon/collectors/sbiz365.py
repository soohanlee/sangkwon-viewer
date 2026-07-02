"""소상공인365 / 소상공인 상권정보시스템 - 상권분석 지표 (상권 축).

유동인구 · 폐업률 · 업력 · 추정매출 등 동단위 상권 지표를 수집한다.

⚠ 이 소스는 공개 오픈API 스펙이 기관/구독에 따라 달라 확정 엔드포인트를 고정하지 않았다.
   실제 발급받은 API 의 베이스 URL/엔드포인트/응답필드를 아래 env 로 주입하면 동작한다.
     SBIZ365_BASE_URL, SBIZ365_ENDPOINT, SBIZ365_SERVICE_KEY
   응답이 표준 공공데이터포털 JSON({body:{items:[...]}}) 형태라고 가정하고 파싱한다.
   필드명이 다르면 _map_item() 만 수정하면 된다.
"""
from __future__ import annotations

import os

from ..http import ApiError, HttpClient
from ..settings import Region
from ..util import clean, save_raw, to_float
from .base import BaseCollector, CollectResult

BASE = os.getenv("SBIZ365_BASE_URL", "")
ENDPOINT = os.getenv("SBIZ365_ENDPOINT", "")

# 응답 필드 -> 표준 지표명 매핑 (실제 스펙에 맞게 조정)
INDICATOR_FIELDS = {
    "flpop_co": "유동인구",
    "clsbiz_rt": "폐업률",
    "bsn_yy": "평균업력",
    "estm_sales": "추정매출",
}


class Sbiz365Collector(BaseCollector):
    source = "sbiz365"
    required_keys = ("sbiz365",)

    def collect(self, region: Region, http: HttpClient, result: CollectResult) -> None:
        if not (BASE and ENDPOINT):
            result.status = "error"
            result.message = (
                "소상공인365 엔드포인트 미설정. 발급받은 API 의 SBIZ365_BASE_URL / "
                "SBIZ365_ENDPOINT 를 .env 에 추가하세요. (스펙 확정 후 _map_item 조정)"
            )
            return

        adong_codes = region.adong_codes
        if not adong_codes:
            result.status = "error"
            result.message = "행정동 코드(adong_codes)가 필요합니다. store_info 수집 후 재시도하거나 regions.json 에 채우세요."
            return

        count = 0
        for adong in adong_codes:
            count += self._fetch(region, http, result, adong)
        result.record_count = count
        self.conn.commit()

    def _fetch(self, region: Region, http: HttpClient, result: CollectResult, adong_cd: str) -> int:
        params = {
            "serviceKey": self.keys.sbiz365,
            "type": "json",
            "divId": "adongCd",
            "key": adong_cd,
        }
        payload = http.get_json(f"{BASE.rstrip('/')}/{ENDPOINT.lstrip('/')}", params=params)
        result.raw_paths.append(str(save_raw(self.source, region.key, f"dong_{adong_cd}", payload)))
        items = self._extract_items(payload)
        n = 0
        for it in items:
            n += self._map_item(region, adong_cd, it)
        return n

    def _map_item(self, region: Region, adong_cd: str, it: dict) -> int:
        from ..util import now_iso

        stamp = now_iso()
        period = clean(it.get("stdr_ym") or it.get("baseYm"))
        wrote = 0
        for field, indicator in INDICATOR_FIELDS.items():
            if field not in it:
                continue
            self.conn.execute(
                """
                INSERT OR REPLACE INTO commercial_analysis
                    (adm_cd, indicator, period, value, unit, region_key, collected_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (adong_cd, indicator, period, to_float(it.get(field)), None, region.key, stamp),
            )
            wrote += 1
        return wrote

    @staticmethod
    def _extract_items(payload: object) -> list[dict]:
        if not isinstance(payload, dict):
            raise ApiError(f"예상치 못한 응답형식: {str(payload)[:200]}")
        body = payload.get("body") or payload.get("response", {}).get("body") or {}
        items = body.get("items") or []
        if isinstance(items, dict):
            items = items.get("item") or [items]
        return items if isinstance(items, list) else [items]
