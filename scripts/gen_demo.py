import sqlite3, json, datetime
DB='data/sangkwon.sqlite'
OUT='docs/data/demo.json'

LABELS={
 "bizes_nm":"상호명","branch_nm":"지점명","inds_lcls_nm":"업종 대분류","inds_mcls_nm":"업종 중분류",
 "inds_scls_nm":"업종 소분류","adong_nm":"행정동","road_addr":"도로명주소","region_key":"지역",
 "adm_cd":"행정동코드","adm_nm":"행정동명","sigungu":"시군구코드","dong":"동",
 "indicator":"지표","period":"기준시점","value":"값","unit":"단위",
 "year":"연도","population":"총인구","households":"가구수","avg_age":"평균연령",
 "inds_cls_cd":"업종코드","inds_cls_nm":"업종","level":"분류단계","store_count":"점포수",
 "lawd_cd":"시군구코드","deal_ym":"거래연월","trade_type":"거래구분","building_type":"건물유형",
 "building_nm":"건물명","dong_nm":"동","use_area":"면적(㎡)","floor":"층",
 "deal_amount":"매매금액(만원)","deposit":"보증금(만원)","monthly_rent":"월세(만원)","build_year":"건축년도",
 "trdar_nm":"상권명","trdar_se_nm":"상권구분","signgu_nm":"자치구","adstrd_nm":"행정동",
 "id":"ID","source":"출처","started_at":"시작","finished_at":"종료","status":"상태",
 "record_count":"건수","message":"메시지",
}
REGION_LABELS={"gangnam":"강남구","seongnam":"성남시","suwon":"수원시"}

# 테이블: (라벨, 아이콘, 출처, 표시컬럼, 샘플용 정렬)
TABLES={
 "stores":{"label":"상가업소","icon":"🏪","source":"소상공인공단 상가정보 API",
   "columns":["bizes_nm","inds_lcls_nm","inds_mcls_nm","inds_scls_nm","adong_nm","road_addr","region_key"],
   "order":"bizes_nm ASC"},
 "store_counts":{"label":"업종별 점포수","icon":"📊","source":"상가정보 집계",
   "columns":["adm_cd","inds_cls_nm","level","store_count","region_key"],"order":"store_count DESC"},
 "real_estate":{"label":"부동산 실거래","icon":"🏢","source":"국토부 실거래가 API",
   "columns":["deal_ym","trade_type","building_type","dong_nm","use_area","floor","deal_amount","build_year","region_key"],
   "order":"deal_amount DESC"},
 "commercial_analysis":{"label":"상권분석 지표","icon":"📈","source":"서울 골목상권 분석서비스",
   "columns":["adm_cd","indicator","period","value","unit","region_key"],"order":"adm_cd ASC"},
 "demographics":{"label":"인구·가구","icon":"👥","source":"통계청 SGIS 오픈API",
   "columns":["adm_cd","year","population","households","avg_age","region_key"],"order":"population DESC"},
 "trdar_area":{"label":"상권 영역","icon":"🗺️","source":"서울 골목상권(상권영역)",
   "columns":["trdar_nm","trdar_se_nm","signgu_nm","adstrd_nm","region_key"],"order":"trdar_nm ASC"},
}
SAMPLE_N=40

c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
def cols_exist(t):
    return {r["name"] for r in c.execute(f'PRAGMA table_info("{t}")')}

out={"generated_at":datetime.date.today().isoformat(),"tables":[],"summary":{}}

for name,cfg in TABLES.items():
    have=cols_exist(name)
    if not have: continue
    cols=[x for x in cfg["columns"] if x in have]
    total=c.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    colsql=", ".join(f'"{x}"' for x in cols)
    order=cfg["order"] if cfg["order"].split()[0] in have else ""
    q=f'SELECT {colsql} FROM "{name}"' + (f' ORDER BY {order}' if order else '') + f' LIMIT {SAMPLE_N}'
    rows=[dict(r) for r in c.execute(q)]
    for r in rows:
        if "region_key" in r:
            r["region_key"]=REGION_LABELS.get(r["region_key"],r["region_key"])
    out["tables"].append({
        "name":name,"label":cfg["label"],"icon":cfg["icon"],"source":cfg["source"],
        "total":total,"sample_n":len(rows),
        "columns":[{"col":x,"label":LABELS.get(x,x)} for x in cols],
        "rows":rows,
    })

# 요약: 카드 + 지역분포 + 업종 top10
cards=[{"label":t["label"],"icon":t["icon"],"total":t["total"],"source":t["source"]} for t in out["tables"]]
by_region=[{"label":REGION_LABELS.get(r["region_key"],r["region_key"]),"count":r["c"]}
           for r in c.execute('SELECT region_key,COUNT(*) c FROM stores GROUP BY region_key ORDER BY c DESC LIMIT 15')]
by_ind=[{"label":r["inds_lcls_nm"],"count":r["c"]}
        for r in c.execute('SELECT inds_lcls_nm,COUNT(*) c FROM stores WHERE inds_lcls_nm IS NOT NULL GROUP BY inds_lcls_nm ORDER BY c DESC LIMIT 10')]
out["summary"]={"cards":cards,"by_region":by_region,"by_industry":by_ind}

json.dump(out,open(OUT,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
import os
print("wrote",OUT,round(os.path.getsize(OUT)/1024,1),"KB")
print("tables:",[t["name"] for t in out["tables"]])
