import asyncio
import hashlib
import io
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, time as dt_time, timedelta
from typing import Any, cast

import httpx
import numpy as np
import numpy.typing as npt
import tifffile
from pyproj import Transformer

from app.constants import MAX_STORED_ACQUISITIONS

logger = logging.getLogger(__name__)

REFLECTANCE_BANDS = ("B02", "B03", "B04", "B05", "B08", "B8A", "B11")


class SentinelError(RuntimeError):
    pass


class SentinelAuthError(SentinelError):
    """Sentinel Hub autentifikatsiya xatosi (HTTP 401)."""
    pass


@dataclass(frozen=True)
class CatalogItem:
    acquired_at: str
    product_id: str
    revision_key: str
    cloud_coverage: float | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RasterData:
    bands: dict[str, npt.NDArray[np.float32]]
    scl: npt.NDArray[np.uint8]
    data_mask: npt.NDArray[np.bool_]
    bbox: list[float]
    width: int
    height: int


def _iso_after(value: str, seconds: int = 1) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed + timedelta(seconds=seconds)).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _revision_key(item: dict[str, Any]) -> str:
    properties = item.get("properties", {})
    revision_source = {
        "id": item.get("id"),
        "updated": properties.get("updated"),
        "created": properties.get("created"),
        "product_uri": properties.get("s2:product_uri"),
        "processing_baseline": properties.get("s2:processing_baseline"),
    }
    payload = json.dumps(revision_source, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _as_channels_last(payload: bytes, channel_count: int) -> npt.NDArray[np.float32]:
    array = np.asarray(tifffile.imread(io.BytesIO(payload)))
    if array.ndim == 2 and channel_count == 1:
        array = array[..., np.newaxis]
    elif array.ndim == 3 and array.shape[0] == channel_count and array.shape[-1] != channel_count:
        array = np.moveaxis(array, 0, -1)
    if array.ndim != 3 or array.shape[-1] != channel_count:
        raise SentinelError(f"Sentinel TIFF kanal shakli kutilmagan: {array.shape}")
    return array.astype(np.float32, copy=False)


def _web_mercator_polygon(geometry: dict[str, Any]) -> dict[str, Any]:
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    coordinates = [
        [[*transformer.transform(float(point[0]), float(point[1]))] for point in ring]
        for ring in geometry["coordinates"]
    ]
    return {"type": "Polygon", "coordinates": coordinates}


class SentinelHubClient:
    # CDSE (Copernicus Data Space Ecosystem) manzillari — 2-kodda ishlatilgan
    # va tasdiqlangan konfiguratsiyaga mos.
    token_url = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    )
    catalog_url = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"
    process_url = "https://sh.dataspace.copernicus.eu/api/v1/process"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = "https://sh.dataspace.copernicus.eu",
        token_url: str | None = None,
        proxy: str | None = None,
        timeout: float = 45.0,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        # CDSE identity hosti (identity.dataspace.copernicus.eu) ba'zi tarmoqlarda
        # bloklanganda so'rovlarni HTTP proksi orqali yo'naltirish uchun.
        # Bo'sh string None ga tenglashtiriladi — httpx bo'sh proxy URL ni
        # "Unknown scheme" xatosi bilan rad etadi.
        self.proxy = proxy or None
        self._access_token: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        # Konfiguratsiya moslashuvchan bo'lishi uchun instance darajasida
        # override qilish imkoniyati (class atributlari fallback bo'lib qoladi).
        self.base_url = base_url.rstrip("/")
        self.token_url = token_url or self.__class__.token_url
        self.catalog_url = f"{self.base_url}/api/v1/catalog/1.0.0/search"
        self.process_url = f"{self.base_url}/api/v1/process"

    def _get_client(self) -> httpx.AsyncClient:
        """Barcha so'rovlar uchun qayta ishlatiladigan HTTP klient.

        Har so'rovda yangi AsyncClient ochish har safar TCP/TLS handshake
        talab qiladi; bitta klient keep-alive orqali ulanishni qayta ishlatadi.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout, proxy=self.proxy)
        return self._client

    async def aclose(self) -> None:
        """Ichki HTTP klientni yopish (ilova to'xtatilganda chaqiriladi)."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        client = self._get_client()
        for attempt in range(3):
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                if response.status_code == 401:
                    # 401 ni qayta urinib bo'lmaydi — token yangilash yuqori darajada.
                    raise SentinelAuthError(
                        f"Sentinel Hub autentifikatsiya xatosi (401): {response.text[:500]}"
                    )
                if response.status_code >= 400:
                    logger.warning(
                        "Sentinel Hub error status=%d url=%s body=%s",
                        response.status_code,
                        url,
                        response.text[:2000],
                    )
                response.raise_for_status()
                return response
            except SentinelAuthError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise SentinelError(f"Sentinel Hub so'rovi bajarilmadi: {last_error!r}") from last_error

    async def _token(self) -> str:
        # Fast-path: tokenni keshdan qaytarish.
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        async with self._token_lock:
            # Lock ichida qayta tekshirish — parallel chaqiruvchilar bir token
            # uchun bir nechta so'rov yuborishining oldini olish.
            if self._access_token and time.time() < self._token_expires_at:
                return self._access_token
            response = await self._request(
                "POST",
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            payload = response.json()
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                raise SentinelError("Sentinel Hub access token qaytarmadi")
            expires_in = payload.get("expires_in")
            if not isinstance(expires_in, int | float):
                expires_in = 3600
            # 60 soniya zaxira — token muddati tugashidan oldin yangilaymiz.
            self._token_expires_at = time.time() + float(expires_in) - 60
            self._access_token = token
            return token

    async def _authorized_request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Bearer token bilan so'rov; 401 bo'lsa tokenni bir marta yangilab qaytaradi."""
        token = await self._token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            return await self._request(method, url, headers=headers, **kwargs)
        except SentinelAuthError:
            self._access_token = None
            self._token_expires_at = 0.0
            token = await self._token()
            headers = {"Authorization": f"Bearer {token}"}
            return await self._request(method, url, headers=headers, **kwargs)

    async def catalog(self, geometry: dict[str, Any], days: int = 14) -> list[CatalogItem]:
        now_dt = datetime.now(UTC)
        from_dt = now_dt - timedelta(days=days)
        now_str = now_dt.isoformat()
        from_str = from_dt.isoformat()
        payload: dict[str, Any] = {
            "collections": ["sentinel-2-l2a"],
            "datetime": f"{from_str}/{now_str}",
            "intersects": geometry,
            "limit": MAX_STORED_ACQUISITIONS,
            # CDSE katalogi "sortby" ni qabul qilmaydi; saralash quyida Python
            # tomonida acquired_at bo'yicha bajariladi.
            "fields": {"include": ["id", "geometry", "properties"], "exclude": []},
        }
        logger.info(
            "Sentinel catalog request (last %d days) window=%s/%s limit=%d",
            days,
            from_str,
            now_str,
            MAX_STORED_ACQUISITIONS,
        )
        response = await self._authorized_request("POST", self.catalog_url, json=payload)
        found: list[CatalogItem] = []
        for feature in response.json().get("features", []):
            properties = feature.get("properties", {})
            acquired_at = properties.get("datetime")
            product_id = properties.get("s2:product_uri") or feature.get("id")
            if not isinstance(acquired_at, str) or not isinstance(product_id, str):
                continue
            cloud = properties.get("eo:cloud_cover")

            found.append(
                CatalogItem(
                    acquired_at=acquired_at,
                    product_id=product_id,
                    revision_key=_revision_key(feature),
                    cloud_coverage=float(cloud) if isinstance(cloud, int | float) else None,
                    metadata={
                        "catalog_id": feature.get("id"),
                        "datetime": acquired_at,
                        "product_id": product_id,
                        "updated": properties.get("updated"),
                        "created": properties.get("created"),
                        "processing_baseline": properties.get("s2:processing_baseline"),
                        "cloud_coverage": cloud,
                    },
                )
            )
        latest = sorted(found, key=lambda item: item.acquired_at, reverse=True)[
            :MAX_STORED_ACQUISITIONS
        ]
        logger.info("Sentinel catalog returned latest_count=%d", len(latest))
        return sorted(latest, key=lambda item: item.acquired_at)


    @staticmethod
    def _catalog_items(payload: dict[str, Any]) -> list[CatalogItem]:
        found: list[CatalogItem] = []
        for feature in payload.get("features", []):
            properties = feature.get("properties", {})
            acquired_at = properties.get("datetime")
            product_id = properties.get("s2:product_uri") or feature.get("id")
            if not isinstance(acquired_at, str) or not isinstance(product_id, str):
                continue
            cloud = properties.get("eo:cloud_cover")
            found.append(
                CatalogItem(
                    acquired_at=acquired_at,
                    product_id=product_id,
                    revision_key=_revision_key(feature),
                    cloud_coverage=float(cloud) if isinstance(cloud, int | float) else None,
                    metadata={
                        "catalog_id": feature.get("id"),
                        "datetime": acquired_at,
                        "product_id": product_id,
                        "updated": properties.get("updated"),
                        "created": properties.get("created"),
                        "processing_baseline": properties.get("s2:processing_baseline"),
                        "cloud_coverage": cloud,
                    },
                )
            )
        return found

    async def catalog_range(self, geometry: dict[str, Any], from_date: date) -> list[CatalogItem]:
        """Return every real acquisition from the requested UTC date through now."""
        started_at = datetime.combine(from_date, dt_time.min, tzinfo=UTC).isoformat()
        ended_at = datetime.now(UTC).isoformat()
        request_payload: dict[str, Any] = {
            "collections": ["sentinel-2-l2a"],
            "datetime": f"{started_at}/{ended_at}",
            "intersects": geometry,
            "limit": 100,
            # CDSE katalogi "sortby" ni qabul qilmaydi; natijalar quyida
            # acquired_at bo'yicha saralanadi.
            "fields": {"include": ["id", "geometry", "properties"], "exclude": []},
        }
        found: dict[tuple[str, str], CatalogItem] = {}
        seen_tokens: set[str] = set()
        while True:
            response = await self._authorized_request(
                "POST", self.catalog_url, json=request_payload
            )
            body = response.json()
            for item in self._catalog_items(body):
                found[(item.product_id, item.revision_key)] = item

            context = body.get("context", {})
            next_token = context.get("next") if isinstance(context, dict) else None
            if not isinstance(next_token, str | int) or next_token == "":
                break
            token_key = str(next_token)
            if token_key in seen_tokens:
                break
            seen_tokens.add(token_key)
            request_payload["next"] = next_token

        items = sorted(found.values(), key=lambda item: item.acquired_at)
        logger.info("Sentinel catalog range returned from_date=%s count=%d", from_date, len(items))
        return items

    async def _process_tiff(
        self,
        geometry: dict[str, Any],
        acquired_at: str,
        evalscript: str,
        *,
        resampling: str,
    ) -> bytes:
        processing_geometry = _web_mercator_polygon(geometry)
        request = {
            "input": {
                "bounds": {
                    "geometry": processing_geometry,
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/3857"},
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {"from": acquired_at, "to": _iso_after(acquired_at)},
                            "mosaickingOrder": "mostRecent",
                        },
                        "processing": {"upsampling": resampling, "downsampling": resampling},
                    }
                ],
            },
            "output": {
                "resx": 10,
                "resy": 10,
                "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
            },
            "evalscript": evalscript,
        }
        response = await self._authorized_request("POST", self.process_url, json=request)
        return response.content

    async def raster(self, geometry: dict[str, Any], acquired_at: str) -> RasterData:
        # Eslatma: reflektans va maska alohida so'rovlarda olinadi. Bitta
        # so'rovga birlashtirish sinovdan o'tmadi: CDSE da SCL bandi
        # units="REFLECTANCE" ni qo'llamaydi (faqat DN), ikki input obyektli
        # variant esa ikki dataset talab qiladi va bunda API bo'sh (NaN)
        # raster qaytardi. Shu sababli tasdiqlangan ikki so'rovli sxema
        # saqlanadi — tezlik token keshi, keep-alive klient va parallel
        # yuklash orqali ta'minlanadi.
        reflectance_script = """//VERSION=3
function setup() {
  return { input: [{
             bands: ["B02","B03","B04","B05","B08","B8A","B11"],
             units: "REFLECTANCE"
           }],
           output: { bands: 7, sampleType: "FLOAT32" } };
}
function evaluatePixel(s) { return [s.B02,s.B03,s.B04,s.B05,s.B08,s.B8A,s.B11]; }
"""
        mask_script = """//VERSION=3
function setup() {
  return { input: [{ bands: ["SCL","dataMask"] }], output: { bands: 2, sampleType: "UINT8" } };
}
function evaluatePixel(s) { return [s.SCL,s.dataMask]; }
"""
        reflectance_payload, mask_payload = await asyncio.gather(
            self._process_tiff(geometry, acquired_at, reflectance_script, resampling="BILINEAR"),
            self._process_tiff(geometry, acquired_at, mask_script, resampling="NEAREST"),
        )
        reflectance = _as_channels_last(reflectance_payload, len(REFLECTANCE_BANDS))
        mask = _as_channels_last(mask_payload, 2)
        if reflectance.shape[:2] != mask.shape[:2]:
            raise SentinelError("Reflektans va maska gridlari bir xil emas")
        height, width = reflectance.shape[:2]
        coordinates = geometry["coordinates"][0]
        longitudes = [float(point[0]) for point in coordinates]
        latitudes = [float(point[1]) for point in coordinates]
        return RasterData(
            bands={name: reflectance[..., index] for index, name in enumerate(REFLECTANCE_BANDS)},
            scl=mask[..., 0].astype(np.uint8),
            data_mask=mask[..., 1] > 0,
            bbox=[min(longitudes), min(latitudes), max(longitudes), max(latitudes)],
            width=width,
            height=height,
        )


def valid_pixel_mask(raster: RasterData) -> npt.NDArray[np.bool_]:
    invalid_scl = np.isin(raster.scl, np.array([0, 1, 3, 8, 9, 10, 11], dtype=np.uint8))
    all_finite = np.logical_and.reduce([np.isfinite(value) for value in raster.bands.values()])
    return cast(
        npt.NDArray[np.bool_],
        (raster.data_mask & ~invalid_scl & all_finite).astype(np.bool_),
    )
