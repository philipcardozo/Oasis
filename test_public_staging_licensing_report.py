"""Public-staging licensing report regressions."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

from scripts.public_staging_licensing_report import build_payload, template


def test_licensing_report_passes_when_unresolved_providers_are_disabled():
    payload = build_payload(_evidence(), _browser_map_summary(), input_path="licensing.json", browser_map_path="browser.json")

    assert payload["verdict"] == "pass"
    assert payload["failures"] == []


def test_licensing_report_rejects_enabled_unresolved_provider():
    evidence = _evidence()
    evidence["providers"]["esri_world_imagery"]["enabled_in_public_staging"] = True
    evidence["feature_flags"]["OASIS_FEATURE_SATELLITE"] = True

    payload = build_payload(evidence, _browser_map_summary(), input_path="licensing.json", browser_map_path="browser.json")

    assert payload["verdict"] == "investigate"
    assert "esri_world_imagery must remain disabled in public staging" in payload["failures"]
    assert "feature flag check is not true: OASIS_FEATURE_SATELLITE" in payload["failures"]


def test_licensing_report_rejects_stale_or_unofficial_terms():
    evidence = _evidence()
    evidence["providers"]["yahoo_finance_yfinance"]["reviewed_at"] = "2024-01-01"
    evidence["providers"]["yahoo_finance_yfinance"]["current_official_source_url"] = "https://example.com/yahoo"

    payload = build_payload(evidence, _browser_map_summary(), input_path="licensing.json", browser_map_path="browser.json")

    assert any("official terms review is older than 45 days" in item for item in payload["failures"])
    assert "yahoo_finance_yfinance current official source URL is not an allowed official source" in payload["failures"]


def test_licensing_report_rejects_restricted_provider_use_in_browser_capture():
    browser = _browser_map_summary()
    for row in browser["map_provider"]["rows"]:
        if row["key"] == "disabled_providers_unused":
            row["value"] = False
    browser["map_provider"]["observed_external_hosts"].append("server.arcgisonline.com")

    payload = build_payload(_evidence(), browser, input_path="licensing.json", browser_map_path="browser.json")

    assert "browser/map licensing check is not true: disabled_providers_unused" in payload["failures"]
    assert "browser/map licensing check is not true: approved_hosts_only" in payload["failures"]


def test_licensing_report_cli_writes_pass_artifacts(tmp_path):
    evidence = tmp_path / "licensing-evidence.json"
    browser = tmp_path / "browser-map-summary.json"
    report = tmp_path / "17-licensing-gates.md"
    summary = tmp_path / "licensing-summary.json"
    evidence.write_text(json.dumps(_evidence()))
    browser.write_text(json.dumps(_browser_map_summary()))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_licensing_report.py",
            f"--input={evidence}",
            f"--browser-map-summary={browser}",
            f"--output={report}",
            f"--summary-output={summary}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Verdict: **pass**" in report.read_text()
    assert json.loads(summary.read_text())["verdict"] == "pass"


def test_licensing_template_is_non_secret_shape():
    data = template()

    assert data["secure_mode"] == "staging"
    assert data["feature_flags"]["OASIS_FEATURE_SATELLITE"] is False
    assert set(data["providers"])


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _review(
    *,
    url: str,
    status: str,
    enabled: bool,
    commercial: bool,
    replacement: str,
) -> dict:
    return {
        "status": status,
        "current_official_source_url": url,
        "reviewed_at": _today(),
        "commercial_use_permission": commercial,
        "caching_rules": "reviewed for this public staging use" if enabled else "disabled; no caching",
        "redistribution_rules": "reviewed for this public staging use" if enabled else "disabled; no redistribution",
        "attribution_required": True,
        "offline_use": "reviewed for this public staging use" if enabled else "disabled",
        "account_or_api_key_required": enabled,
        "replacement_provider": replacement,
        "enabled_in_public_staging": enabled,
    }


def _evidence() -> dict:
    return {
        "input_captured_at": datetime.now(timezone.utc).isoformat(),
        "secure_mode": "staging",
        "feature_flags": {
            "OASIS_FEATURE_SATELLITE": False,
            "OASIS_FEATURE_PRICES": False,
            "OASIS_FEATURE_LOGOS": False,
        },
        "providers": {
            "esri_world_imagery": _review(
                url="https://www.esri.com/en-us/legal/terms/full-master-agreement",
                status="disabled",
                enabled=False,
                commercial=False,
                replacement="Sentinel-2 or licensed imagery",
            ),
            "carto_tiles": _review(
                url="https://carto.com/legal/",
                status="approved",
                enabled=True,
                commercial=True,
                replacement="self-hosted dark style if terms change",
            ),
            "yahoo_finance_yfinance": _review(
                url="https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
                status="disabled",
                enabled=False,
                commercial=False,
                replacement="Polygon, Tiingo, or Nasdaq",
            ),
            "company_logos": _review(
                url="https://clearbit.com/logo",
                status="disabled",
                enabled=False,
                commercial=False,
                replacement="local approved logos only",
            ),
            "news_sources": _review(
                url="https://policies.google.com/terms",
                status="approved",
                enabled=True,
                commercial=True,
                replacement="headline and link only; no full-text cache",
            ),
            "political_trading_feeds": _review(
                url="https://www.quiverquant.com/terms/",
                status="disabled",
                enabled=False,
                commercial=False,
                replacement="filing provenance only until paid access",
            ),
            "property_parcel_data": _review(
                url="not-selected",
                status="not_selected",
                enabled=False,
                commercial=False,
                replacement="official county/open-data source after review",
            ),
            "other_commercial_datasets": _review(
                url="not-selected",
                status="not_selected",
                enabled=False,
                commercial=False,
                replacement="disabled until provider-specific review",
            ),
        },
    }


def _browser_map_summary() -> dict:
    return {
        "browser": {"verdict": "pass"},
        "map_provider": {
            "verdict": "pass",
            "approved_hosts": ["tiles.openfreemap.org"],
            "observed_external_hosts": ["tiles.openfreemap.org"],
            "rows": [
                {"key": "disabled_providers_unused", "value": True},
                {"key": "no_provider_credentials", "value": True},
                {"key": "no_unpkg", "value": True},
            ],
        },
    }
