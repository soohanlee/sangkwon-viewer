-- =====================================================================
-- 상권분석 데이터베이스 DDL (PostgreSQL)
-- 현재 SQLite(data/sangkwon.sqlite) 스키마를 정식 RDBMS로 옮긴 버전
-- 작성: 2026-06-22
--
-- 코드 체계 주의:
--   adm_cd      = 행정동코드(소스마다 체계 다름, 조인은 행정동명 기준 권장)
--   lawd_cd     = 국토부 법정동 시군구코드(5자리)
--   region_key  = 프로젝트 내부 지역 키(예: gangnam, seongnam)
--   모든 행에 collected_at 부여 → 여러 번 수집 시 이력 보존, 최신값은 MAX(collected_at)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0) 지역 마스터
-- ---------------------------------------------------------------------
CREATE TABLE regions (
    adm_cd        TEXT PRIMARY KEY,          -- 행정동 코드
    adm_nm        TEXT,                      -- 행정동 전체 경로명
    sido          TEXT,
    sigungu       TEXT,
    dong          TEXT,
    region_key    TEXT NOT NULL,
    lon           DOUBLE PRECISION,
    lat           DOUBLE PRECISION,
    collected_at  TIMESTAMPTZ
);
CREATE INDEX idx_regions_region_key ON regions (region_key);

-- ---------------------------------------------------------------------
-- 1) 수요 — 인구 / 가구 / 연령 / 소득 (통계청 SGIS)
-- ---------------------------------------------------------------------
CREATE TABLE demographics (
    adm_cd        TEXT NOT NULL,
    year          INTEGER NOT NULL,
    population    INTEGER,                   -- 총인구
    households    INTEGER,                   -- 가구수
    avg_age       NUMERIC(5,2),
    region_key    TEXT,
    collected_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (adm_cd, year, collected_at)
);
CREATE INDEX idx_demographics_region ON demographics (region_key);

CREATE TABLE demographics_age (
    adm_cd        TEXT NOT NULL,
    year          INTEGER NOT NULL,
    age_group     TEXT NOT NULL,             -- 예: 0-9, 10-19 ...
    population    INTEGER,
    region_key    TEXT,
    collected_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (adm_cd, year, age_group, collected_at)
);
CREATE INDEX idx_demo_age_region ON demographics_age (region_key);

CREATE TABLE income (
    adm_cd        TEXT NOT NULL,
    year          INTEGER NOT NULL,
    indicator     TEXT NOT NULL,             -- 소득/소비 지표명
    value         NUMERIC,
    unit          TEXT,
    region_key    TEXT,
    collected_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (adm_cd, year, indicator, collected_at)
);
CREATE INDEX idx_income_region ON income (region_key);

-- ---------------------------------------------------------------------
-- 2) 경쟁 — 개별 점포 / 업종별 집계 (소상공인 상가정보)
-- ---------------------------------------------------------------------
CREATE TABLE stores (
    bizes_id      TEXT NOT NULL,             -- 상가업소번호
    bizes_nm      TEXT,                      -- 상호명
    branch_nm     TEXT,
    inds_lcls_cd  TEXT,  inds_lcls_nm  TEXT, -- 업종 대분류
    inds_mcls_cd  TEXT,  inds_mcls_nm  TEXT, -- 중분류
    inds_scls_cd  TEXT,  inds_scls_nm  TEXT, -- 소분류
    adong_cd      TEXT,  adong_nm      TEXT, -- 행정동
    ldong_cd      TEXT,                      -- 법정동
    road_addr     TEXT,
    lon           DOUBLE PRECISION,
    lat           DOUBLE PRECISION,
    region_key    TEXT,
    collected_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (bizes_id, collected_at)
);
CREATE INDEX idx_stores_region  ON stores (region_key);
CREATE INDEX idx_stores_adong   ON stores (adong_cd);
CREATE INDEX idx_stores_lcls    ON stores (inds_lcls_cd);

CREATE TABLE store_counts (
    adm_cd        TEXT NOT NULL,
    inds_cls_cd   TEXT NOT NULL,
    inds_cls_nm   TEXT,
    level         TEXT NOT NULL,             -- lcls | mcls | scls
    store_count   INTEGER,
    region_key    TEXT,
    collected_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (adm_cd, inds_cls_cd, level, collected_at)
);
CREATE INDEX idx_store_counts_region ON store_counts (region_key);

-- ---------------------------------------------------------------------
-- 3) 비용 — 상가 실거래 (국토부) + 임대료/권리금 평균·추이 (다운로드)
-- ---------------------------------------------------------------------
CREATE TABLE real_estate (
    id            BIGSERIAL PRIMARY KEY,
    lawd_cd       TEXT NOT NULL,             -- 시군구코드(5)
    deal_ym       TEXT NOT NULL,             -- 거래 연월 YYYYMM
    trade_type    TEXT NOT NULL,             -- trade(매매) | rent(전월세)
    building_type TEXT,                      -- 건물유형(상업업무용 등)
    building_nm   TEXT,
    dong_nm       TEXT,
    use_area      NUMERIC(10,2),             -- 면적(㎡)
    floor         TEXT,
    deal_amount   BIGINT,                    -- 거래금액(만원, 매매)
    deposit       BIGINT,                    -- 보증금(만원, 전월세)
    monthly_rent  BIGINT,                    -- 월세(만원)
    build_year    TEXT,
    region_key    TEXT,
    collected_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_re_region   ON real_estate (region_key);
CREATE INDEX idx_re_lawd_ym  ON real_estate (lawd_cd, deal_ym);

-- 임대료·권리금 "평균/추이" (OpenAPI 아님 → 파일 다운로드로 적재)
-- 서울시 상가임대차, 한국부동산원 R-ONE, 공공데이터포털 CSV, KOSIS 등
CREATE TABLE rent_stats (
    id            BIGSERIAL PRIMARY KEY,
    region_key    TEXT,
    area_code     TEXT,                      -- 시군구/상권 등 집계 단위 코드
    area_name     TEXT,                      -- 집계 단위 명
    period        TEXT NOT NULL,             -- 기준 시점(YYYY / YYYYQn 등)
    indicator     TEXT NOT NULL,             -- 평균임대료 | 권리금 | 공실률 ...
    value         NUMERIC,
    unit          TEXT,                      -- 원/㎡, 만원, % 등
    source        TEXT,                      -- seoul_sftc | reb_rone | kosis | data_go_kr
    collected_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (area_code, period, indicator, source, collected_at)
);
CREATE INDEX idx_rent_stats_region ON rent_stats (region_key);

-- ---------------------------------------------------------------------
-- 4) 상권 — 유동인구/매출/폐업률 지표 + 상권영역 (서울 골목상권)
-- ---------------------------------------------------------------------
CREATE TABLE commercial_analysis (
    adm_cd        TEXT NOT NULL,
    indicator     TEXT NOT NULL,             -- 유동인구 | 추정매출 | 폐업률 ...
    period        TEXT NOT NULL,             -- 기준 분기/시점
    value         NUMERIC,
    unit          TEXT,
    region_key    TEXT,
    collected_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (adm_cd, indicator, period, collected_at)
);
CREATE INDEX idx_comm_region ON commercial_analysis (region_key);

CREATE TABLE trdar_area (
    trdar_cd      TEXT PRIMARY KEY,          -- 상권코드
    trdar_nm      TEXT,                      -- 상권명
    trdar_se_nm   TEXT,                      -- 상권구분(골목/발달/전통시장/관광특구)
    signgu_cd     TEXT,  signgu_nm   TEXT,   -- 자치구
    adstrd_cd     TEXT,  adstrd_nm   TEXT,   -- 행정동(조인용)
    x             DOUBLE PRECISION,
    y             DOUBLE PRECISION,
    region_key    TEXT,
    collected_at  TIMESTAMPTZ
);
CREATE INDEX idx_trdar_region ON trdar_area (region_key);
CREATE INDEX idx_trdar_adstrd ON trdar_area (adstrd_cd);

-- ---------------------------------------------------------------------
-- 5) 급지 결과 — SV 기준으로 산출한 등급 (POC 산출물)
-- ---------------------------------------------------------------------
CREATE TABLE grade_result (
    id            BIGSERIAL PRIMARY KEY,
    region_key    TEXT,
    adm_cd        TEXT,                      -- 또는 trdar_cd (집계 단위)
    area_name     TEXT,
    total_score   NUMERIC(6,2),             -- 종합 점수
    grade         TEXT,                      -- S | A | B | C
    ruleset_id    TEXT,                      -- 적용한 SV 기준(버전) 식별자
    detail        JSONB,                     -- 지표별 점수/가중치 등 상세
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_grade_region ON grade_result (region_key);

-- ---------------------------------------------------------------------
-- 6) 수집 이력
-- ---------------------------------------------------------------------
CREATE TABLE collection_runs (
    id            BIGSERIAL PRIMARY KEY,
    source        TEXT NOT NULL,             -- store_info | sgis | molit | seoul_golmok | rent_file ...
    region_key    TEXT NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL,
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL,             -- running | success | partial | error
    record_count  INTEGER DEFAULT 0,
    raw_path      TEXT,
    message       TEXT
);
CREATE INDEX idx_runs_source_region ON collection_runs (source, region_key);
