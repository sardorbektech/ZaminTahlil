import pytest

from app.geometry import (
    GeometryError,
    canonical_geojson_and_hash,
    geodesic_area_hectares,
    validate_polygon_geojson,
)


def test_valid_polygon_and_geodesic_area(polygon_geojson: dict[str, object]) -> None:
    polygon = validate_polygon_geojson(polygon_geojson)
    area = geodesic_area_hectares(polygon)
    assert 90 < area < 100


@pytest.mark.parametrize(
    "geometry, message",
    [
        ({"type": "Point", "coordinates": [69, 41]}, "Polygon"),
        (
            {"type": "Polygon", "coordinates": [[[69, 41], [70, 41], [70, 42], [69, 42]]]},
            "yopiq",
        ),
        (
            {
                "type": "Polygon",
                "coordinates": [[[181, 41], [70, 41], [70, 42], [181, 41]]],
            },
            "Longitude",
        ),
        (
            {
                "type": "Polygon",
                "coordinates": [[[41, 91], [42, 41], [42, 42], [41, 91]]],
            },
            "Latitude",
        ),
    ],
)
def test_polygon_validation_rejects_invalid_geometry(
    geometry: dict[str, object], message: str
) -> None:
    with pytest.raises(GeometryError, match=message):
        validate_polygon_geojson(geometry)


def test_canonical_hash_is_rotation_independent(polygon_geojson: dict[str, object]) -> None:
    rotated = {
        "type": "Polygon",
        "coordinates": [
            [[69.21, 41.21], [69.20, 41.21], [69.20, 41.20], [69.21, 41.20], [69.21, 41.21]]
        ],
    }
    _, first_hash = canonical_geojson_and_hash(validate_polygon_geojson(polygon_geojson))
    _, second_hash = canonical_geojson_and_hash(validate_polygon_geojson(rotated))
    assert first_hash == second_hash
