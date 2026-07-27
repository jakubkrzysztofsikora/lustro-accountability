"""Tests for the polite, defensive HTTP client (no live requests)."""

from __future__ import annotations

import httpx
import pytest

from lustro_accountability.client import LustroApiError, LustroClient


def make_client(handler) -> LustroClient:
    transport = httpx.MockTransport(handler)
    return LustroClient(base_url="https://test.invalid", client=httpx.Client(transport=transport))


def test_get_corrections_bare_array():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/corrections"
        return httpx.Response(200, json=[{"id": "c1"}, "junk", {"id": "c2"}])

    client = make_client(handler)
    assert client.get_corrections() == [{"id": "c1"}, {"id": "c2"}]


def test_get_corrections_unexpected_shape_is_empty():
    client = make_client(lambda r: httpx.Response(200, json={"nope": 1}))
    assert client.get_corrections() == []


def test_get_feed_items():
    client = make_client(
        lambda r: httpx.Response(200, json={"items": [{"id": "a1"}], "next": None})
    )
    assert client.get_feed() == [{"id": "a1"}]


def test_health_non_dict_tolerated():
    client = make_client(lambda r: httpx.Response(200, json=["weird"]))
    assert client.get_health() == {}


def test_retry_after_on_429():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 2:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=[])

    client = make_client(handler)
    assert client.get_corrections() == []
    assert len(attempts) == 2


def test_422_raises():
    client = make_client(lambda r: httpx.Response(422, json={"detail": "bad"}))
    with pytest.raises(LustroApiError):
        client.get_feed()


def test_persistent_500_raises():
    client = make_client(lambda r: httpx.Response(500))
    with pytest.raises(LustroApiError):
        client.get_health()


def test_non_json_raises():
    client = make_client(
        lambda r: httpx.Response(
            200, content=b"<html>oops</html>", headers={"Content-Type": "text/html"}
        )
    )
    with pytest.raises(LustroApiError):
        client.get_health()
