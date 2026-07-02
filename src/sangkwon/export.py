"""SQLite -> JSON / CSV 내보내기."""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from .settings import EXPORT_DIR

# 내보낼 데이터 테이블 (로그성 테이블 제외)
DATA_TABLES = [
    "regions",
    "demographics",
    "demographics_age",
    "income",
    "stores",
    "store_counts",
    "real_estate",
    "trdar_area",
    "commercial_analysis",
    "collection_runs",
]


def _rows(conn: sqlite3.Connection, table: str, region_key: str | None) -> list[dict]:
    if region_key and _has_column(conn, table, "region_key"):
        cur = conn.execute(f"SELECT * FROM {table} WHERE region_key = ?", (region_key,))
    else:
        cur = conn.execute(f"SELECT * FROM {table}")
    return [dict(r) for r in cur.fetchall()]


def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return col in cols


def export_json(conn: sqlite3.Connection, region_key: str | None = None) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = {t: _rows(conn, t, region_key) for t in DATA_TABLES}
    suffix = f"_{region_key}" if region_key else "_all"
    path = EXPORT_DIR / f"sangkwon{suffix}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_csv(conn: sqlite3.Connection, region_key: str | None = None) -> list[Path]:
    suffix = f"_{region_key}" if region_key else ""
    out_dir = EXPORT_DIR / f"csv{('_' + region_key) if region_key else ''}"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table in DATA_TABLES:
        rows = _rows(conn, table, region_key)
        if not rows:
            continue
        path = out_dir / f"{table}{suffix}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        written.append(path)
    return written
