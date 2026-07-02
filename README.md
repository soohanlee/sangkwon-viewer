# 상권분석 데이터 수집기 (sangkwon-collector)

공공 API에서 **수요·경쟁·비용·상권** 데이터를 모아 **SQLite**에 정규화 적재하고, **JSON/CSV**로 내보내는 수집 프레임워크입니다. API 키만 채우면 `시` 단위로 데이터를 모읍니다.

## 수집 데이터 매핑

| 축 | 데이터 | 소스 | 수집기(source) | 적재 테이블 |
|----|--------|------|----------------|-------------|
| 수요 | 인구·가구·연령 | 통계청 SGIS | `sgis` | `demographics`, `demographics_age` |
| 수요 | 소득/소비 | SGIS 통계주제도 | `sgis` | `income` |
| 경쟁 | 점포수·업종·밀도 | 공공데이터포털 상가정보 (15012005/15083033) | `store_info` | `stores`, `store_counts` |
| 비용 | 상가 실거래(매매·전월세) | 국토부 실거래가 | `molit` | `real_estate` |
| 상권 | 유동인구·추정매출·점포·폐업률 | 서울 골목상권 분석서비스(서울 한정) | `seoul_golmok` | `commercial_analysis`, `trdar_area` |
| 상권 | (전국 대안) 유동인구·매출 | 소상공인365 — 공개 API 없음(보류) | `sbiz365` | `commercial_analysis` |

## 빠른 시작

```bash
# 1) 의존성 설치 (uv 사용)
uv sync

# 2) API 키 설정
cp .env.example .env      # 그리고 발급받은 키 입력
uv run sangkwon doctor    # 키 설정 점검

# 3) DB 초기화 + 지역 확인
uv run sangkwon init-db
uv run sangkwon regions

# 4) 수집 (예: 성남시 전체)
uv run sangkwon collect-all --region seongnam
uv run sangkwon status

# 5) 내보내기
uv run sangkwon export --region seongnam --format both
#   → data/exports/sangkwon_seongnam.json
#   → data/exports/csv_seongnam/*.csv
```

개별 소스만 수집:
```bash
uv run sangkwon collect store_info --region seongnam
uv run sangkwon collect molit      --region seongnam --months 6
uv run sangkwon collect sgis       --region seongnam
```

## 지역 추가 (config/regions.json)

```jsonc
"seongnam": {
  "name": "경기도 성남시",
  "sido_code": "41",
  "sgis_adm_cd": "41131",
  "sigungu": [                       // 국토부 실거래가용 5자리 LAWD(법정동) 시군구코드
    { "code": "41131", "name": "성남시 수정구" },
    { "code": "41133", "name": "성남시 중원구" },
    { "code": "41135", "name": "성남시 분당구" }
  ],
  "sgis_codes": ["31021", "31022", "31023"],  // SGIS 시군구코드 (행안부와 다름!)
  "adong_codes": []                  // (선택) sbiz365용. 상가정보는 sigungu 코드로 동작하므로 불필요
}
```

> **SGIS 코드 찾는 법**: SGIS는 시도 코드부터 행안부와 다릅니다(경기=31, 부산=21 …). `addr/stage` API 로 조회하세요.
> 예) 인증 후 `https://sgisapi.kostat.go.kr/OpenAPI3/addr/stage.json?accessToken=&cd=31` → 경기 시군구 목록.

## 데이터 저장 구조

- **원본 응답**: `data/raw/<source>/<region>/<label>_<timestamp>.json` 으로 그대로 보관 (감사/재처리용)
- **정규화 데이터**: `data/sangkwon.sqlite` 의 테이블에 적재
- **수집 이력**: `collection_runs` 테이블 (소스·지역·시각·상태·건수·에러메시지)
- 모든 데이터 행에 `region_key` 와 `collected_at` 이 붙어 여러 번 수집해도 이력이 남습니다. 최신값은 `MAX(collected_at)` 로 조회.

## 코드 체계 주의 ⚠

- **국토부 실거래가**: 5자리 **법정동 시군구코드(LAWD_CD)** 사용 → `sigungu[].code` (예: 강남구 `11680`)
- **SGIS**: 통계청 자체 **행정구역코드** 사용 → `sgis_codes` (예: 강남구 `11230`, 경기=시도31). **시도 코드부터 행안부와 다름**
- **상가정보/소상공인365**: 행안부 **행정동코드** 사용 → `adong_codes`

세 체계가 서로 달라(같은 강남구도 LAWD 11680 ≠ SGIS 11230) **소스 간 조인 시 행정동명 기준 매핑**이 필요합니다. SGIS 코드는 `addr/stage` API로, 행안부 행정동코드는 행정표준코드관리시스템(code.go.kr)에서 확인하세요.

> 실측 검증 완료: 강남구 SGIS 수집 시 22개 행정동의 인구·가구·평균연령이 정상 적재됨. SGIS API 서버가 `sgisapi.kostat.go.kr` → `sgisapi.mods.go.kr` 로 이전되어 302 리다이렉트를 자동 추적하도록 처리됨.

## 환경 변수 (.env)

| 변수 | 설명 |
|------|------|
| `DATA_GO_KR_SERVICE_KEY` | 공공데이터포털 상가정보 키 (Decoding 키) |
| `SGIS_CONSUMER_KEY` / `SGIS_CONSUMER_SECRET` | 통계청 SGIS 키 |
| `MOLIT_SERVICE_KEY` | 국토부 실거래가 키 (비우면 공공데이터포털 키 재사용) |
| `SBIZ365_SERVICE_KEY` / `SBIZ365_BASE_URL` / `SBIZ365_ENDPOINT` | 소상공인365 (스펙 확정 후 주입) |
| `SGIS_STAT_YEAR` | SGIS 통계 기준연도 (기본 2022) |
| `SANGKWON_DB_PATH` / `SANGKWON_DATA_DIR` | DB·데이터 경로 재정의 |

## 구현 상태 / 검증 메모

실제 키로 **강남구 기준 end-to-end 검증 완료** (2026-06-18):

| 수집기 | 상태 | 검증 결과 |
|--------|------|-----------|
| `sgis` (인구/가구) | ✅ 동작 | 22개 행정동 인구·가구·평균연령 적재 |
| `molit` (상업용 매매) | ✅ 동작 | 3개월 146건, 거래금액·면적·용도·건축년도 적재 |
| `store_info` (상가) | ✅ 동작 | `divId=signguCd` 로 시군구 전체 조회(강남구 64,239건), 업종별 집계 |
| `seoul_golmok` (상권, 서울) | ✅ 로직 검증 | 상권영역으로 자치구 필터 → 유동인구·추정매출·점포·폐업률 적재. 전체 수집은 서울 키 필요 |
| `sbiz365` (상권, 전국) | ⏸ 보류 | 소상공인365 공개 API 없음(파일/리포트형) |

핵심 포인트:
- **상가정보는 행정동코드 불필요** — `divId=signguCd` + 시군구코드(`sigungu[].code`)로 시군구 전체를 받고, 각 레코드의 `adongCd` 로 행정동별 집계를 만듭니다. 전체 수집이 부담되면 `--max-pages` 로 제한.
- **국토부 "전월세"는 공개 API가 없음** — 상업업무용은 **매매만** 수집됩니다. `--with-rent` 를 줘도 500이 나며 매매 수집은 정상 진행됩니다(부분 성공 처리).
- **SGIS 서버 도메인 이전**(`kostat.go.kr`→`mods.go.kr`)은 302 자동 추적으로 처리됨.
- `sbiz365`(유동인구·폐업률·매출)는 공개 오픈API가 아니라 파일데이터/대화형 리포트라 자동수집 부적합. 서울이면 [서울 열린데이터광장 골목상권](https://data.seoul.go.kr)으로 대체 가능. 별도 API를 확보하면 `SBIZ365_BASE_URL`/`SBIZ365_ENDPOINT` 주입 후 `INDICATOR_FIELDS` 매핑만 맞추면 됩니다.
- 키 없이도 `init-db / regions / doctor / status / export` 는 동작합니다.

### 키 점검 (ping)
```bash
uv run python -m sangkwon.cli ping     # 발급 키가 실제로 동작하는지 라이브 확인
```
data.go.kr 키는 활용신청 "승인" 후에도 실동작까지 시간차가 있을 수 있습니다(401 → 잠시 후 정상).
