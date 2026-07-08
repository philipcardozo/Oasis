from pathlib import Path


HTML = Path("graph/index.html").read_text()


def test_main() -> None:
    for token in [
        'class="rail"',
        'id="gearBtn"',
        'id="dataBtn"',
        'id="gearPanel"',
        'id="dataPanel"',
        'id="toolThemeBtn"',
        'id="toolGlobeBtn"',
        'id="toolModeBtn"',
        'id="sectorFilters"',
        'id="groupFilters"',
        'id="relFilters"',
        "PRODUCT_PREF_KEY",
        "MANUAL_LAYER_KEY",
        "function addManualNodeAtCenter",
        "function activateLens",
        "function applyProductPrefs",
        "function configureMapGestures",
        "map.dragRotate?.enable?.();",
        "function normalizeBaseMapLabels",
        "function buildToolKinds",
        'data-rail="engine"',
        'data-rail="maker"',
        'data-rail="lenses"',
    ]:
        assert token in HTML, token
    assert 'class="panel-card filters"' not in HTML
    print("product shell ok")


if __name__ == "__main__":
    test_main()
