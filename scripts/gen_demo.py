"""docs 정적 뷰어용 샘플 JSON 생성 (동탄·화성·오산 한정)."""
import sqlite3, json, datetime, os

DB = "data/sangkwon.sqlite"
OUT = "docs/data/demo.json"
REGIONS = ("hwaseong", "osan")
REGION_LABELS = {"hwaseong": "화성시", "osan": "오산시"}
SAMPLE_N = 40

LABELS = {
    "bizes_nm": "상호명", "branch_nm": "지점명", "inds_lcls_nm": "업종 대분류",
    "inds_mcls_nm": "업종 중분류", "inds_scls_nm": "업종 소분류", "adong_nm": "행정동",
    "road_addr": "도로명주소", "region_key": "지역",
    "adm_cd": "행정동코드", "adm_nm": "행정동명", "sigungu": "시군구코드", "dong": "동",
    "indicator": "지표", "period": "기준시점", "value": "값", "unit": "단위",
    "year": "연도", "population": "총인구", "households": "가구수", "avg_age": "평균연령",
    "inds_cls_cd": "업종코드", "inds_cls_nm": "업종", "level": "분류단계", "store_count": "점포수",
    "lawd_cd": "시군구코드", "deal_ym": "거래연월", "trade_type": "거래구분",
    "building_type": "건물유형", "building_nm": "건물명", "dong_nm": "동",
    "use_area": "면적(㎡)", "floor": "층", "deal_amount": "매매금액(만원)",
    "deposit": "보증금(만원)", "monthly_rent": "월세(만원)", "build_year": "건축년도",
}

TABLES = {
    "stores": {"label": "상가업소", "icon": "🏪", "source": "소상공인공단 상가정보 API",
        "columns": ["bizes_nm", "inds_lcls_nm", "inds_mcls_nm", "inds_scls_nm", "adong_nm", "road_addr", "region_key"],
        "order": "region_key ASC, adong_nm ASC"},
    "store_counts": {"label": "업종별 점포수", "icon": "📊", "source": "상가정보 집계",
        "columns": ["adm_cd", "inds_cls_nm", "level", "store_count", "region_key"],
        "order": "store_count DESC"},
    "real_estate": {"label": "부동산 실거래", "icon": "🏢", "source": "국토부 실거래가 API (상업용 매매)",
        "columns": ["deal_ym", "trade_type", "building_type", "dong_nm", "use_area", "floor", "deal_amount", "build_year", "region_key"],
        "order": "deal_amount DESC"},
    "demographics": {"label": "인구·가구", "icon": "👥", "source": "통계청 SGIS 오픈API",
        "columns": ["adm_cd", "year", "population", "households", "avg_age", "region_key"],
        "order": "population DESC"},
}

c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
def cols_exist(t):
    return {r["name"] for r in c.execute('PRAGMA table_info("%s")' % t)}

ph = ",".join("?" * len(REGIONS))
out = {"generated_at": datetime.date.today().isoformat(),
       "scope": "동탄 · 화성시 · 오산시", "tables": [], "summary": {}}

for name, cfg in TABLES.items():
    have = cols_exist(name)
    if not have:
        continue
    cols = [x for x in cfg["columns"] if x in have]
    total = c.execute('SELECT COUNT(*) FROM "%s" WHERE region_key IN (%s)' % (name, ph), REGIONS).fetchone()[0]
    colsql = ", ".join('"%s"' % x for x in cols)
    q = 'SELECT %s FROM "%s" WHERE region_key IN (%s) ORDER BY %s LIMIT %d' % (colsql, name, ph, cfg["order"], SAMPLE_N)
    rows = [dict(r) for r in c.execute(q, REGIONS)]
    for r in rows:
        if "region_key" in r:
            r["region_key"] = REGION_LABELS.get(r["region_key"], r["region_key"])
    out["tables"].append({
        "name": name, "label": cfg["label"], "icon": cfg["icon"], "source": cfg["source"],
        "total": total, "sample_n": len(rows),
        "columns": [{"col": x, "label": LABELS.get(x, x)} for x in cols],
        "rows": rows,
    })

cards = [{"label": t["label"], "icon": t["icon"], "total": t["total"], "source": t["source"]}
         for t in out["tables"]]

dongtan = c.execute("SELECT COUNT(*) FROM stores WHERE region_key='hwaseong' AND adong_nm LIKE '%동탄%'").fetchone()[0]
hwaseong_all = c.execute("SELECT COUNT(*) FROM stores WHERE region_key='hwaseong'").fetchone()[0]
osan = c.execute("SELECT COUNT(*) FROM stores WHERE region_key='osan'").fetchone()[0]
by_region = [
    {"label": "동탄(화성 내)", "count": dongtan},
    {"label": "화성 그 외", "count": hwaseong_all - dongtan},
    {"label": "오산시", "count": osan},
]

by_dongtan = [{"label": r["adong_nm"], "count": r["c"]} for r in c.execute(
    "SELECT adong_nm, COUNT(*) c FROM stores WHERE region_key='hwaseong' AND adong_nm LIKE '%동탄%' "
    "GROUP BY adong_nm ORDER BY c DESC")]

by_ind = [{"label": r["inds_lcls_nm"], "count": r["c"]} for r in c.execute(
    "SELECT inds_lcls_nm, COUNT(*) c FROM stores WHERE region_key IN (%s) "
    "AND inds_lcls_nm IS NOT NULL GROUP BY inds_lcls_nm ORDER BY c DESC LIMIT 10" % ph, REGIONS)]

out["summary"] = {"cards": cards, "by_region": by_region,
                  "by_dongtan": by_dongtan, "by_industry": by_ind}

json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote", OUT, round(os.path.getsize(OUT) / 1024, 1), "KB")
print("tables:", [t["name"] for t in out["tables"]])
print("동탄:", dongtan, "화성전체:", hwaseong_all, "오산:", osan)
