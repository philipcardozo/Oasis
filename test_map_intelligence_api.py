import json

from fastapi.testclient import TestClient

from map_api import DATA, app, features_for_layer, parse_bbox, public_cameras_geojson


def test_main() -> None:
    bbox = parse_bbox({"bbox": ["-180,-90,180,90"]})
    farms = features_for_layer("farms", bbox)
    farm_parcels = features_for_layer("farm_parcels", bbox)
    soil = features_for_layer("soil_quality", bbox)
    crop = features_for_layer("crop_history", bbox)
    industrial = features_for_layer("industrial", bbox)
    data_centers = features_for_layer("data_centers", bbox)
    transmission = features_for_layer("transmission_lines", bbox)
    government = features_for_layer("government_facilities", bbox)
    regulatory = features_for_layer("regulatory_zones", bbox)
    marketplace = features_for_layer("marketplace", bbox)
    cameras = public_cameras_geojson(bbox)
    assert farms["features"]
    assert farm_parcels["features"]
    assert any(f["geometry"]["type"] == "Polygon" for f in farm_parcels["features"])
    assert all(f["properties"]["layer"] == "farm-soil-quality" for f in soil["features"])
    assert all(f["properties"]["layer"] == "farm-crop-history" for f in crop["features"])
    assert industrial["features"]
    assert data_centers["features"]
    assert all(f["properties"]["layer"] == "industrial-data-centers" for f in data_centers["features"])
    assert transmission["features"]
    assert all(f["properties"]["layer"] == "industrial-transmission" for f in transmission["features"])
    assert any(f["geometry"]["type"] == "Polygon" for f in industrial["features"])
    assert government["features"]
    assert regulatory["features"]
    assert all(f["properties"]["layer"] == "government-regulatory-zones" for f in regulatory["features"])
    assert marketplace["features"]
    assert any(f["properties"]["layer"] == "marketplace-houses" for f in marketplace["features"])
    assert all(f["properties"]["layer"] for f in farms["features"] + industrial["features"])
    assert all(f["properties"]["legal_public_access"] is True for f in cameras["features"])

    client = TestClient(app)
    assert client.get("/api/map/layers").status_code == 200
    # Default terrain is AWS terrarium (client-side); this status reports the
    # optional local 3DEP source. Local-specific fields only assert when present.
    dem_status = client.get("/api/reliefs/dem/status").json()
    assert dem_status["source"] in ("aws", "local")
    assert dem_status["ready"] is True
    assert "2Lp" not in str(dem_status)
    if dem_status["available"]:  # local 3DEP tiles are built
        assert dem_status["tilejson"]["encoding"] == "mapbox"
        assert client.get("/api/reliefs/dem/tilejson").json()["tiles"]
    assert isinstance(client.get("/api/reliefs/terrain/sources").json()["sources"], list)
    assert client.get("/api/reliefs/terrain/coverage").status_code == 200
    assert client.get("/api/reliefs/terrain/jobs/status").status_code == 200
    source_status = client.get("/api/data-sources/status").json()
    assert all(c["ok"] for c in source_status["checks"])
    html = client.get("/").text
    assert "unpkg.com/maplibre-gl" not in html
    assert "vendor/maplibre-gl/5.6.2/maplibre-gl.js" in client.get("/js/main.js").text
    for cache_path in ("/vendor/maplibre-gl/5.6.2/maplibre-gl.css", "/vendor/maplibre-gl/5.6.2/maplibre-gl.js"):
        first = client.get(cache_path, headers={"accept-encoding": "gzip"})
        assert first.status_code == 200
        assert first.headers["etag"]
        assert first.headers["cache-control"] == "public, max-age=31536000, immutable"
        second = client.get(cache_path, headers={"if-none-match": first.headers["etag"], "accept-encoding": "gzip"})
        assert second.status_code == 304
        assert not second.content
    for cache_path in ("/", "/index.html", "/js/main.js", "/js/config.js", "/js/state.js", "/css/app.css"):
        first = client.get(cache_path, headers={"accept-encoding": "gzip"})
        assert first.status_code == 200
        assert first.headers["etag"]
        assert first.headers["cache-control"] == "public, max-age=60, must-revalidate"
        second = client.get(cache_path, headers={"if-none-match": first.headers["etag"], "accept-encoding": "gzip"})
        assert second.status_code == 304
        assert not second.content
    bootstrap_signals = client.get("/api/bootstrap/signals").json()
    assert isinstance(bootstrap_signals["aliases"], dict)
    assert isinstance(bootstrap_signals["hq_coords"], dict)
    assert bootstrap_signals["news"] is None
    assert bootstrap_signals["edge_candidates"] == []
    assert bootstrap_signals["location_unknown_count"] == len(client.get("/api/location/unknown").json())
    ui_bulk = client.get("/api/universe/bulk").json()
    assert ui_bulk["nodes"]
    assert "entity_model" not in ui_bulk["nodes"][0]
    assert len(ui_bulk["nodes"]) == len(json.loads((DATA / "universe_bulk.json").read_text())["nodes"])
    full_entities = client.get("/api/map/entities.geojson").json()
    world_bbox_entities = client.get("/api/map/entities.geojson?bbox=-180,-90,180,90").json()
    assert world_bbox_entities == full_entities
    for cache_path in (
        "/data/universe_core.json",
        "/api/map/layers",
        "/api/bootstrap/signals",
        "/api/universe/bulk",
        "/api/map/entities.geojson",
        "/api/map/entities.geojson?bbox=-180,-90,180,90",
        "/api/map/relationships.geojson",
        "/api/map/relationships.geojson?bbox=-180,-90,180,90",
        "/api/map/features.geojson?layer=industrial_assets",
        "/api/map/features.geojson?layer=industrial_assets&bbox=-180,-90,180,90",
        "/api/map/features.geojson?layer=marketplace&bbox=-180,-90,180,90",
        "/api/assets/search?asset_type=farm&bbox=-180,-90,180,90",
        "/api/assets/search?bbox=-180,-90,180,90",
        "/api/listings/search?format=geojson&asset_type=farm&bbox=-180,-90,180,90",
        "/api/listings/search?asset_type=house&bbox=-180,-90,180,90",
        "/api/cameras/public.geojson?bbox=-180,-90,180,90",
        "/api/permits/search?bbox=-180,-90,180,90",
        "/api/location/unknown",
        "/api/entity/GM",
        "/api/entity/GM/neighborhood",
        "/api/entity/GM/combined-neighborhood?depth=2",
        "/api/entity/GM/reverse-dcf",
        "/api/entity/GM/comps?cap=8",
        "/api/entity/GM/events",
        "/api/entity/GM/political",
        "/api/entity/GM/risk",
        "/api/entity/USDA/assets",
        "/api/entity/USDA/asset-map.geojson",
        "/api/data-quality/dashboard",
        "/api/assets/asset%3Ademo-farm-iowa",
        "/api/assets/asset%3Ademo-farm-iowa/due-diligence",
        "/api/assets/asset%3Ademo-farm-iowa/valuation?case=base",
        "/api/assets/asset%3Ademo-farm-iowa/risk-score",
        "/api/assets/asset%3Ademo-farm-iowa/valuation-assumptions",
        "/api/assets/asset%3Ademo-farm-iowa/scenario?case=bull",
        "/api/assets/asset%3Ademo-farm-iowa/entities",
        "/api/assets/asset%3Ademo-farm-iowa/relationship-graph",
        "/api/assets/asset%3Ademo-farm-iowa/nearby-infrastructure",
        "/api/assets/asset%3Ademo-farm-iowa/risk-summary",
        "/api/listings/listing%3Ademo-farm-iowa",
        "/api/evidence?object_type=asset&object_id=asset%3Ademo-farm-iowa",
        "/api/evidence/ev%3Aasset_asset_demo-farm-iowa_acreage_public_seed_640",
        "/api/data-quality/summary",
        "/api/data-quality/layer/farms",
        "/api/data-sources/status",
        "/api/reliefs/dem/status",
        "/api/reliefs/terrain/sources",
        "/api/reliefs/terrain/coverage",
        "/api/reliefs/terrain/jobs/status",
        "/api/reports/asset/asset%3Ademo-farm-iowa",
    ):
        first = client.get(cache_path, headers={"accept-encoding": "gzip"})
        assert first.status_code == 200
        assert first.headers["etag"]
        assert first.headers["cache-control"] == "public, max-age=60, must-revalidate"
        second = client.get(cache_path, headers={"if-none-match": first.headers["etag"], "accept-encoding": "gzip"})
        assert second.status_code == 304
        assert not second.content
    assert client.get("/api/map/features.geojson?layer=farms&bbox=-180,-90,180,90").json()["features"]
    assert client.get("/api/map/features.geojson?layer=farm_parcels&bbox=-180,-90,180,90").json()["features"]
    assert client.get("/api/map/features.geojson?layer=industrial_assets&bbox=-180,-90,180,90").json()["features"]
    assert client.get("/api/map/features.geojson?layer=government_facilities&bbox=-180,-90,180,90").json()["features"]
    assert client.get("/api/map/features.geojson?layer=regulatory_zones&bbox=-180,-90,180,90").json()["features"]
    listings_geo = client.get("/api/listings/search?format=geojson&asset_type=farm&bbox=-180,-90,180,90").json()
    assert listings_geo["features"]
    listing = client.get("/api/listings/search?asset_type=house&bbox=-180,-90,180,90").json()["listings"][0]
    assert client.get(f"/api/listings/{listing['id']}").json()["listing"]["id"] == listing["id"]
    asset = client.get("/api/assets/search?asset_type=farm&bbox=-180,-90,180,90").json()["assets"][0]
    diligence = client.get(f"/api/assets/{asset['id']}/due-diligence").json()
    assert diligence["asset"]["id"] == asset["id"]
    assert diligence["asset"]["farm_profile"]["current_estimated_value"]
    industrial_asset = client.get("/api/assets/search?asset_type=power_plant&bbox=-180,-90,180,90").json()["assets"][0]
    industrial_diligence = client.get(f"/api/assets/{industrial_asset['id']}/due-diligence").json()
    assert industrial_diligence["asset"]["industrial_profile"]["power_capacity_mw"]
    gov_asset = client.get("/api/assets/search?asset_type=government_facility&bbox=-180,-90,180,90").json()["assets"][0]
    assert client.get(f"/api/assets/{gov_asset['id']}/due-diligence").json()["asset"]["facility_type"]
    assert client.get("/api/permits/search?bbox=-180,-90,180,90").json()["permits"]
    assert client.get("/api/assets/search?asset_type=farm&min_price=1&max_price=7000000&bbox=-180,-90,180,90").json()["assets"]
    assert client.get(f"/api/assets/{asset['id']}/entities").json()["asset_id"] == asset["id"]
    assert client.get(f"/api/assets/{asset['id']}/nearby-infrastructure").json()["nearby_infrastructure"]
    assert client.get(f"/api/assets/{asset['id']}/risk-summary").json()["asset_id"] == asset["id"]
    valuation = client.get(f"/api/assets/{asset['id']}/valuation").json()
    assert valuation["estimated_annual_revenue"] is not None
    assert valuation["score_breakdown"]
    assert client.get(f"/api/assets/{asset['id']}/risk-score").json()["breakdown"]
    assert client.get(f"/api/assets/{asset['id']}/valuation-assumptions").json()["assumptions"]
    posted = client.post(f"/api/assets/{asset['id']}/valuation-assumptions", json={"case": "custom", "assumptions": {"revenue": 123456, "cost": 65432, "discount_rate": 0.11}}).json()
    assert posted["assumptions"]["revenue"] == 123456
    assert client.get(f"/api/assets/{asset['id']}/scenario?case=bull").json()["case"] == "bull"
    assert client.get(f"/api/assets/{asset['id']}/scenario?case=bear").json()["case"] == "bear"
    evidence = client.get(f"/api/evidence?object_type=asset&object_id={asset['id']}").json()["evidence"]
    assert evidence
    assert {"source_name", "confidence", "claim_type"} <= set(evidence[0])
    assert client.get(f"/api/evidence/{evidence[0]['id']}").status_code == 200
    quality = client.get("/api/data-quality/summary").json()
    assert quality["total_evidence_records"] >= len(evidence)
    assert client.get("/api/data-quality/layer/farms").json()["metrics"]["farms_loaded"] >= 1
    dashboard_quality = client.get("/api/data-quality/dashboard").json()
    assert dashboard_quality["summary"]["total_evidence_records"] == quality["total_evidence_records"]
    assert dashboard_quality["layers"]["farms"]["metrics"]["farms_loaded"] >= 1
    override = client.post("/api/overrides", json={"object_type": "asset", "object_id": asset["id"], "field_name": "acreage", "old_value": None, "new_value": "reviewed", "user_note": "test correction"}).json()["override"]
    assert client.get(f"/api/overrides?object_type=asset&object_id={asset['id']}").json()["overrides"]
    assert client.delete(f"/api/overrides/{override['id']}").json()["ok"] is True
    report_preview = client.get(f"/api/reports/asset/{asset['id']}").json()
    assert report_preview["evidence_source_appendix"]
    report = client.post(f"/api/reports/asset/{asset['id']}/generate", json={"report_type": "farm acquisition report"}).json()
    assert report["ok"] is True
    assert client.get(report["html"]).status_code == 200
    assert client.get(report["csv"]).status_code == 200
    for download_path in (report["html"], report["json"], report["csv"]):
        first = client.get(download_path)
        assert first.status_code == 200
        assert first.headers["etag"]
        second = client.get(download_path, headers={"if-none-match": first.headers["etag"]})
        assert second.status_code == 304
        assert not second.content
    dcf = client.get("/api/entity/BLK/dcf.xlsx?method=cash_flow")
    assert dcf.status_code == 200
    assert dcf.headers["etag"]
    dcf_cached = client.get("/api/entity/BLK/dcf.xlsx?method=cash_flow", headers={"if-none-match": dcf.headers["etag"]})
    assert dcf_cached.status_code == 304
    assert not dcf_cached.content
    assert client.get("/api/entity/USDA/assets").json()["assets"]
    assert client.get("/api/evidence?object_type=entity&object_id=USDA").json()["evidence"]
    assert client.post("/api/reports/entity/USDA/generate", json={}).json()["html"]
    assert client.get("/api/entity/USDA/asset-map.geojson").json()["features"]
    assert client.get(f"/api/assets/{asset['id']}/relationship-graph").json()["nodes"]
    assert client.get("/api/entity/USDA/combined-neighborhood?depth=2").json()["assets"]
    rel_types = {e["relationship_type"] for e in client.get("/api/assets/asset%3Ademo-data-center-phx/relationship-graph").json()["edges"]}
    assert {"OPERATES", "FINANCES", "PERMITS", "CONNECTED_TO"} & rel_types
    gm_assets = client.get("/api/entity/GM/assets").json()["assets"]
    assert {a["asset_relationship"]["relationship_type"] for a in gm_assets} >= {"OPERATES", "SUPPLIES"}
    assert client.get("/api/cameras/public.geojson?bbox=-180,-90,180,90").status_code == 200
    assert client.get("/api/assets/search?bbox=bad").status_code == 400
    print("map intelligence api ok")


if __name__ == "__main__":
    test_main()
