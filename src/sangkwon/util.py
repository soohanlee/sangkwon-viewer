"""공용 유틸: 시각, 원본 JSON 저장, 안전 형변환."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import RAW_DIR


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")


def save_raw(source: str, region_key: str, label: str, payload: Any) -> Path:
    """원본 응답을 data/raw/<source>/<region>/<label>_<timestamp>.json 으로 보관."""
    out_dir = RAW_DIR / source / region_key
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{label}_{_stamp()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        s = str(value).replace(",", "").strip()
        if s == "" or s == "-":
            return None
        return int(float(s))
    except (ValueError, TypeError):
        return None


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        s = str(value).replace(",", "").strip()
        if s == "" or s == "-":
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def clean(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None
