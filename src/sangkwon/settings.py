"""환경 변수 · 경로 · 지역 설정 로딩."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트 = 이 파일 기준 ../../..  (src/sangkwon/settings.py -> 루트)
ROOT = Path(__file__).resolve().parents[2]

load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("SANGKWON_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = Path(os.getenv("SANGKWON_DB_PATH", DATA_DIR / "sangkwon.sqlite"))
REGIONS_PATH = ROOT / "config" / "regions.json"


@dataclass(frozen=True)
class ApiKeys:
    data_go_kr: str = ""
    sgis_key: str = ""
    sgis_secret: str = ""
    molit: str = ""
    sbiz365: str = ""
    seoul: str = ""

    @classmethod
    def from_env(cls) -> "ApiKeys":
        data_key = os.getenv("DATA_GO_KR_SERVICE_KEY", "").strip()
        return cls(
            data_go_kr=data_key,
            sgis_key=os.getenv("SGIS_CONSUMER_KEY", "").strip(),
            sgis_secret=os.getenv("SGIS_CONSUMER_SECRET", "").strip(),
            # 국토부 키가 비어 있으면 공공데이터포털 키를 재사용
            molit=os.getenv("MOLIT_SERVICE_KEY", "").strip() or data_key,
            sbiz365=os.getenv("SBIZ365_SERVICE_KEY", "").strip(),
            # 서울 열린데이터광장 키 (없으면 sample: 최대 5건 제한)
            seoul=os.getenv("SEOUL_OPEN_API_KEY", "").strip(),
        )


@dataclass(frozen=True)
class Sigungu:
    code: str
    name: str


@dataclass
class Region:
    key: str
    name: str
    sido_code: str
    sgis_adm_cd: str
    sigungu: list[Sigungu] = field(default_factory=list)   # MOLIT용 LAWD(법정동 시군구) 코드
    sgis_codes: list[str] = field(default_factory=list)    # SGIS 시군구 코드 (행안부와 다름)
    adong_codes: list[str] = field(default_factory=list)   # store_info/sbiz365용 행안부 행정동코드


def load_regions() -> dict[str, Region]:
    raw = json.loads(REGIONS_PATH.read_text(encoding="utf-8"))
    regions: dict[str, Region] = {}
    for key, val in raw.get("regions", {}).items():
        regions[key] = Region(
            key=key,
            name=val["name"],
            sido_code=val.get("sido_code", ""),
            sgis_adm_cd=val.get("sgis_adm_cd", ""),
            sigungu=[Sigungu(**s) for s in val.get("sigungu", [])],
            sgis_codes=list(val.get("sgis_codes", [])),
            adong_codes=list(val.get("adong_codes", [])),
        )
    return regions


def get_region(key: str) -> Region:
    regions = load_regions()
    if key not in regions:
        available = ", ".join(regions) or "(없음)"
        raise KeyError(f"지역 '{key}' 을(를) 찾을 수 없습니다. 사용 가능: {available}")
    return regions[key]


def ensure_dirs() -> None:
    for d in (DATA_DIR, RAW_DIR, EXPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)
