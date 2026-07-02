"""소스별 데이터 수집기."""
from __future__ import annotations

from .base import BaseCollector, CollectResult
from .molit import MolitCollector
from .sbiz365 import Sbiz365Collector
from .seoul_golmok import SeoulGolmokCollector
from .sgis import SgisCollector
from .store_info import StoreInfoCollector

# CLI 에서 이름으로 선택할 수 있도록 등록
COLLECTORS: dict[str, type[BaseCollector]] = {
    StoreInfoCollector.source: StoreInfoCollector,
    SgisCollector.source: SgisCollector,
    MolitCollector.source: MolitCollector,
    SeoulGolmokCollector.source: SeoulGolmokCollector,
    Sbiz365Collector.source: Sbiz365Collector,
}

__all__ = [
    "BaseCollector",
    "CollectResult",
    "COLLECTORS",
    "StoreInfoCollector",
    "SgisCollector",
    "MolitCollector",
    "SeoulGolmokCollector",
    "Sbiz365Collector",
]
