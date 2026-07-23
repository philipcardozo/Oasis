#!/usr/bin/env python3
"""Probe lower-traffic route families for performance evidence coverage.

This is not a load test. It measures representative safe routes that were not
covered by the primary browser/auth performance matrix. Persistent mutation
routes are skipped unless they can be safely contained or cleaned up.
"""

from __future__ import annotations

import hashlib
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "performance"
REPORTS_DIR = ROOT / "graph" / "data" / "reports"
sys.path.insert(0, str(ROOT))


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def timed(fn: Callable[[], Any]) -> tuple[float, Any]:
    started = time.perf_counter()
    response = fn()
    return (time.perf_counter() - started) * 1000, response


def compact_shape(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        counts = {}
        scalars = {}
        for key, item in value.items():
            if isinstance(item, (list, dict)):
                counts[str(key)] = len(item)
            elif isinstance(item, (str, int, float, bool)) or item is None:
                scalars[str(key)] = item
        out: dict[str, Any] = {"type": "object", "keys": sorted(map(str, value))}
        if counts:
            out["counts"] = counts
        if scalars:
            out["scalars"] = scalars
        return out
    if isinstance(value, list):
        return {"type": "array", "count": len(value)}
    return {"type": type(value).__name__}


def clear_map_api_caches(map_api: Any) -> None:
    for value in vars(map_api).values():
        cache_clear = getattr(value, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


@contextmanager
def temporary_persistent_json_paths(map_api: Any):
    names = ("OVERRIDES", "VALUATION_ASSUMPTIONS", "USER_OVERRIDES", "WATCHLISTS")
    original = {name: getattr(map_api, name) for name in names}
    with tempfile.TemporaryDirectory(prefix="oasis-route-probe-") as tmp:
        root = Path(tmp)
        map_api.OVERRIDES = root / "location_overrides.json"
        map_api.VALUATION_ASSUMPTIONS = root / "valuation_assumptions.json"
        map_api.USER_OVERRIDES = root / "user_overrides.json"
        map_api.WATCHLISTS = root / "watchlists.json"
        clear_map_api_caches(map_api)
        try:
            yield
        finally:
            for name, value in original.items():
                setattr(map_api, name, value)
            clear_map_api_caches(map_api)


@contextmanager
def temporary_dem_tilejson_paths():
    import data_sources

    names = ("UNIFIED_TILEJSON_PATH", "TILEJSON_PATH")
    original = {name: getattr(data_sources, name) for name in names}
    with tempfile.TemporaryDirectory(prefix="oasis-tilejson-probe-") as tmp:
        root = Path(tmp)
        data_sources.UNIFIED_TILEJSON_PATH = root / "terrain-rgb" / "tiles.json"
        data_sources.TILEJSON_PATH = root / "usgs_3dep" / "tiles.json"
        data_sources.UNIFIED_TILEJSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        data_sources.UNIFIED_TILEJSON_PATH.write_text(json.dumps({
            "tilejson": "2.2.0",
            "name": "OASIS performance probe DEM tilejson",
            "description": "Temporary fixture used only by route_family_performance_probe.py.",
            "version": "1.0.0",
            "scheme": "xyz",
            "tiles": ["/tiles/terrain-rgb/{z}/{x}/{y}.png"],
            "minzoom": 6,
            "maxzoom": 6,
            "bounds": [-85.0, 34.0, -84.0, 35.0],
            "center": [-84.5, 34.5, 6],
            "encoding": "mapbox",
            "attribution": "temporary performance probe fixture",
        }, indent=2) + "\n")
        data_sources._dem_tilejson_cached.cache_clear()
        try:
            yield
        finally:
            for name, value in original.items():
                setattr(data_sources, name, value)
            data_sources._dem_tilejson_cached.cache_clear()


def measure(client: TestClient, spec: dict[str, Any], samples: int) -> dict[str, Any]:
    durations = []
    statuses = []
    lengths = []
    headers = {}
    first_body = b""
    method = spec["method"]
    path = spec["path"]
    kwargs = spec.get("kwargs") or {}
    for i in range(samples):
        duration, response = timed(lambda: client.request(method, path, headers={"accept-encoding": "gzip"}, **kwargs))
        durations.append(duration)
        statuses.append(response.status_code)
        lengths.append(len(response.content))
        if i == 0:
            first_body = response.content
            headers = {
                key: response.headers[key]
                for key in ("cache-control", "content-encoding", "content-length", "content-type", "etag")
                if key in response.headers
            }
    out: dict[str, Any] = {
        "name": spec["name"],
        "method": method,
        "path": path,
        "template": spec.get("template", path.split("?", 1)[0]),
        "family": spec.get("family"),
        "samples": samples,
        "status_codes": sorted(set(statuses)),
        "body_bytes_min": min(lengths),
        "body_bytes_max": max(lengths),
        "p50_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "min_ms": round(min(durations), 3),
        "max_ms": round(max(durations), 3),
        "body_sha256": hashlib.sha256(first_body).hexdigest(),
        "headers": headers,
    }
    ctype = headers.get("content-type", "")
    if "json" in ctype or path.endswith(".geojson"):
        try:
            out["json_shape"] = compact_shape(json.loads(first_body))
        except Exception as exc:
            out["json_shape_error"] = str(exc)
    return out


def measure_dynamic(
    client: TestClient,
    spec: dict[str, Any],
    samples: int,
    request_for_index: Callable[[int], tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    durations = []
    statuses = []
    lengths = []
    headers = {}
    first_body = b""
    for i in range(samples):
        path, kwargs = request_for_index(i)
        duration, response = timed(
            lambda: client.request(spec["method"], path, headers={"accept-encoding": "gzip"}, **kwargs)
        )
        durations.append(duration)
        statuses.append(response.status_code)
        lengths.append(len(response.content))
        if i == 0:
            first_body = response.content
            headers = {
                key: response.headers[key]
                for key in ("cache-control", "content-encoding", "content-length", "content-type", "etag")
                if key in response.headers
            }
    out: dict[str, Any] = {
        "name": spec["name"],
        "method": spec["method"],
        "path": spec["path"],
        "template": spec.get("template", spec["path"]),
        "family": spec.get("family"),
        "samples": samples,
        "status_codes": sorted(set(statuses)),
        "body_bytes_min": min(lengths),
        "body_bytes_max": max(lengths),
        "p50_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "min_ms": round(min(durations), 3),
        "max_ms": round(max(durations), 3),
        "body_sha256": hashlib.sha256(first_body).hexdigest(),
        "headers": headers,
    }
    ctype = headers.get("content-type", "")
    if "json" in ctype:
        try:
            out["json_shape"] = compact_shape(json.loads(first_body))
        except Exception as exc:
            out["json_shape_error"] = str(exc)
    return out


def representative_ids() -> dict[str, str]:
    import map_api

    data = map_api.intel()
    assets = [row for row in data.get("assets", []) if row.get("id")]
    listings = [row for row in data.get("asset_listings", []) if row.get("id")]
    evidence = map_api.generated_evidence()
    return {
        "asset_id": assets[0]["id"] if assets else "asset:demo-farm-iowa",
        "listing_id": listings[0]["id"] if listings else "listing:demo-farm-iowa",
        "evidence_id": evidence[0]["id"] if evidence else "ev:missing",
        "entity_id": "GM",
    }


def probe_specs(ids: dict[str, str]) -> list[dict[str, Any]]:
    asset = ids["asset_id"]
    listing = ids["listing_id"]
    evidence = ids["evidence_id"]
    entity = ids["entity_id"]
    bbox = "-180,-90,180,90"
    return [
        {"name": "asset search", "method": "GET", "path": "/api/assets/search?limit=20", "template": "/api/assets/search", "family": "assets/due diligence"},
        {"name": "asset profile", "method": "GET", "path": f"/api/assets/{asset}", "template": "/api/assets/{asset_id}", "family": "assets/due diligence"},
        {"name": "asset due diligence", "method": "GET", "path": f"/api/assets/{asset}/due-diligence", "template": "/api/assets/{asset_id}/due-diligence", "family": "assets/due diligence"},
        {"name": "asset entities", "method": "GET", "path": f"/api/assets/{asset}/entities", "template": "/api/assets/{asset_id}/entities", "family": "assets/due diligence"},
        {"name": "asset nearby infrastructure", "method": "GET", "path": f"/api/assets/{asset}/nearby-infrastructure", "template": "/api/assets/{asset_id}/nearby-infrastructure", "family": "assets/due diligence"},
        {"name": "asset relationship graph", "method": "GET", "path": f"/api/assets/{asset}/relationship-graph", "template": "/api/assets/{asset_id}/relationship-graph", "family": "assets/due diligence"},
        {"name": "asset risk score", "method": "GET", "path": f"/api/assets/{asset}/risk-score", "template": "/api/assets/{asset_id}/risk-score", "family": "assets/due diligence"},
        {"name": "asset risk summary", "method": "GET", "path": f"/api/assets/{asset}/risk-summary", "template": "/api/assets/{asset_id}/risk-summary", "family": "assets/due diligence"},
        {"name": "asset scenario", "method": "GET", "path": f"/api/assets/{asset}/scenario", "template": "/api/assets/{asset_id}/scenario", "family": "assets/due diligence"},
        {"name": "asset valuation", "method": "GET", "path": f"/api/assets/{asset}/valuation", "template": "/api/assets/{asset_id}/valuation", "family": "assets/due diligence"},
        {"name": "asset valuation assumptions", "method": "GET", "path": f"/api/assets/{asset}/valuation-assumptions", "template": "/api/assets/{asset_id}/valuation-assumptions", "family": "assets/due diligence"},
        {"name": "cameras public", "method": "GET", "path": f"/api/cameras/public.geojson?bbox={bbox}", "template": "/api/cameras/public.geojson", "family": "api"},
        {"name": "data-quality layer farms", "method": "GET", "path": "/api/data-quality/layer/farms", "template": "/api/data-quality/layer/{layer_name}", "family": "data quality"},
        {"name": "data-quality summary", "method": "GET", "path": "/api/data-quality/summary", "template": "/api/data-quality/summary", "family": "data quality"},
        {"name": "data sources status", "method": "GET", "path": "/api/data-sources/status", "template": "/api/data-sources/status", "family": "api"},
        {"name": "entity asset map", "method": "GET", "path": f"/api/entity/{entity}/asset-map.geojson", "template": "/api/entity/{entity_id}/asset-map.geojson", "family": "entity drawer/model"},
        {"name": "entity combined neighborhood", "method": "GET", "path": f"/api/entity/{entity}/combined-neighborhood", "template": "/api/entity/{entity_id}/combined-neighborhood", "family": "entity drawer/model"},
        {"name": "entity neighborhood", "method": "GET", "path": f"/api/entity/{entity}/neighborhood", "template": "/api/entity/{entity_id}/neighborhood", "family": "entity drawer/model"},
        {"name": "evidence one", "method": "GET", "path": f"/api/evidence/{evidence}", "template": "/api/evidence/{evidence_id}", "family": "evidence/overrides"},
        {"name": "listings search", "method": "GET", "path": "/api/listings/search?asset_type=farm", "template": "/api/listings/search", "family": "api"},
        {"name": "listing profile", "method": "GET", "path": f"/api/listings/{listing}", "template": "/api/listings/{listing_id}", "family": "api"},
        {"name": "location unknown", "method": "GET", "path": "/api/location/unknown", "template": "/api/location/unknown", "family": "api"},
        {"name": "map features farms", "method": "GET", "path": f"/api/map/features.geojson?layer=farms&bbox={bbox}", "template": "/api/map/features.geojson", "family": "map API"},
        {"name": "permits search", "method": "GET", "path": f"/api/permits/search?bbox={bbox}", "template": "/api/permits/search", "family": "api"},
        {"name": "reliefs dem status", "method": "GET", "path": "/api/reliefs/dem/status", "template": "/api/reliefs/dem/status", "family": "relief/terrain"},
        {"name": "reliefs terrain coverage", "method": "GET", "path": "/api/reliefs/terrain/coverage", "template": "/api/reliefs/terrain/coverage", "family": "relief/terrain"},
        {"name": "reliefs terrain jobs", "method": "GET", "path": "/api/reliefs/terrain/jobs/status", "template": "/api/reliefs/terrain/jobs/status", "family": "relief/terrain"},
        {"name": "reliefs terrain sources", "method": "GET", "path": "/api/reliefs/terrain/sources", "template": "/api/reliefs/terrain/sources", "family": "relief/terrain"},
        {"name": "graph index", "method": "GET", "path": "/data/graph-index.json", "template": "/data/graph-index.json", "family": "static data"},
    ]


def cleanup_report_exports(report_ids: list[str]) -> list[str]:
    removed = []
    for report_id in report_ids:
        for suffix in (".html", ".json", ".csv"):
            path = REPORTS_DIR / f"{report_id}{suffix}"
            if path.exists():
                path.unlink()
                removed.append(str(path))
    return removed


def measure_report_generate(client: TestClient, spec: dict[str, Any], samples: int) -> tuple[dict[str, Any], list[str]]:
    durations = []
    statuses = []
    lengths = []
    headers = {}
    first_body = b""
    report_ids = []
    kwargs = spec.get("kwargs") or {}
    for i in range(samples):
        duration, response = timed(lambda: client.post(spec["path"], **kwargs))
        durations.append(duration)
        statuses.append(response.status_code)
        lengths.append(len(response.content))
        if i == 0:
            first_body = response.content
            headers = {
                key: response.headers[key]
                for key in ("cache-control", "content-encoding", "content-length", "content-type", "etag")
                if key in response.headers
            }
        if response.status_code == 200:
            report_id = response.json().get("report_id")
            if report_id:
                report_ids.append(report_id)
    result = {
        "name": spec["name"],
        "method": spec["method"],
        "path": spec["path"],
        "template": spec["template"],
        "family": spec.get("family"),
        "samples": samples,
        "status_codes": sorted(set(statuses)),
        "body_bytes_min": min(lengths),
        "body_bytes_max": max(lengths),
        "p50_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "min_ms": round(min(durations), 3),
        "max_ms": round(max(durations), 3),
        "body_sha256": hashlib.sha256(first_body).hexdigest(),
        "headers": headers,
    }
    try:
        result["json_shape"] = compact_shape(json.loads(first_body))
    except Exception as exc:
        result["json_shape_error"] = str(exc)
    return result, report_ids


def generate_report_and_download(client: TestClient, samples: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    skipped = []
    notes = []
    spec = {
        "name": "report generate",
        "method": "POST",
        "path": "/api/reports/entity/GM/generate",
        "template": "/api/reports/{object_type}/{object_id}/generate",
        "family": "reports",
        "kwargs": {"json": {"sections": ["overview", "evidence"], "report_type": "performance_probe"}},
    }
    result, report_ids = measure_report_generate(client, spec, samples)
    measurements = [result]
    try:
        report_id = report_ids[0]
        download_spec = {
            "name": "report download html",
            "method": "GET",
            "path": f"/api/reports/{report_id}/download?format=html",
            "template": "/api/reports/{report_id}/download",
            "family": "reports",
        }
        download = measure(client, download_spec, samples)
        measurements.append(download)
    except (IndexError, KeyError) as exc:
        skipped.append({"template": "/api/reports/{report_id}/download", "reason": str(exc)})
    finally:
        removed_paths = cleanup_report_exports(report_ids)
        if removed_paths:
            notes.append({"operation": "report cleanup", "removed_paths": removed_paths})
    return measurements, notes + skipped


def measure_sandboxed_mutations(client: TestClient, ids: dict[str, str], samples: int) -> list[dict[str, Any]]:
    asset = ids["asset_id"]
    entity = ids["entity_id"]
    override_ids: list[str] = []
    measurements = [
        measure_dynamic(
            client,
            {
                "name": "valuation assumptions write",
                "method": "POST",
                "path": f"/api/assets/{asset}/valuation-assumptions",
                "template": "/api/assets/{asset_id}/valuation-assumptions",
                "family": "assets/due diligence",
            },
            samples,
            lambda i: (
                f"/api/assets/{asset}/valuation-assumptions",
                {"json": {"case": "performance_probe", "assumptions": {"revenue": 1000 + i, "cost": 500 + i}}},
            ),
        ),
        measure_dynamic(
            client,
            {
                "name": "location override write",
                "method": "POST",
                "path": "/api/location/override",
                "template": "/api/location/override",
                "family": "api",
            },
            samples,
            lambda i: (
                "/api/location/override",
                {"json": {"id": f"performance-probe-location-{i}", "lat": 40.0 + i / 1000, "lng": -73.0}},
            ),
        ),
        measure_dynamic(
            client,
            {
                "name": "watchlist toggle",
                "method": "POST",
                "path": "/api/watchlist/toggle",
                "template": "/api/watchlist/toggle",
                "family": "api",
            },
            samples,
            lambda i: ("/api/watchlist/toggle", {"json": {"entity_id": entity}}),
        ),
    ]

    create_spec = {
        "name": "user override create",
        "method": "POST",
        "path": "/api/overrides",
        "template": "/api/overrides",
        "family": "evidence/overrides",
    }

    def create_override(i: int) -> tuple[str, dict[str, Any]]:
        return (
            "/api/overrides",
            {
                "json": {
                    "object_type": "asset",
                    "object_id": asset,
                    "field_name": f"performance_probe_{i}",
                    "old_value": "old",
                    "new_value": f"new-{i}",
                    "user_note": "performance probe temporary override",
                }
            },
        )

    created = []
    durations = []
    statuses = []
    lengths = []
    headers = {}
    first_body = b""
    for i in range(samples):
        path, kwargs = create_override(i)
        duration, response = timed(lambda: client.post(path, headers={"accept-encoding": "gzip"}, **kwargs))
        durations.append(duration)
        statuses.append(response.status_code)
        lengths.append(len(response.content))
        if i == 0:
            first_body = response.content
            headers = {
                key: response.headers[key]
                for key in ("cache-control", "content-encoding", "content-length", "content-type", "etag")
                if key in response.headers
            }
        if response.status_code == 200:
            override_id = response.json().get("override", {}).get("id")
            if override_id:
                override_ids.append(override_id)
                created.append(override_id)
    create_out = {
        "name": create_spec["name"],
        "method": create_spec["method"],
        "path": create_spec["path"],
        "template": create_spec["template"],
        "family": create_spec["family"],
        "samples": samples,
        "status_codes": sorted(set(statuses)),
        "body_bytes_min": min(lengths),
        "body_bytes_max": max(lengths),
        "p50_ms": round(statistics.median(durations), 3),
        "p95_ms": round(percentile(durations, 0.95), 3),
        "min_ms": round(min(durations), 3),
        "max_ms": round(max(durations), 3),
        "body_sha256": hashlib.sha256(first_body).hexdigest(),
        "headers": headers,
        "created_override_count": len(created),
    }
    measurements.append(create_out)
    if override_ids:
        measurements.append(
            measure_dynamic(
                client,
                {
                    "name": "user override delete",
                    "method": "DELETE",
                    "path": "/api/overrides/{override_id}",
                    "template": "/api/overrides/{override_id}",
                    "family": "evidence/overrides",
                },
                len(override_ids),
                lambda i: (f"/api/overrides/{override_ids[i]}", {}),
            )
        )
    return measurements


def measure_sandboxed_dem_tilejson(client: TestClient, samples: int) -> dict[str, Any]:
    with temporary_dem_tilejson_paths():
        return measure(
            client,
            {
                "name": "reliefs dem tilejson temporary fixture",
                "method": "GET",
                "path": "/api/reliefs/dem/tilejson",
                "template": "/api/reliefs/dem/tilejson",
                "family": "relief/terrain",
                "fixture": "temporary tilejson path redirection",
            },
            samples,
        )


def main() -> int:
    import argparse
    import map_api

    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()

    client = TestClient(map_api.app)
    ids = representative_ids()
    measurements = [measure(client, spec, args.samples) for spec in probe_specs(ids)]
    report_measurements, report_notes = generate_report_and_download(client, args.samples)
    measurements.extend(report_measurements)
    with temporary_persistent_json_paths(map_api):
        measurements.extend(measure_sandboxed_mutations(client, ids, args.samples))
    measurements.append(measure_sandboxed_dem_tilejson(client, args.samples))
    skipped = []
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "python": platform.python_version(),
        "samples_per_route": args.samples,
        "representative_ids": ids,
        "measurements": measurements,
        "notes": report_notes,
        "sandboxed_fixtures": [
            {
                "method": "GET",
                "template": "/api/reliefs/dem/tilejson",
                "reason": "temporary tilejson path redirection; real local DEM tilejson artifact remains ungenerated",
            },
            {
                "templates": [
                    "/api/assets/{asset_id}/valuation-assumptions",
                    "/api/location/override",
                    "/api/watchlist/toggle",
                    "/api/overrides",
                    "/api/overrides/{override_id}",
                ],
                "reason": "temporary JSON path redirection for file-backed mutation routes",
            },
        ],
        "skipped": skipped,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / "17-route-family-performance-probes.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote route-family performance probes to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
