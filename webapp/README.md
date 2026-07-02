# 상권분석 데이터 뷰어 (webapp)

`data/sangkwon.sqlite` 에 수집된 상권분석 데이터를 **필터 + 페이지네이션**으로 조회하는
웹 뷰어. 읽기전용 FastAPI 백엔드 + React(Vite) 프론트엔드로 구성된다.

```
webapp/
├── api.py              # FastAPI 읽기전용 API (SQLite -> JSON)
└── frontend/           # React + Vite + TypeScript SPA
    └── src/
        ├── App.tsx     # 대시보드 · 탭 · 필터 · 테이블
        ├── api.ts      # API 호출/타입
        └── styles.css
```

## 실행

### 1) 백엔드 (포트 8000)

프로젝트 루트(`sangkwon-collector/`)에서:

```bash
pip install fastapi uvicorn          # 최초 1회
python -m uvicorn webapp.api:app --port 8000
```

### 2) 프론트엔드 (포트 5190)

```bash
cd webapp/frontend
npm install                          # 최초 1회
npm run dev
```

브라우저에서 http://localhost:5190 접속. `/api/*` 요청은 Vite 프록시가 8000번 백엔드로 전달한다.

## 기능

- **대시보드**: 지역별 상가 분포, 업종 대분류 TOP 10
- **탭**: 상가업소(11만)·업종별 점포수·부동산 실거래·상권분석 지표·인구·상권영역·행정동·수집로그
- **필터**
  - 셀렉트(다중선택, OR): 지역·업종·행정동·거래구분·지표 등 (각 옵션별 건수 표시)
  - 범위: 매매금액·월세·면적·점포수·인구 등 (min/max)
  - 검색: 상호명·주소·건물명 등 LIKE 검색
- **정렬**: 헤더 클릭으로 컬럼 오름/내림차순
- **페이지네이션**: 서버사이드 (25/50/100/200행)

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/tables` | 테이블 목록 + 컬럼/필터 메타 |
| GET | `/api/summary` | 대시보드 요약 통계 |
| GET | `/api/options/{table}/{col}` | 컬럼 distinct 값(셀렉트 옵션) |
| GET | `/api/data/{table}` | 필터·정렬·페이지네이션된 행 |

`/api/data` 쿼리 파라미터: `page`, `page_size`, `sort`, `order`, `q`(검색),
`{col}=값`(동등, 반복 시 IN), `{col}__min` / `{col}__max`(범위).

> 보안: 테이블/컬럼명은 화이트리스트(api.py `TABLES`)와 실제 스키마로 검증하고,
> 값은 항상 파라미터 바인딩으로만 전달한다. DB는 `mode=ro`(읽기전용)로 연다.
