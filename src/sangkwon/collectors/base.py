"""모든 수집기의 공통 베이스."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from ..db import finalize_run, run_logger
from ..http import HttpClient
from ..settings import ApiKeys, Region


@dataclass
class CollectResult:
    source: str
    region_key: str
    record_count: int = 0
    raw_paths: list[str] = field(default_factory=list)
    status: str = "success"
    message: str | None = None


class BaseCollector:
    """수집기 인터페이스.

    하위 클래스는 `source` 와 `collect()` 를 구현한다.
    - source: 짧은 식별자 (store_info / sgis / molit / sbiz365)
    - required_keys: 동작에 필요한 ApiKeys 속성명 목록 (검증용)
    """

    source: str = "base"
    required_keys: tuple[str, ...] = ()

    def __init__(self, conn: sqlite3.Connection, keys: ApiKeys):
        self.conn = conn
        self.keys = keys

    # --- 하위 클래스가 구현 ---------------------------------------------------
    def collect(self, region: Region, http: HttpClient, result: CollectResult) -> None:
        raise NotImplementedError

    # --- 공통 실행 래퍼 -------------------------------------------------------
    def missing_keys(self) -> list[str]:
        return [k for k in self.required_keys if not getattr(self.keys, k, "")]

    def run(self, region: Region, *, min_interval: float = 0.2) -> CollectResult:
        result = CollectResult(source=self.source, region_key=region.key)
        with run_logger(self.conn, self.source, region.key) as run_id:
            with HttpClient(min_interval=min_interval) as http:
                self.collect(region, http, result)
            finalize_run(
                self.conn,
                run_id,
                status=result.status,
                record_count=result.record_count,
                raw_path=";".join(result.raw_paths) or None,
                message=result.message,
            )
        return result
