from pathlib import Path


# The UI is split across index.html + ES modules under graph/js/ + graph/css/;
# assert tokens against the whole served bundle, not just the HTML shell.
HTML = Path("graph/index.html").read_text()
for _f in sorted(Path("graph/js").glob("*.js")) + sorted(Path("graph/css").glob("*.css")):
    HTML += "\n" + _f.read_text()


def test_main() -> None:
    for token in [
        'class="rail"',
        'id="gearBtn"',
        'id="dataBtn"',
        'id="gearPanel"',
        'id="studioBtn"',
        'id="studioPanel"',
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
        "function renderMapStudio",
        "function switchBasemap",
        "function saveMapSlot",
        "Satellite Site Analysis",
        "not loaded yet",
        "function buildToolKinds",
        'data-rail="engine"',
        'data-rail="maker"',
        'data-rail="lenses"',
        # Prompt 07 product shell: left-nav surfaces, command bar, drawer, theme vars.
        'class="rail"',
        'data-rail="map"',
        'data-rail="network"',
        'data-rail="research"',
        'data-rail="model"',
        'id="search"',        # command bar input
        "metaKey",            # Cmd/Ctrl-K command-bar focus
        'id="detail"',        # right drawer
        "--accent",           # theme custom properties (Engine hook)
        "--panel",
        "--border",
    ]:
        assert token in HTML, token
    assert 'class="panel-card filters"' not in HTML
    print("product shell ok")


def test_drawer_type_coverage() -> None:
    # Prompt 08: the per-type drawer config must cover every node_type in the graph.
    import json
    core_path = Path("graph/data/universe_core.json")
    if not core_path.exists():
        import pytest
        pytest.skip("universe_core.json not built")
    types = {n.get("node_type") for n in json.loads(core_path.read_text())["nodes"] if n.get("node_type")}
    config = Path("graph/js/config.js").read_text()
    block = config[config.index("DRAWER_TYPES"):]
    for t in sorted(types):
        assert f"\n  {t}:" in block, f"DRAWER_TYPES missing node_type: {t}"
    print(f"drawer config covers node_types: {sorted(types)}")


def test_builtin_lenses_validate() -> None:
    # Prompt 12: built-in lens presets must reference real node kinds / edge rels.
    import re
    from store import load_edges, load_nodes
    main = Path("graph/js/main.js").read_text()
    block = main[main.index("const LENS_PRESETS="):main.index("const LENS_PRESETS=") + 400]
    assert "company:" in block and "security:" in block, block
    kinds = {n.get("kind") for n in load_nodes()}
    rels = {l.get("rel") for l in load_edges()}
    for grp, valid in (("kind", kinds), ("rel", rels)):
        for m in re.finditer(grp + r":\{([^}]*)\}", block):
            for key in re.findall(r"(\w+):", m.group(1)):
                assert key in valid, f"lens {grp} '{key}' not a real filter"
    print("built-in lenses validate")


if __name__ == "__main__":
    test_main()
    test_drawer_type_coverage()
    test_builtin_lenses_validate()
