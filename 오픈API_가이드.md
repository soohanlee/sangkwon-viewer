# 상권분석 오픈 API 가이드

교촌 상권분석 POC의 데이터를 수집하기 위해 실제로 사용한 공개(오픈) API의 **발급 → 호출 → 응답 처리** 전 과정을 정리한 실무 문서입니다. 각 API의 인증 방식, 엔드포인트, 파라미터, 응답 필드, 코드 체계 주의점, 그리고 이 프로젝트의 수집기(`src/sangkwon/collectors/`)와의 대응 관계를 함께 담았습니다.

- 최종 업데이트: 2026-07-01
- 대상 데이터 축: 수요(인구·가구) · 경쟁(점포·업종) · 비용(실거래) · 상권(유동인구·매출·폐업률)

---

## 0. 한눈에 보기

| # | API | 기관 | 인증 방식 | 응답 | 수집기 | 상태 |
|---|-----|------|-----------|------|--------|------|
| 1 | 상가(상권)정보 | 소상공인시장진흥공단 (공공데이터포털) | 서비스키 | JSON | `store_info` | ✅ 검증 완료 |
| 2 | SGIS 오픈API | 통계청 | 토큰(키+시크릿) | JSON | `sgis` | ✅ 검증 완료 |
| 3 | 상업업무용 실거래가 | 국토교통부 (공공데이터포털) | 서비스키 | XML | `molit` | ✅ 검증 완료 (매매만) |
| 4 | 골목상권 분석서비스 | 서울 열린데이터광장 | 인증키(URL 삽입) | JSON | `seoul_golmok` | ✅ 로직 검증 (서울 한정) |
| 5 | 소상공인365 상권분석 | 소상공인시장진흥공단 | (미확정) | — | `sbiz365` | ⏸ 보류 (공개 API 없음) |

> 핵심 주의: **세 기관이 서로 다른 지역 코드 체계를 씁니다.** 같은 강남구라도 국토부(LAWD) `11680`, SGIS `11230`, 행안부 행정동코드가 모두 다릅니다. 소스 간 조인은 코드가 아니라 **행정동명 기준 매핑**으로 해야 합니다. (자세한 내용은 §6)

---

## 1. 소상공인시장진흥공단 상가(상권)정보 — `store_info`

**경쟁 축.** 시군구 단위로 개별 상가업소 목록(점포명·업종·좌표·주소)을 받아, 각 레코드의 행정동코드로 업종별 점포수를 집계합니다. 전국 약 74만 점포 규모.

### 1.1 발급

1. [공공데이터포털(data.go.kr)](https://www.data.go.kr) 회원가입 후 로그인.
2. "소상공인시장진흥공단_상가(상권)정보" 검색 → 데이터 번호 **15012005 / 15083033** 활용신청.
3. 마이페이지 > 개발계정 > **일반 인증키(Decoding)** 값을 복사.
4. `.env` 의 `DATA_GO_KR_SERVICE_KEY` 에 붙여넣기.

> ⚠️ Encoding 키가 아니라 **Decoding 키**를 넣으세요. `httpx` 가 파라미터를 자동 인코딩하므로 Encoding 키를 넣으면 이중 인코딩되어 인증에 실패합니다.
> ⚠️ 활용신청 "승인" 직후에도 실제 호출까지 시간차가 있어 잠시 401이 날 수 있습니다(수십 분~1시간).

### 1.2 엔드포인트

```
GET https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong
```

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `serviceKey` | 발급키 | data.go.kr Decoding 키 |
| `divId` | `signguCd` | 조회 기준 구분 (시군구 단위) |
| `key` | 시군구코드 5자리 | 예: 강남구 `11680` |
| `pageNo` | 1, 2, … | 페이지 번호 |
| `numOfRows` | `1000` | 페이지당 건수 |
| `type` | `json` | 응답 형식 |

**페이징:** `body.totalCount` 를 읽어 `pageNo * numOfRows >= totalCount` 가 될 때까지 페이지를 증가시킵니다. (강남구 기준 약 6.4만 건 → 65페이지)

### 1.3 응답 (JSON)

```jsonc
{
  "header": { "resultCode": "00", "resultMsg": "NORMAL SERVICE" },
  "body": {
    "items": [
      {
        "bizesId": "MA010120200817...",   // 상가업소번호(PK)
        "bizesNm": "교촌치킨강남점",        // 상호명
        "brchNm": "강남점",                // 지점명
        "indsLclsCd": "Q",  "indsLclsNm": "음식",       // 대분류
        "indsMclsCd": "Q12","indsMclsNm": "닭/오리요리", // 중분류
        "indsSclsCd": "Q12A01","indsSclsNm": "후라이드/양념치킨", // 소분류
        "adongCd": "1168010100", "adongNm": "역삼동",   // 행정동코드/명
        "ldongCd": "1168010100",                        // 법정동코드
        "rdnmAdr": "서울特別市 강남구 ...",             // 도로명주소
        "lon": "127.03...", "lat": "37.49..."           // 경위도
      }
    ],
    "totalCount": 64239, "numOfRows": 1000, "pageNo": 1
  }
}
```

- **에러 판정:** `header.resultCode` 가 `00`/`0` 이 아니면 오류로 처리.
- **집계:** 수집 후 `adongCd × 업종(대/중/소분류)` 로 GROUP BY 하여 `store_counts` 테이블에 점포수를 적재합니다. 즉 **행정동코드를 따로 준비할 필요 없이** 상가 레코드 자체의 `adongCd` 를 씁니다.

### 1.4 실행

```bash
uv run sangkwon collect store_info --region seongnam
uv run sangkwon collect store_info --region seongnam --max-pages 3   # 테스트: 시군구당 3페이지만
```

---

## 2. 통계청 SGIS 오픈API — `sgis`

**수요 축.** 행정동 단위 인구·가구·평균연령. 다른 API와 달리 **토큰 발급 후** 각 통계 API를 호출하는 2단계 인증입니다.

### 2.1 발급

1. [SGIS 오픈플랫폼(sgis.kostat.go.kr)](https://sgis.kostat.go.kr) 회원가입.
2. "서비스 신청/관리"에서 오픈API 활용 신청 → **서비스 ID(consumer_key)** 와 **보안 Key(consumer_secret)** 발급.
3. `.env` 에 `SGIS_CONSUMER_KEY`, `SGIS_CONSUMER_SECRET` 입력.

> ℹ️ SGIS API 서버가 `sgisapi.kostat.go.kr` → `sgisapi.mods.go.kr` 로 이전되며 **302 리다이렉트**가 발생합니다. 이 프로젝트의 HTTP 클라이언트는 리다이렉트를 자동 추적하도록 처리되어 있습니다.

### 2.2 인증 → 통계 호출 흐름

**1단계) 토큰 발급**
```
GET https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.json
  ?consumer_key=...&consumer_secret=...
```
응답 `result.accessToken` 을 이후 모든 호출에 사용.

**2단계) 통계 조회**

| 용도 | 엔드포인트 |
|------|-----------|
| 인구 | `GET /OpenAPI3/stats/population.json` |
| 가구 | `GET /OpenAPI3/stats/household.json` |
| 하위 행정동 코드 조회 | `GET /OpenAPI3/addr/stage.json` |

공통 파라미터:

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `accessToken` | 1단계 토큰 | |
| `year` | `2022` | 통계 기준연도 (`SGIS_STAT_YEAR` 로 변경) |
| `adm_cd` | SGIS 시군구코드 | 예: 강남구 `11230` (행안부와 다름!) |
| `low_search` | `1` | 하위 1단계(행정동)까지 전개 |

### 2.3 응답 (JSON)

```jsonc
{
  "errCd": 0,
  "result": [
    {
      "adm_cd": "1123051", "adm_nm": "역삼1동",
      "population": 33421,        // 또는 tot_ppltn
      "avg_age": 39.2,
      "x": 127.03, "y": 37.49
    }
  ]
}
```
가구(household) 응답의 `household_cnt`(또는 `tot_family`) 를 `adm_cd` 기준으로 인구와 병합하여 `demographics` 테이블에 적재합니다.

- **에러 판정:** `errCd` 가 `0`/`00` 이 아니면 오류.

### 2.4 SGIS 시군구코드 찾는 법

SGIS는 **시도 코드부터** 행안부와 다릅니다(경기=`31`, 부산=`21` …). 토큰 발급 후 `addr/stage` 로 조회하세요.

```
# 경기도(31) 하위 시군구 목록
GET /OpenAPI3/addr/stage.json?accessToken=...&cd=31
```
결과의 `cd` 값을 `config/regions.json` 의 `sgis_codes` 에 채웁니다.

### 2.5 실행

```bash
uv run sangkwon collect sgis --region seongnam
```

---

## 3. 국토교통부 상업업무용 실거래가 — `molit`

**비용 축.** 상업·업무용 부동산 **매매** 실거래. 응답이 유일하게 **XML** 입니다.

> ⚠️ 상업업무용 **전월세**는 공개 오픈API가 없습니다. `--with-rent` 를 줘도 500/401이 나며, 이 경우 매매 수집은 정상 진행하고 **부분 성공(partial)** 으로 기록합니다.

### 3.1 발급

- 공공데이터포털 **1613000** 그룹 "국토교통부_상업업무용 부동산 매매 신고 자료" 활용신청.
- `.env` 의 `MOLIT_SERVICE_KEY` 에 입력. **비워두면 `DATA_GO_KR_SERVICE_KEY` 를 재사용**합니다(같은 포털 키면 공유 가능).

### 3.2 엔드포인트

```
# 매매
GET https://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade
# 전월세 (구독/제공 여부 확인 — 상업용은 대개 미제공)
GET https://apis.data.go.kr/1613000/RTMSDataSvcNrgRent/getRTMSDataSvcNrgRent
```

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `serviceKey` | 발급키 | |
| `LAWD_CD` | **법정동 시군구코드 5자리** | 예: 강남구 `11680` (SGIS와 다름) |
| `DEAL_YMD` | `YYYYMM` | 계약 연월 (예: `202606`) |
| `pageNo` / `numOfRows` | 1 / `1000` | 페이징 |

수집 대상 월은 CLI에서 `--months N`(최근 N개월) 또는 `--deal-ym YYYYMM,YYYYMM` 로 지정합니다.

### 3.3 응답 (XML)

```xml
<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL</resultMsg></header>
  <body>
    <items>
      <item>
        <거래금액>150,000</거래금액>       <!-- 만원 단위, 콤마 포함 -->
        <건물면적>84.5</건물면적>
        <건물주용도>제2종근린생활시설</건물주용도>
        <법정동>역삼동</법정동>
        <층>3</층>
        <건축년도>2005</건축년도>
      </item>
    </items>
    <totalCount>146</totalCount>
  </body>
</response>
```

- **필드명 유동성:** 국토부 응답은 한글/영문 필드가 버전에 따라 섞여 옵니다. 수집기는 `거래금액|dealAmount`, `건물면적|buildingAr|전용면적` 처럼 **여러 후보명을 순차 시도**해 파싱합니다. 필드가 바뀌면 `molit.py` 의 `pick(...)` 목록만 보강하면 됩니다.
- **에러 판정:** `header/resultCode` 가 `00`/`000`/`0` 이 아니면 오류.

### 3.4 실행

```bash
uv run sangkwon collect molit --region seongnam --months 6
uv run sangkwon collect molit --region seongnam --deal-ym 202605,202606
```

---

## 4. 서울 열린데이터광장 골목상권 분석서비스 — `seoul_golmok`

**상권 축(서울 한정).** 유동인구·추정매출·점포수·폐업률. 소상공인365가 공개 API를 제공하지 않아, 서울 지역은 이 서비스로 상권 축을 채웁니다. 데이터 단위는 **상권코드(TRDAR_CD)** 이며, 상권영역 서비스에 자치구/행정동 코드가 함께 있어 조인이 가능합니다.

### 4.1 발급

- [서울 열린데이터광장(data.seoul.go.kr)](https://data.seoul.go.kr) 에서 인증키 발급 → `.env` 의 `SEOUL_OPEN_API_KEY`.
- **키가 없으면 `sample` 키로 동작**하지만 **최대 5건 제한**(테스트용). 실제 수집은 발급키 필요.

### 4.2 호출 형식 (경로에 값 삽입 — 특이)

```
GET http://openapi.seoul.go.kr:8088/{인증키}/json/{서비스명}/{시작인덱스}/{끝인덱스}/{기준년분기}
```
`{기준년분기}`(STDR_YYQU_CD)를 붙이면 서버측에서 분기 필터. 한 번에 최대 1000건.

**사용 서비스:**

| 서비스명 | 내용 | 핵심 필드 |
|----------|------|-----------|
| `TbgisTrdarRelm` | 상권영역(좌표·자치구·행정동) — 자치구 필터용 마스터 | `TRDAR_CD`, `SIGNGU_CD`, `ADSTRD_CD` |
| `VwsmTrdarFlpopQq` | 길단위 유동인구 | `TOT_FLPOP_CO` |
| `VwsmTrdarSelngQq` | 추정매출(상권×업종) | `THSMON_SELNG_AMT`, `THSMON_SELNG_CO` |
| `VwsmTrdarStorQq` | 점포(상권×업종) | `STOR_CO`, `CLSBIZ_STOR_CO`(폐업), `OPBIZ_STOR_CO`(개업), `FRC_STOR_CO`(프랜차이즈) |

### 4.3 수집 로직

1. `TbgisTrdarRelm` 전체를 받아 **대상 자치구(SIGNGU_CD)** 의 상권코드만 추림.
2. 최신 분기 자동탐색: `20261, 20254, … 20241` 순으로 `VwsmTrdarFlpopQq` 를 1건 조회해 데이터가 있는 분기를 선택(분기말 +2개월 후 갱신).
3. 유동인구는 그대로, 추정매출·점포는 **상권×업종 → 상권 합계**로 집계.
4. **폐업률 파생:** `폐업점포수 / 점포수 × 100`.

### 4.4 응답 (JSON)

```jsonc
{
  "VwsmTrdarStorQq": {
    "list_total_count": 1520,
    "RESULT": { "CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다" },
    "row": [
      { "TRDAR_CD": "3110001", "STOR_CO": 42, "CLSBIZ_STOR_CO": 3, "OPBIZ_STOR_CO": 5, "FRC_STOR_CO": 8 }
    ]
  }
}
```
- **에러 판정:** `RESULT.CODE` 가 `INFO-000` 이 아니면 오류. `sample` 키로 5건 초과 요청 시 에러 응답이 옵니다.

### 4.5 실행

```bash
uv run sangkwon collect seoul_golmok --region gangnam
uv run sangkwon collect seoul_golmok --region gangnam --quarter 20261   # 분기 고정
```

---

## 5. 소상공인365 상권분석 — `sbiz365` (보류)

전국 단위 유동인구·폐업률·업력·추정매출을 노렸으나, **소상공인365는 공개 오픈API 스펙이 없고 파일/대화형 리포트 형태**라 자동 수집에 부적합합니다. 코드는 "발급 API를 주입하면 동작하는" 골격만 남겨 두었습니다.

- 별도 API를 확보하면 `.env` 에 `SBIZ365_BASE_URL`, `SBIZ365_ENDPOINT`, `SBIZ365_SERVICE_KEY` 를 주입하고, 응답 필드가 다르면 `sbiz365.py` 의 `INDICATOR_FIELDS` 매핑(`flpop_co→유동인구`, `clsbiz_rt→폐업률`, `bsn_yy→평균업력`, `estm_sales→추정매출`)만 맞추면 됩니다.
- 표준 공공데이터포털 JSON(`{body:{items:[...]}}`) 형태를 가정합니다.
- **대안:** 서울은 §4 골목상권, 전국 평균 시세·추이는 다운로드(파일) 데이터로 보완(`오픈데이터_수집목록.md` 참고).

---

## 6. 지역 코드 체계 ⚠ (가장 흔한 실수)

| 소스 | 코드 종류 | regions.json 필드 | 강남구 예 |
|------|-----------|-------------------|-----------|
| 국토부 실거래가 | **법정동 시군구코드(LAWD_CD, 5자리)** | `sigungu[].code` | `11680` |
| SGIS | **통계청 행정구역코드** (시도부터 다름) | `sgis_codes` | `11230` |
| 상가정보 / 소상공인365 | 행안부 **행정동코드** | (상가정보는 응답 `adongCd` 사용) | `1168010100` |

같은 강남구도 **LAWD 11680 ≠ SGIS 11230** 이므로, 코드로 직접 조인하면 안 됩니다. **행정동명 기준 매핑**을 함께 써야 합니다. SGIS 코드는 `addr/stage` API로, 행안부 행정동코드는 [행정표준코드관리시스템(code.go.kr)](https://www.code.go.kr) 에서 확인합니다.

### `config/regions.json` 예시

```jsonc
"seongnam": {
  "name": "경기도 성남시",
  "sido_code": "41",
  "sgis_adm_cd": "41131",
  "sigungu": [                                  // 국토부 LAWD 5자리
    { "code": "41131", "name": "성남시 수정구" },
    { "code": "41133", "name": "성남시 중원구" },
    { "code": "41135", "name": "성남시 분당구" }
  ],
  "sgis_codes": ["31021", "31022", "31023"],    // SGIS 시군구코드 (경기=31)
  "adong_codes": []                             // 상가정보는 sigungu로 동작하므로 보통 불필요
}
```

---

## 7. 키 설정과 점검

`.env` (루트, `.gitignore` 로 커밋 제외):

| 변수 | 설명 |
|------|------|
| `DATA_GO_KR_SERVICE_KEY` | 공공데이터포털 상가정보 키 (**Decoding**) |
| `SGIS_CONSUMER_KEY` / `SGIS_CONSUMER_SECRET` | 통계청 SGIS 키 |
| `MOLIT_SERVICE_KEY` | 국토부 키 (비우면 포털 키 재사용) |
| `SEOUL_OPEN_API_KEY` | 서울 골목상권 키 (없으면 sample, 5건 제한) |
| `SBIZ365_SERVICE_KEY` / `SBIZ365_BASE_URL` / `SBIZ365_ENDPOINT` | 소상공인365 (스펙 확정 후) |
| `SGIS_STAT_YEAR` | SGIS 기준연도 (기본 2022) |

```bash
cp .env.example .env       # 키 입력
uv run sangkwon doctor     # 키 설정 여부 점검
uv run python -m sangkwon.cli ping   # 발급 키가 실제로 동작하는지 라이브 확인
```

> data.go.kr 키는 승인 후에도 실동작까지 시간차가 있어 `ping` 이 잠시 401을 낼 수 있습니다. 잠시 후 재시도하세요.

---

## 8. 전체 수집 파이프라인

```bash
uv sync                                         # 의존성 설치
uv run sangkwon init-db                         # DB 초기화
uv run sangkwon regions                         # 등록 지역 확인
uv run sangkwon collect-all --region seongnam   # 4개 소스 일괄 수집
uv run sangkwon status                          # 수집 이력 확인
uv run sangkwon export --region seongnam --format both   # JSON/CSV 내보내기
```

- **원본 응답**은 `data/raw/<source>/<region>/<label>_<timestamp>` 에 그대로 보관(감사·재처리용).
- **정규화 데이터**는 `data/sangkwon.sqlite`, **수집 이력**은 `collection_runs` 테이블.
- 모든 행에 `region_key` · `collected_at` 이 붙어 재수집 이력이 남으며, 최신값은 `MAX(collected_at)` 로 조회합니다.

---

## 9. 자주 겪는 이슈 요약

| 증상 | 원인 / 해결 |
|------|-------------|
| 상가정보 401 | 활용신청 직후 시간차, 또는 Encoding 키 사용. Decoding 키로 교체 후 재시도 |
| SGIS 302 계속 | 서버 이전(`kostat`→`mods`). 리다이렉트 자동 추적으로 처리됨(정상) |
| 국토부 전월세 500 | 상업용 전월세는 공개 API 없음. 매매만 수집(부분 성공) |
| 서울 골목상권 5건만 | `sample` 키 사용 중. `SEOUL_OPEN_API_KEY` 발급 필요 |
| 소스 간 조인 안 맞음 | 코드 체계 상이(§6). 행정동명 기준 매핑 사용 |
| SGIS 코드 모름 | `addr/stage.json?cd=<시도코드>` 로 하위 시군구 조회 |
