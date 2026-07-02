"""국토교통부 실거래가 - 상업업무용 부동산 매매/전월세 (비용 축).

공공데이터포털 1613000 그룹.
  매매:   .../RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade
  전월세: .../RTMSDataSvcNrgRent/getRTMSDataSvcNrgRent   (제공 여부는 구독 확인)
  파라미터: serviceKey, LAWD_CD(시군구5자리), DEAL_YMD(YYYYMM), pageNo, numOfRows
  응답: XML (<response><header><body><items><item>...)

수집 대상 월은 CLI --months N (최근 N개월) 또는 --deal-ym YYYYMM[,YYYYMM] 로 지정.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import date

import httpx

from ..http import ApiError, HttpClient
from ..settings import Region
from ..util import clean, save_raw, to_int
from .base import BaseCollector, CollectResult

MOLIT_BASE = os.getenv("MOLIT_BASE_URL", "https://apis.data.go.kr/1613000")
TRADE_PATH = "RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade"
RENT_PATH = "RTMSDataSvcNrgRent/getRTMSDataSvcNrgRent"
NUM_OF_ROWS = 1000


def recent_months(n: int, base: date | None = None) -> list[str]:
    base = base or date.today()
    months: list[str] = []
    y, m = base.year, base.month
    for _ in range(n):
        months.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return months


class MolitCollector(BaseCollector):
    source = "molit"
    required_keys = ("molit",)

    # 상업업무용 '전월세'는 공개 오픈API가 없어 기본 비활성화. (매매만 수집)
    def __init__(self, conn, keys, *, deal_yms: list[str] | None = None, include_rent: bool = False):
        super().__init__(conn, keys)
        self.deal_yms = deal_yms or recent_months(3)
        self.include_rent = include_rent

    def collect(self, region: Region, http: HttpClient, result: CollectResult) -> None:
        count = 0
        partial = False
        for sgg in region.sigungu:
            for ym in self.deal_yms:
                count += self._fetch(region, http, result, sgg.code, ym, TRADE_PATH, "trade")
                if self.include_rent:
                    try:
                        count += self._fetch(
                            region, http, result, sgg.code, ym, RENT_PATH, "rent"
                        )
                    except (ApiError, httpx.HTTPError) as exc:
                        # 전월세 API 미제공(500/401 등)이어도 매매는 계속 수집
                        partial = True
                        result.message = f"전월세 API 건너뜀(상업업무용 전월세는 공개 API 없음): {str(exc)[:120]}"
        result.record_count = count
        if partial:
            result.status = "partial"
        self.conn.commit()

    def _fetch(
        self,
        region: Region,
        http: HttpClient,
        result: CollectResult,
        lawd_cd: str,
        deal_ym: str,
        path: str,
        trade_type: str,
    ) -> int:
        page = 1
        fetched = 0
        while True:
            params = {
                "serviceKey": self.keys.molit,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": deal_ym,
                "pageNo": page,
                "numOfRows": NUM_OF_ROWS,
            }
            resp = http.get(f"{MOLIT_BASE}/{path}", params=params)
            if resp.status_code >= 400:
                raise ApiError(f"MOLIT HTTP {resp.status_code}: {resp.text[:200]}")
            root = self._parse_xml(resp.text)
            self._check_header(root)
            items = root.findall(".//items/item")
            if page == 1:
                result.raw_paths.append(
                    str(save_raw(self.source, region.key, f"{trade_type}_{lawd_cd}_{deal_ym}", resp.text))
                )
            for item in items:
                self._insert(region, item, lawd_cd, deal_ym, trade_type)
                fetched += 1

            total = to_int(self._text(root, ".//totalCount")) or 0
            if page * NUM_OF_ROWS >= total or not items:
                break
            page += 1
        return fetched

    def _insert(self, region: Region, item: ET.Element, lawd_cd: str, deal_ym: str, trade_type: str) -> None:
        from ..util import now_iso, to_float

        g = {child.tag.strip(): (child.text or "").strip() for child in item}

        def pick(*names: str) -> str | None:
            for n in names:
                if n in g and g[n] != "":
                    return g[n]
            return None

        self.conn.execute(
            """
            INSERT INTO real_estate (
                lawd_cd, deal_ym, trade_type, building_type, building_nm, dong_nm,
                use_area, floor, deal_amount, deposit, monthly_rent, build_year,
                region_key, collected_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                lawd_cd,
                deal_ym,
                trade_type,
                clean(pick("buildingUse", "건물주용도", "landUse", "용도지역")),
                clean(pick("건물명", "단지명")),  # 상업용 매매엔 건물명 없음(개인정보) → None 정상
                clean(pick("umdNm", "법정동")),
                to_float(pick("buildingAr", "건물면적", "전용면적")),
                clean(pick("floor", "층")),
                to_int(pick("거래금액", "dealAmount")) if trade_type == "trade" else None,
                to_int(pick("보증금", "보증금액", "deposit")) if trade_type == "rent" else None,
                to_int(pick("월세", "월세금액", "monthlyRent")) if trade_type == "rent" else None,
                clean(pick("buildYear", "건축년도")),
                region.key,
                now_iso(),
            ),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_xml(text: str) -> ET.Element:
        try:
            return ET.fromstring(text)
        except ET.ParseError as exc:
            raise ApiError(f"MOLIT XML 파싱 실패: {text[:200]}") from exc

    @staticmethod
    def _text(root: ET.Element, path: str) -> str | None:
        el = root.find(path)
        return el.text if el is not None else None

    def _check_header(self, root: ET.Element) -> None:
        code = self._text(root, ".//header/resultCode")
        if code is not None and code.strip() not in ("00", "000", "0"):
            msg = self._text(root, ".//header/resultMsg")
            raise ApiError(f"MOLIT API 오류: {code} {msg}")
