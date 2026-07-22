import hashlib
import json
from collections.abc import Sequence
from typing import Any

from pyproj import Geod
from shapely.geometry import Polygon, shape
from shapely.geometry.polygon import orient
from shapely.validation import explain_validity


class GeometryError(ValueError):
    pass


def _validate_position(position: Sequence[Any]) -> tuple[float, float]:
    if len(position) != 2:
        raise GeometryError("Har bir koordinata aynan [longitude, latitude] bo'lishi kerak")
    if isinstance(position[0], bool) or isinstance(position[1], bool):
        raise GeometryError("Koordinatalar son bo'lishi kerak")
    try:
        longitude, latitude = float(position[0]), float(position[1])
    except (TypeError, ValueError) as exc:
        raise GeometryError("Koordinatalar son bo'lishi kerak") from exc
    if not -180 <= longitude <= 180:
        raise GeometryError("Longitude -180 va 180 oralig'ida bo'lishi kerak")
    if not -90 <= latitude <= 90:
        raise GeometryError("Latitude -90 va 90 oralig'ida bo'lishi kerak")
    return longitude, latitude


def validate_polygon_geojson(geometry: dict[str, Any]) -> Polygon:
    if geometry.get("type") != "Polygon":
        raise GeometryError("Geometriya turi Polygon bo'lishi kerak")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise GeometryError("Polygon koordinatalari bo'sh bo'lmasligi kerak")
    normalized: list[list[tuple[float, float]]] = []
    for ring in coordinates:
        if not isinstance(ring, list) or len(ring) < 4:
            raise GeometryError("Har bir polygon halqasi kamida 4 nuqtadan iborat bo'lishi kerak")
        parsed = [_validate_position(position) for position in ring]
        if parsed[0] != parsed[-1]:
            raise GeometryError("Polygon halqasi yopiq bo'lishi kerak")
        normalized.append(parsed)
    polygon = shape({"type": "Polygon", "coordinates": normalized})
    if not isinstance(polygon, Polygon) or polygon.is_empty or polygon.area == 0:
        raise GeometryError("Polygon bo'sh yoki maydonsiz")
    if not polygon.is_valid:
        raise GeometryError(f"Yaroqsiz polygon: {explain_validity(polygon)}")
    return polygon


def geodesic_area_hectares(polygon: Polygon) -> float:
    area_m2, _ = Geod(ellps="WGS84").geometry_area_perimeter(polygon)
    return abs(area_m2) / 10_000.0


def _rotate_ring(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    open_ring = ring[:-1]
    start = min(range(len(open_ring)), key=lambda index: open_ring[index])
    rotated = open_ring[start:] + open_ring[:start]
    return [*rotated, rotated[0]]


def canonical_geojson_and_hash(polygon: Polygon) -> tuple[dict[str, Any], str]:
    normalized = orient(polygon, sign=1.0)
    exterior = _rotate_ring([(round(x, 7), round(y, 7)) for x, y in normalized.exterior.coords])
    holes = sorted(
        (
            _rotate_ring([(round(x, 7), round(y, 7)) for x, y in ring.coords])
            for ring in normalized.interiors
        ),
        key=lambda ring: ring[0],
    )
    geojson: dict[str, Any] = {
        "type": "Polygon",
        "coordinates": [[list(point) for point in exterior]]
        + [[[x, y] for x, y in ring] for ring in holes],
    }
    payload = json.dumps(geojson, sort_keys=True, separators=(",", ":"))
    return geojson, hashlib.sha256(payload.encode()).hexdigest()
