"""재시도 · 레이트리밋이 적용된 공용 HTTP 클라이언트."""
from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

DEFAULT_TIMEOUT = 30.0


class ApiError(RuntimeError):
    """API 가 비정상 응답(에러코드, 인증 실패 등)을 반환했을 때."""


class HttpClient:
    """공공 API 호출용 얇은 래퍼.

    - min_interval 초 만큼 호출 간 최소 간격을 둬서 레이트리밋을 회피한다.
    - 네트워크/5xx 오류는 지수 백오프로 재시도한다.
    """

    def __init__(self, *, min_interval: float = 0.2, timeout: float = DEFAULT_TIMEOUT):
        # follow_redirects: SGIS 등 기관 도메인 이전(kostat.go.kr→mods.go.kr) 시 302 자동 추적
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "sangkwon-collector/0.1"},
        )
        self._min_interval = min_interval
        self._last_call = 0.0

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        self._throttle()
        resp = self._client.get(url, params=params)
        # 5xx 만 재시도 대상으로(4xx 는 키/파라미터 문제이므로 즉시 실패)
        if resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        resp = self.get(url, params=params)
        if resp.status_code >= 400:
            raise ApiError(f"HTTP {resp.status_code} @ {url} :: {resp.text[:300]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ApiError(f"JSON 파싱 실패 @ {url} :: {resp.text[:300]}") from exc
