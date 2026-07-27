"""Minimal, polite, defensive HTTP client for the public LUSTRO API.

Politeness: at most one request at a time, optional spacing delay, honors
429 + Retry-After with a single bounded retry. No full advisory bodies are
cached beyond the fields the public API serves.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

BASE_URL = "https://projektlustro.eu"
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3

log = logging.getLogger(__name__)


class LustroApiError(RuntimeError):
    """Raised when the API cannot be reached or returns an unusable response."""


class LustroClient:
    """Sync client for the endpoints the accountability monitor needs."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        min_interval: float = 0.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self._last_request_at = 0.0
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LustroClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        for attempt in range(MAX_RETRIES):
            wait = self.min_interval - (time.monotonic() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
            try:
                self._last_request_at = time.monotonic()
                resp = self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES - 1:
                    raise LustroApiError(f"request failed: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = float(retry_after)
                else:
                    delay = 2.0 * (attempt + 1)
                log.warning("rate-limited on %s; backing off %.1fs", path, delay)
                time.sleep(delay)
                continue
            if resp.status_code == 422:
                raise LustroApiError(f"422 from {path}: {resp.text[:200]}")
            if resp.status_code >= 400:
                if attempt == MAX_RETRIES - 1:
                    raise LustroApiError(f"HTTP {resp.status_code} from {path}")
                time.sleep(2**attempt)
                continue
            try:
                return resp.json()
            except ValueError as exc:
                raise LustroApiError(f"non-JSON response from {path}") from exc
        raise LustroApiError(f"exhausted retries for {path}")

    def get_corrections(self) -> list[dict[str, Any]]:
        """GET /v1/corrections — a bare array of correction records."""
        data = self._get("/v1/corrections")
        if isinstance(data, list):
            return [c for c in data if isinstance(c, dict)]
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return [c for c in data["items"] if isinstance(c, dict)]
        log.warning("unexpected /v1/corrections payload shape; treating as empty")
        return []

    def get_feed(self, limit: int = 100) -> list[dict[str, Any]]:
        """GET /v1/feed — first page of feed items (advisories)."""
        data = self._get("/v1/feed", params={"limit": limit})
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return [i for i in data["items"] if isinstance(i, dict)]
        return []

    def get_health(self) -> dict[str, Any]:
        """GET /api/health — service health including classifier state."""
        data = self._get("/api/health")
        return data if isinstance(data, dict) else {}
