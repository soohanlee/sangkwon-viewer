# 공개데이터 뷰어 (정적 데모)

공공 오픈 API로 수집한 상권 데이터의 **형태를 보여주는 정적 미리보기**입니다.
서버 없이 `index.html` + `data/demo.json` 만으로 동작하며, 공개 데이터 샘플만 표시합니다.

```
docs/
├── index.html         # 단일 페이지 뷰어 (서버 불필요)
└── data/
    └── demo.json       # 테이블별 샘플 + 전체 건수/분포 요약 (약 54KB)
```

## 로컬에서 보기

`docs/` 안에서 정적 서버를 하나 띄우면 됩니다. (파일을 직접 열면 fetch가 막힙니다)

```bash
cd docs
python -m http.server 8080
# 브라우저에서 http://localhost:8080
```

## GitHub Pages로 공개하기

1. 이 프로젝트를 GitHub **퍼블릭** 저장소에 push.
   - `docs/` 폴더만 있으면 됩니다. (DB·원본 데이터는 `.gitignore`로 제외되어 올라가지 않음)
2. 저장소 **Settings → Pages** 이동.
3. **Build and deployment → Source: Deploy from a branch** 선택.
4. **Branch: `main` / 폴더: `/docs`** 선택 후 Save.
5. 1~2분 뒤 `https://<사용자명>.github.io/<저장소명>/` 에서 공개됩니다.

> 이 데모는 공개(오픈) 데이터 샘플만 담고 있어 그대로 퍼블릭 공개해도 안전합니다.
> API 키(`.env`)는 커밋 대상이 아니며, 개인정보·비공개 정보는 포함되지 않습니다.

## 샘플 데이터 갱신

DB를 다시 수집한 뒤 아래를 실행하면 `data/demo.json` 이 새로 만들어집니다.
(생성 스크립트: 테이블별 대표 40건 + 전체 건수·지역/업종 분포 요약)

전체 데이터를 공개하려는 게 아니라 "이런 데이터가 나온다"를 보여주는 용도이므로,
샘플 건수(현재 40건)만 조절하면 됩니다.
