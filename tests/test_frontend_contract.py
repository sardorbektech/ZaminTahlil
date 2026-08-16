from pathlib import Path


def test_layer_order_navigation_comparison_and_session_storage() -> None:
    source = Path("app/static/app.js").read_text()
    assert 'const LAYERS = ["RGB", "NDVI", "NDMI", "NDRE", "EVI", "BSI"]' in source
    assert all(name not in source for name in ("SAVI", "GNDVI", "NDWI", "NBR", "OSAVI"))
    assert "state.compare" in source and "applySwipe" in source
    assert "sessionStorage.setItem" in source and ".slice(-10)" in source
    assert "/artifacts" in source and ".image_url" in source
    assert "/annual-metrics" in source and "Date.parse" in source
    assert "/historical-metrics" in source and "from_date" in source
    assert "loadHistoryButton" in source and "chartFromDate" in source
    assert "World_Imagery" in source and "drawFieldBoundary" in source
    assert "imageMap.invalidateSize()" in source
    assert "advice-card" in source and "recommendation.groupRedTitle" in source
    assert "product_id" in source and "valid_pixel_count" in source
    assert "render_version" in source and "layer_valid_pixel_count" in source
    assert "processing_error" in source
