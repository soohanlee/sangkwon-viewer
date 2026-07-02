"""상권분석 DB 뷰어 - 읽기전용 FastAPI 백엔드.

data/sangkwon.sqlite 를 읽어 프론트엔드에 다음을 제공한다.
  GET /api/tables                 -> 테이블 목록 + 컬럼/필터 메타
  GET /api/options/{table}/{col}  -> 특정 컬럼의 distinct 값 (셀렉트 필터용)
  GET /api/summary                -> 대시보드용 요약 통계
  GET /api/data/{table}           -> 필터 + 정렬 + 페이지네이션된 행

보안: 테이블/컬럼명은 모두 아래 TABLES 설정과 실제 스키마로 화이트리스트 검증하고,
      값은 항상 파라미터 바인딩으로만 넘긴다 (SQL 인젝션 차단).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "sangkwon.sqlite"

# 컬럼 한글 라벨
LABELS: dict[str, str] = {
    "bizes_id": "상가업소번호", "bizes_nm": "상호명", "branch_nm": "지점명",
    "inds_lcls_nm": "업종 대분류", "inds_mcls_nm": "업종 중분류", "inds_scls_nm": "업종 소분류",
    "inds_lcls_cd": "대분류코드", "inds_mcls_cd": "중분류코드", "inds_scls_cd": "소분류코드",
    "adong_cd": "행정동코드", "adong_nm": "행정동", "ldong_cd": "법정동코드",
    "road_addr": "도로명주소", "lon": "경도", "lat": "위도",
    "region_key": "지역", "collected_at": "수집시각",
    "adm_cd": "행정동코드", "adm_nm": "행정동명", "sido": "시도", "sigungu": "시군구코드",
    "dong": "동",
    "indicator": "지표", "period": "기준시점", "value": "값", "unit": "단위",
    "year": "연도", "population": "총인구", "households": "가구수", "avg_age": "평균연령",
    "inds_cls_cd": "업종코드", "inds_cls_nm": "업종", "level": "분류단계", "store_count": "점포수",
    "lawd_cd": "시군구코드", "deal_ym": "거래연월", "trade_type": "거래구분",
    "building_type": "건물유형", "building_nm": "건물명", "dong_nm": "동",
    "use_area": "면적(㎡)", "floor": "층", "deal_amount": "매매금액(만원)",
    "deposit": "보증금(만원)", "monthly_rent": "월세(만원)", "build_year": "건축년도",
    "trdar_cd": "상권코드", "trdar_nm": "상권명", "trdar_se_nm": "상권구분",
    "signgu_cd": "자치구코드", "signgu_nm": "자치구", "adstrd_cd": "행정동코드",
    "adstrd_nm": "행정동", "x": "X좌표", "y": "Y좌표",
    "id": "ID", "source": "출처", "started_at": "시작", "finished_at": "종료",
    "status": "상태", "record_count": "건수", "raw_path": "원본경로", "message": "메시지",
}

REGION_LABELS = {
    "gangnam": "강남구",
    "suwon": "수원시", "seongnam": "성남시", "uijeongbu": "의정부시", "anyang": "안양시",
    "bucheon": "부천시", "gwangmyeong": "광명시", "pyeongtaek": "평택시", "dongducheon": "동두천시",
    "ansan": "안산시", "goyang": "고양시", "gwacheon": "과천시", "guri": "구리시",
    "namyangju": "남양주시", "osan": "오산시", "siheung": "시흥시", "gunpo": "군포시",
    "uiwang": "의왕시", "hanam": "하남시", "yongin": "용인시", "paju": "파주시",
    "icheon": "이천시", "anseong": "안성시", "gimpo": "김포시", "hwaseong": "화성시",
    "gwangju_gg": "광주시", "yangju": "양주시", "pocheon": "포천시", "yeoju": "여주시",
    "yeoncheon": "연천군", "gapyeong": "가평군", "yangpyeong": "양평군",
}

# 테이블별 메타: 라벨 / 노출컬럼순서 / 검색(LIKE)컬럼 / select필터 / range필터 / 기본정렬
TABLES: dict[str, dict[str, Any]] = {
    "stores": {
        "label": "상가업소", "icon": "🏪",
        "columns": ["bizes_nm", "branch_nm", "inds_lcls_nm", "inds_mcls_nm",
                    "inds_scls_nm", "adong_nm", "road_addr", "region_key"],
        "search": ["bizes_nm", "road_addr", "adong_nm"],
        "selects": ["region_key", "inds_lcls_nm", "adong_nm"],
        "ranges": [],
        "sort": ("bizes_nm", "asc"),
    },
    "store_counts": {
        "label": "업종별 점포수", "icon": "📊",
        "columns": ["adm_cd", "inds_cls_nm", "level", "store_count", "region_key"],
        "search": ["inds_cls_nm"],
        "selects": ["region_key", "level"],
        "ranges": ["store_count"],
        "sort": ("store_count", "desc"),
    },
    "real_estate": {
        "label": "부동산 실거래", "icon": "🏢",
        "columns": ["deal_ym", "trade_type", "building_type", "building_nm", "dong_nm",
                    "use_area", "floor", "deal_amount", "deposit", "monthly_rent",
                    "build_year", "region_key"],
        "search": ["building_nm", "dong_nm"],
        "selects": ["region_key", "trade_type", "building_type", "deal_ym"],
        "ranges": ["deal_amount", "monthly_rent", "use_area"],
        "sort": ("deal_ym", "desc"),
    },
    "commercial_analysis": {
        "label": "상권분석 지표", "icon": "📈",
        "columns": ["adm_cd", "indicator", "period", "value", "unit", "region_key"],
        "search": [],
        "selects": ["region_key", "indicator", "period"],
        "ranges": ["value"],
        "sort": ("adm_cd", "asc"),
    },
    "demographics": {
        "label": "인구·가구", "icon": "👥",
        "columns": ["adm_cd", "year", "population", "households", "avg_age", "region_key"],
        "search": [],
        "selects": ["region_key", "year"],
        "ranges": ["population", "households"],
        "sort": ("population", "desc"),
    },
    "trdar_area": {
        "label": "상권 영역", "icon": "🗺️",
        "columns": ["trdar_nm", "trdar_se_nm", "signgu_nm", "adstrd_nm", "region_key"],
        "search": ["trdar_nm", "adstrd_nm"],
        "selects": ["region_key", "trdar_se_nm", "signgu_nm"],
        "ranges": [],
        "sort": ("trdar_nm", "asc"),
    },
    "regions": {
        "label": "행정동 마스터", "icon": "📍",
        "columns": ["adm_cd", "adm_nm", "sigungu", "dong", "region_key"],
        "search": ["adm_nm", "dong"],
        "selects": ["region_key", "sigungu"],
        "ranges": [],
        "sort": ("adm_cd", "asc"),
    },
    "demographics_age": {
        "label": "연령별 인구", "icon": "🧒",
        "columns": ["adm_cd", "year", "age_group", "population", "region_key"],
        "search": [],
        "selects": ["region_key", "year", "age_group"],
        "ranges": ["population"],
        "sort": ("adm_cd", "asc"),
    },
    "income": {
        "label": "소득·소비", "icon": "💰",
        "columns": ["adm_cd", "year", "indicator", "value", "unit", "region_key"],
        "search": [],
        "selects": ["region_key", "year", "indicator"],
        "ranges": ["value"],
        "sort": ("adm_cd", "asc"),
    },
    "collection_runs": {
        "label": "수집 로그", "icon": "🧾",
        "columns": ["id", "source", "region_key", "started_at", "finished_at",
                    "status", "record_count", "message"],
        "search": ["message"],
        "selects": ["source", "region_key", "status"],
        "ranges": [],
        "sort": ("id", "desc"),
    },
}

app = FastAPI(title="상권분석 DB 뷰어 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# 실제 스키마(컬럼/타입)를 시작 시 1회 캐시
_SCHEMA: dict[str, dict[str, str]] = {}


def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(500, f"DB 파일이 없습니다: {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_schema() -> None:
    conn = get_conn()
    try:
        for tbl in TABLES:
            cols: dict[str, str] = {}
            for row in conn.execute(f'PRAGMA table_info("{tbl}")'):
                # sqlite 타입 -> 단순 분류
                t = (row["type"] or "").upper()
                if "INT" in t:
                    kind = "int"
                elif "REAL" in t or "FLOA" in t or "DOUB" in t:
                    kind = "real"
                else:
                    kind = "text"
                cols[row["name"]] = kind
            _SCHEMA[tbl] = cols
    finally:
        conn.close()


@app.on_event("startup")
def _startup() -> None:
    load_schema()


def _label(col: str) -> str:
    return LABELS.get(col, col)


def _is_numeric(table: str, col: str) -> bool:
    return _SCHEMA.get(table, {}).get(col) in ("int", "real")


@app.get("/api/tables")
def list_tables() -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        out = []
        for name, cfg in TABLES.items():
            if name not in _SCHEMA or not _SCHEMA[name]:
                continue
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            except sqlite3.Error:
                count = 0
            cols = [c for c in cfg["columns"] if c in _SCHEMA[name]]
            filters = []
            for col in cfg["selects"]:
                if col in _SCHEMA[name]:
                    filters.append({"col": col, "label": _label(col), "type": "select"})
            for col in cfg["ranges"]:
                if col in _SCHEMA[name]:
                    filters.append({"col": col, "label": _label(col), "type": "range"})
            out.append({
                "name": name,
                "label": cfg["label"],
                "icon": cfg["icon"],
                "count": count,
                "columns": [{"col": c, "label": _label(c),
                             "numeric": _is_numeric(name, c)} for c in cols],
                "search": [c for c in cfg["search"] if c in _SCHEMA[name]],
                "filters": filters,
                "sort": {"col": cfg["sort"][0], "order": cfg["sort"][1]},
            })
        return out
    finally:
        conn.close()


@app.get("/api/options/{table}/{col}")
def options(table: str, col: str) -> list[dict[str, Any]]:
    if table not in TABLES or col not in _SCHEMA.get(table, {}):
        raise HTTPException(404, "알 수 없는 테이블/컬럼")
    conn = get_conn()
    try:
        rows = conn.execute(
            f'SELECT "{col}" v, COUNT(*) c FROM "{table}" '
            f'WHERE "{col}" IS NOT NULL AND "{col}" != "" '
            f'GROUP BY "{col}" ORDER BY c DESC LIMIT 500'
        ).fetchall()
        out = []
        for r in rows:
            v = r["v"]
            label = REGION_LABELS.get(v, str(v)) if col == "region_key" else str(v)
            out.append({"value": v, "label": label, "count": r["c"]})
        return out
    finally:
        conn.close()


@app.get("/api/summary")
def summary() -> dict[str, Any]:
    conn = get_conn()
    try:
        cards = []
        for name, cfg in TABLES.items():
            if name not in _SCHEMA or not _SCHEMA[name]:
                continue
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            cards.append({"name": name, "label": cfg["label"],
                          "icon": cfg["icon"], "count": count})
        # 지역별 상가 분포
        by_region = []
        for r in conn.execute(
            'SELECT region_key, COUNT(*) c FROM stores GROUP BY region_key ORDER BY c DESC'
        ):
            by_region.append({"key": r["region_key"],
                              "label": REGION_LABELS.get(r["region_key"], r["region_key"]),
                              "count": r["c"]})
        # 업종 대분류 분포 (상위)
        by_industry = []
        for r in conn.execute(
            'SELECT inds_lcls_nm n, COUNT(*) c FROM stores '
            'WHERE inds_lcls_nm IS NOT NULL GROUP BY inds_lcls_nm ORDER BY c DESC LIMIT 10'
        ):
            by_industry.append({"label": r["n"], "count": r["c"]})
        return {"cards": cards, "by_region": by_region, "by_industry": by_industry}
    finally:
        conn.close()


@app.get("/api/data/{table}")
def data(
    request: Request,
    table: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    sort: str | None = None,
    order: str = Query("asc"),
    q: str | None = None,
) -> dict[str, Any]:
    if table not in TABLES:
        raise HTTPException(404, "알 수 없는 테이블")
    cfg = TABLES[table]
    schema = _SCHEMA.get(table, {})
    if not schema:
        raise HTTPException(404, "테이블 스키마 없음")

    where: list[str] = []
    params: list[Any] = []

    # 1) 컬럼별 동등/범위 필터 (쿼리스트링 자유 파라미터)
    reserved = {"page", "page_size", "sort", "order", "q"}
    for key in request.query_params.keys():
        if key in reserved:
            continue
        # 범위: col__min / col__max
        base, _, suffix = key.partition("__")
        if suffix in ("min", "max"):
            if base in cfg["ranges"] and base in schema:
                val = request.query_params.get(key)
                if val not in (None, ""):
                    op = ">=" if suffix == "min" else "<="
                    where.append(f'"{base}" {op} ?')
                    params.append(val)
            continue
        # 동등 (다중 값 지원: ?col=a&col=b -> IN)
        if key in cfg["selects"] and key in schema:
            vals = [v for v in request.query_params.getlist(key) if v != ""]
            if vals:
                placeholders = ",".join("?" * len(vals))
                where.append(f'"{key}" IN ({placeholders})')
                params.extend(vals)

    # 2) 전역 검색 (LIKE OR)
    if q:
        search_cols = [c for c in cfg["search"] if c in schema]
        if search_cols:
            ors = " OR ".join(f'"{c}" LIKE ?' for c in search_cols)
            where.append(f"({ors})")
            params.extend([f"%{q}%"] * len(search_cols))

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    # 정렬 (화이트리스트)
    sort_col = sort if (sort and sort in schema) else cfg["sort"][0]
    sort_order = "DESC" if order.lower() == "desc" else "ASC"

    conn = get_conn()
    try:
        total = conn.execute(
            f'SELECT COUNT(*) FROM "{table}"{where_sql}', params
        ).fetchone()[0]
        cols = [c for c in cfg["columns"] if c in schema]
        col_sql = ", ".join(f'"{c}"' for c in cols)
        offset = (page - 1) * page_size
        rows = conn.execute(
            f'SELECT {col_sql} FROM "{table}"{where_sql} '
            f'ORDER BY "{sort_col}" {sort_order} LIMIT ? OFFSET ?',
            [*params, page_size, offset],
        ).fetchall()
        data_rows = []
        for r in rows:
            d = dict(r)
            if "region_key" in d:
                d["_region_label"] = REGION_LABELS.get(d["region_key"], d["region_key"])
            data_rows.append(d)
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
            "columns": [{"col": c, "label": _label(c),
                         "numeric": _is_numeric(table, c)} for c in cols],
            "rows": data_rows,
        }
    finally:
        conn.close()


@app.exception_handler(sqlite3.Error)
def sqlite_error_handler(request: Request, exc: sqlite3.Error) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": f"DB 오류: {exc}"})
