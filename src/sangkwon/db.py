"""SQLite 스키마 및 접속 헬퍼.

설계 원칙
- 모든 테이블은 (출처 source, 지역 region_key, 수집시각 collected_at) 메타를 함께 적재해
  여러 번 수집해도 이력이 남도록 한다. 최신값만 보려면 collected_at MAX 로 조회.
- 원본 응답은 data/raw/ 에 JSON 으로 보관하고, 여기엔 정규화된 행만 적재한다.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .settings import DB_PATH

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 수집 실행 로그 ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collection_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,           -- store_info | sgis | molit | sbiz365
    region_key   TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    status       TEXT NOT NULL,           -- running | success | partial | error
    record_count INTEGER DEFAULT 0,
    raw_path     TEXT,
    message      TEXT
);

-- 행정동 마스터 (수요/경쟁 조인 키) -----------------------------------------
CREATE TABLE IF NOT EXISTS regions (
    adm_cd       TEXT PRIMARY KEY,        -- 행정동 코드
    adm_nm       TEXT,                    -- 행정동 명 (전체 경로)
    sido         TEXT,
    sigungu      TEXT,
    dong         TEXT,
    region_key   TEXT,
    lon          REAL,
    lat          REAL,
    collected_at TEXT
);

-- 수요: 인구/가구 (SGIS) ----------------------------------------------------
CREATE TABLE IF NOT EXISTS demographics (
    adm_cd        TEXT NOT NULL,
    year          INTEGER NOT NULL,
    population     INTEGER,               -- 총인구
    households     INTEGER,               -- 가구수
    avg_age        REAL,
    region_key     TEXT,
    collected_at   TEXT,
    PRIMARY KEY (adm_cd, year, collected_at)
);

-- 수요: 연령별 인구 (SGIS) --------------------------------------------------
CREATE TABLE IF NOT EXISTS demographics_age (
    adm_cd        TEXT NOT NULL,
    year          INTEGER NOT NULL,
    age_group     TEXT NOT NULL,          -- 예: 0-9, 10-19 ...
    population     INTEGER,
    region_key     TEXT,
    collected_at   TEXT,
    PRIMARY KEY (adm_cd, year, age_group, collected_at)
);

-- 수요: 소득/소비 (SGIS 통계주제도) -----------------------------------------
CREATE TABLE IF NOT EXISTS income (
    adm_cd        TEXT NOT NULL,
    year          INTEGER NOT NULL,
    indicator     TEXT NOT NULL,          -- 지표명
    value          REAL,
    unit           TEXT,
    region_key     TEXT,
    collected_at   TEXT,
    PRIMARY KEY (adm_cd, year, indicator, collected_at)
);

-- 경쟁: 개별 상가업소 (공공데이터포털 상가정보) -----------------------------
CREATE TABLE IF NOT EXISTS stores (
    bizes_id      TEXT NOT NULL,          -- 상가업소번호
    bizes_nm      TEXT,                   -- 상호명
    branch_nm     TEXT,
    inds_lcls_cd  TEXT,                   -- 업종 대분류 코드
    inds_lcls_nm  TEXT,
    inds_mcls_cd  TEXT,                   -- 중분류
    inds_mcls_nm  TEXT,
    inds_scls_cd  TEXT,                   -- 소분류
    inds_scls_nm  TEXT,
    adong_cd      TEXT,                   -- 행정동코드
    adong_nm      TEXT,
    ldong_cd      TEXT,                   -- 법정동코드
    road_addr     TEXT,
    lon           REAL,
    lat           REAL,
    region_key    TEXT,
    collected_at  TEXT,
    PRIMARY KEY (bizes_id, collected_at)
);

-- 경쟁: 업종별 점포수 집계 (stores 파생) ------------------------------------
CREATE TABLE IF NOT EXISTS store_counts (
    adm_cd        TEXT NOT NULL,
    inds_cls_cd   TEXT NOT NULL,
    inds_cls_nm   TEXT,
    level          TEXT NOT NULL,         -- lcls | mcls | scls
    store_count    INTEGER,
    region_key     TEXT,
    collected_at   TEXT,
    PRIMARY KEY (adm_cd, inds_cls_cd, level, collected_at)
);

-- 비용: 부동산 실거래 (국토부) ----------------------------------------------
CREATE TABLE IF NOT EXISTS real_estate (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lawd_cd       TEXT NOT NULL,          -- 시군구코드(5)
    deal_ym       TEXT NOT NULL,          -- 거래 연월 YYYYMM
    trade_type    TEXT NOT NULL,          -- trade(매매) | rent(전월세)
    building_type TEXT,                   -- 건물유형(상업업무용 등)
    building_nm   TEXT,
    dong_nm       TEXT,
    use_area      REAL,                   -- 전용/건물 면적(㎡)
    floor          TEXT,
    deal_amount    INTEGER,               -- 거래금액(만원, 매매)
    deposit        INTEGER,               -- 보증금(만원, 전월세)
    monthly_rent   INTEGER,               -- 월세(만원)
    build_year     TEXT,
    region_key     TEXT,
    collected_at   TEXT
);

-- 상권: 서울 골목상권 영역 마스터 (상권코드 ↔ 자치구/행정동/좌표) -----------
CREATE TABLE IF NOT EXISTS trdar_area (
    trdar_cd      TEXT PRIMARY KEY,       -- 상권코드
    trdar_nm      TEXT,                   -- 상권명
    trdar_se_nm   TEXT,                   -- 상권구분(골목/발달/전통시장/관광특구)
    signgu_cd     TEXT,                   -- 자치구코드
    signgu_nm     TEXT,
    adstrd_cd     TEXT,                   -- 행정동코드 (다른 소스와 조인용)
    adstrd_nm     TEXT,
    x             REAL,
    y             REAL,
    region_key    TEXT,
    collected_at  TEXT
);

-- 상권: 상권분석 지표 (서울 골목상권 / 소상공인365 등) ----------------------
CREATE TABLE IF NOT EXISTS commercial_analysis (
    adm_cd        TEXT NOT NULL,
    indicator     TEXT NOT NULL,          -- 유동인구 | 폐업률 | 업력 | 추정매출 ...
    period         TEXT,                  -- 기준 시점
    value          REAL,
    unit           TEXT,
    region_key     TEXT,
    collected_at   TEXT,
    PRIMARY KEY (adm_cd, indicator, period, collected_at)
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | None = None) -> Path:
    db_path = Path(path) if path else DB_PATH
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return db_path


@contextmanager
def run_logger(conn: sqlite3.Connection, source: str, region_key: str) -> Iterator[int]:
    """수집 실행을 collection_runs 에 기록하는 컨텍스트 매니저. run_id 를 yield."""
    from .util import now_iso

    cur = conn.execute(
        "INSERT INTO collection_runs (source, region_key, started_at, status) "
        "VALUES (?, ?, ?, 'running')",
        (source, region_key, now_iso()),
    )
    conn.commit()
    run_id = cur.lastrowid
    try:
        yield run_id
    except Exception as exc:  # noqa: BLE001 - 실패도 로그에 남긴다
        conn.execute(
            "UPDATE collection_runs SET finished_at=?, status='error', message=? WHERE id=?",
            (now_iso(), str(exc)[:500], run_id),
        )
        conn.commit()
        raise


def finalize_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    record_count: int,
    raw_path: str | None = None,
    message: str | None = None,
) -> None:
    from .util import now_iso

    conn.execute(
        "UPDATE collection_runs SET finished_at=?, status=?, record_count=?, raw_path=?, message=? "
        "WHERE id=?",
        (now_iso(), status, record_count, raw_path, message, run_id),
    )
    conn.commit()
