import io
from datetime import UTC, date, datetime
from typing import Any

import httpx
import numpy as np
import pytest
import tifffile

import app.sentinel
from app.sentinel import (
    SentinelAuthError,
    SentinelHubClient,
    _web_mercator_polygon,
    valid_pixel_mask,
)


def tiff_bytes(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    tifffile.imwrite(buffer, array, photometric="minisblack")
    return buffer.getvalue()


class ProcessSpy(SentinelHubClient):
    def __init__(self) -> None:
        super().__init__("id", "secret")
        self.resampling: list[str] = []

    async def _process_tiff(
        self,
        geometry: dict[str, Any],
        acquired_at: str,
        evalscript: str,
        *,
        resampling: str,
    ) -> bytes:
        self.resampling.append(resampling)
        if resampling == "BILINEAR":
            return tiff_bytes(np.full((2, 3, 7), 0.2, dtype=np.float32))
        mask = np.zeros((2, 3, 2), dtype=np.uint8)
        mask[..., 0] = 4
        mask[..., 1] = 1
        return tiff_bytes(mask)


@pytest.mark.asyncio
async def test_reflectance_bilinear_scl_nearest_and_equal_grid(
    polygon_geojson: dict[str, object],
) -> None:
    client = ProcessSpy()
    raster = await client.raster(polygon_geojson, "2026-05-01T10:00:00Z")
    assert sorted(client.resampling) == ["BILINEAR", "NEAREST"]
    assert raster.width == 3 and raster.height == 2
    assert all(value.shape == raster.scl.shape for value in raster.bands.values())
    assert valid_pixel_mask(raster).all()


def test_process_geometry_uses_metric_web_mercator(polygon_geojson: dict[str, object]) -> None:
    transformed = _web_mercator_polygon(polygon_geojson)
    first = transformed["coordinates"][0][0]
    assert abs(first[0]) > 1_000_000
    assert abs(first[1]) > 1_000_000


class CatalogSpy(SentinelHubClient):
    def __init__(self) -> None:
        super().__init__("id", "secret")
        self.payload: dict[str, Any] | None = None

    async def _token(self) -> str:
        return "token"

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.payload = kwargs["json"]
        features = [
            {
                "id": f"P{day}",
                "properties": {
                    "datetime": f"2026-05-{day:02d}T10:00:00Z",
                    "eo:cloud_cover": 10,
                },
            }
            for day in range(1, 7)
        ]
        return httpx.Response(200, json={"features": features})


@pytest.mark.asyncio
async def test_catalog_requests_and_returns_only_latest_five(
    polygon_geojson: dict[str, object],
) -> None:
    client = CatalogSpy()
    items = await client.catalog(polygon_geojson)
    assert client.payload is not None
    assert client.payload["limit"] == 5
    # CDSE katalogi "sortby" ni qabul qilmaydi; saralash Python tomonida bo'ladi.
    assert "sortby" not in client.payload
    assert client.payload["datetime"].startswith("../")
    upper_bound = datetime.fromisoformat(client.payload["datetime"].removeprefix("../"))
    assert upper_bound.astimezone(UTC).tzinfo is UTC
    assert [item.product_id for item in items] == ["P2", "P3", "P4", "P5", "P6"]


class RangeCatalogSpy(SentinelHubClient):
    def __init__(self) -> None:
        super().__init__("id", "secret")
        self.payloads: list[dict[str, Any]] = []

    async def _token(self) -> str:
        return "token"

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        payload = dict(kwargs["json"])
        self.payloads.append(payload)
        day = 2 if payload.get("next") else 1
        body: dict[str, Any] = {
            "features": [
                {
                    "id": f"P{day}",
                    "properties": {
                        "datetime": f"2025-03-0{day}T10:00:00Z",
                        "eo:cloud_cover": day * 10,
                    },
                }
            ]
        }
        if day == 1:
            body["context"] = {"next": 2}
        return httpx.Response(200, json=body)


@pytest.mark.asyncio
async def test_catalog_range_uses_requested_date_and_follows_pagination(
    polygon_geojson: dict[str, object],
) -> None:
    client = RangeCatalogSpy()
    items = await client.catalog_range(polygon_geojson, date(2025, 3, 1))
    assert len(client.payloads) == 2
    assert client.payloads[0]["datetime"].startswith("2025-03-01T00:00:00+00:00/")
    assert client.payloads[0]["limit"] == 100
    assert client.payloads[1]["next"] == 2
    assert [item.product_id for item in items] == ["P1", "P2"]


class _FakeAsyncClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self._request_call: dict[str, Any] | None = None
        self.is_closed = False

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self._request_call = {"method": method, "url": url, **kwargs}
        return httpx.Response(200, text="{}", request=httpx.Request(method, url))

    async def aclose(self) -> None:
        self.is_closed = True


@pytest.mark.asyncio
async def test_proxy_is_stored_and_passed_to_async_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_client(*args: Any, **kwargs: Any) -> _FakeAsyncClient:
        captured["kwargs"] = kwargs
        return _FakeAsyncClient(*args, **kwargs)

    monkeypatch.setattr(app.sentinel.httpx, "AsyncClient", fake_client)

    client = SentinelHubClient("id", "secret", proxy="http://127.0.0.1:8080")
    assert client.proxy == "http://127.0.0.1:8080"
    await client._request("GET", "https://example.com")
    assert captured["kwargs"].get("proxy") == "http://127.0.0.1:8080"


@pytest.mark.asyncio
async def test_default_proxy_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_client(*args: Any, **kwargs: Any) -> _FakeAsyncClient:
        captured["kwargs"] = kwargs
        return _FakeAsyncClient(*args, **kwargs)

    monkeypatch.setattr(app.sentinel.httpx, "AsyncClient", fake_client)

    client = SentinelHubClient("id", "secret")
    assert client.proxy is None
    await client._request("GET", "https://example.com")
    assert "proxy" in captured["kwargs"]
    assert captured["kwargs"]["proxy"] is None


@pytest.mark.asyncio
async def test_http_client_is_reused_across_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    instances: list[_FakeAsyncClient] = []

    def fake_client(*args: Any, **kwargs: Any) -> _FakeAsyncClient:
        instance = _FakeAsyncClient(*args, **kwargs)
        instances.append(instance)
        return instance

    monkeypatch.setattr(app.sentinel.httpx, "AsyncClient", fake_client)

    client = SentinelHubClient("id", "secret")
    await client._request("GET", "https://example.com")
    await client._request("GET", "https://example.com")
    assert len(instances) == 1
    await client.aclose()
    assert instances[0].is_closed


class TokenSpy(SentinelHubClient):
    def __init__(self) -> None:
        super().__init__("id", "secret")
        self.token_responses: list[dict[str, Any]] = []
        self.token_calls = 0

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.token_calls += 1
        return httpx.Response(200, json=self.token_responses.pop(0))


@pytest.mark.asyncio
async def test_token_cached_until_expiry() -> None:
    client = TokenSpy()
    client.token_responses = [{"access_token": "tok1", "expires_in": 3600}]
    assert await client._token() == "tok1"
    assert await client._token() == "tok1"
    assert client.token_calls == 1

    client._token_expires_at = 0.0
    client.token_responses = [{"access_token": "tok2", "expires_in": 3600}]
    assert await client._token() == "tok2"
    assert client.token_calls == 2


class AuthorizedSpy(SentinelHubClient):
    """_authorized_request 401-refresh testi uchun skriptlangan klient."""

    def __init__(self) -> None:
        super().__init__("id", "secret")
        self.token_calls = 0
        self.data_calls: list[dict[str, Any]] = []

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if url == self.token_url:
            self.token_calls += 1
            token = "tok1" if self.token_calls == 1 else "tok2"
            return httpx.Response(200, json={"access_token": token, "expires_in": 3600})
        # Data URL — birinchi chaqiruvda 401 (SentinelAuthError), keyin 200.
        self.data_calls.append({"headers": dict(kwargs.get("headers") or {})})
        if len(self.data_calls) == 1:
            raise SentinelAuthError("401")
        return httpx.Response(200, json={"ok": True})


@pytest.mark.asyncio
async def test_authorized_request_refreshes_token_on_401() -> None:
    client = AuthorizedSpy()
    response = await client._authorized_request("POST", "https://data.example.com")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert client.token_calls == 2
    assert len(client.data_calls) == 2
    assert client.data_calls[1]["headers"]["Authorization"] == "Bearer tok2"
