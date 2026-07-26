#!/usr/bin/env python3
"""Build public-staging licensing-gate evidence.

The public beta gate can pass with licensing uncertainty only when the affected
provider is disabled. This report records current primary-source review metadata
and checks that unresolved providers stayed off in staging evidence.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"

REQUIRED_PROVIDERS = {
    "esri_world_imagery": {
        "name": "Esri World Imagery",
        "category": "satellite imagery",
        "must_be_disabled": True,
        "flag": "OASIS_FEATURE_SATELLITE",
        "official_hosts": {"esri.com", "arcgis.com"},
    },
    "carto_tiles": {
        "name": "CARTO styles and tiles",
        "category": "map styles and tiles",
        "must_be_disabled": False,
        "flag": "",
        "official_hosts": {"carto.com"},
    },
    "yahoo_finance_yfinance": {
        "name": "Yahoo Finance and yfinance",
        "category": "market data",
        "must_be_disabled": True,
        "flag": "OASIS_FEATURE_PRICES",
        "official_hosts": {"yahoo.com", "github.com"},
    },
    "company_logos": {
        "name": "Company logos",
        "category": "logo assets",
        "must_be_disabled": True,
        "flag": "OASIS_FEATURE_LOGOS",
        "official_hosts": {"clearbit.com", "brandfetch.com", "simpleicons.org"},
    },
    "news_sources": {
        "name": "News sources",
        "category": "news snippets",
        "must_be_disabled": False,
        "flag": "",
        "official_hosts": {"google.com", "news.google.com", "policies.google.com"},
    },
    "political_trading_feeds": {
        "name": "Political-trading feeds",
        "category": "political trades",
        "must_be_disabled": True,
        "flag": "",
        "official_hosts": {"quiverquant.com"},
    },
    "property_parcel_data": {
        "name": "Property and parcel data",
        "category": "property and parcel data",
        "must_be_disabled": True,
        "flag": "",
        "official_hosts": set(),
    },
    "other_commercial_datasets": {
        "name": "Other commercial datasets",
        "category": "other commercial datasets",
        "must_be_disabled": True,
        "flag": "",
        "official_hosts": set(),
    },
}

REQUIRED_REVIEW_FIELDS = {
    "current_official_source_url",
    "reviewed_at",
    "commercial_use_permission",
    "caching_rules",
    "redistribution_rules",
    "attribution_required",
    "offline_use",
    "account_or_api_key_required",
    "replacement_provider",
    "enabled_in_public_staging",
    "status",
}

ALLOWED_STATUS = {"approved", "disabled", "not_selected", "investigate"}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def display_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() and path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    return value


def parse_review_date(value: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(str(value))
        except Exception:
            return None


def source_host_ok(provider_key: str, url: str) -> bool:
    if not url:
        return False
    if url in {"not-selected", "not-applicable"}:
        return provider_key in {"property_parcel_data", "other_commercial_datasets"}
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    allowed = REQUIRED_PROVIDERS[provider_key]["official_hosts"]
    if not allowed:
        return True
    host = parsed.hostname.lower()
    return any(host == item or host.endswith("." + item) for item in allowed)


def truthy(value: Any) -> bool:
    return value is True or str(value).lower() in {"true", "yes", "pass", "approved"}


def flag_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    flags = data.get("feature_flags") or {}
    expected = {
        "OASIS_FEATURE_SATELLITE": False,
        "OASIS_FEATURE_PRICES": False,
        "OASIS_FEATURE_LOGOS": False,
    }
    rows = []
    for key, expected_value in expected.items():
        rows.append({
            "key": key,
            "label": f"{key} is disabled in public staging",
            "value": flags.get(key) is expected_value,
            "observed": flags.get(key),
        })
    return rows


def browser_map_rows(browser_map: dict[str, Any] | None) -> list[dict[str, Any]]:
    provider = (browser_map or {}).get("map_provider") or {}
    check_values = {item.get("key"): item.get("value") for item in provider.get("rows") or []}
    return [
        {
            "key": "browser_map_summary_pass",
            "label": "browser/map summary verdict is pass",
            "value": (browser_map or {}).get("browser", {}).get("verdict") == "pass" and provider.get("verdict") == "pass",
        },
        {
            "key": "disabled_providers_unused",
            "label": "disabled providers remained unused in public browser capture",
            "value": check_values.get("disabled_providers_unused") is True,
        },
        {
            "key": "no_provider_credentials",
            "label": "provider credentials did not reach the browser",
            "value": check_values.get("no_provider_credentials") is True,
        },
        {
            "key": "no_unpkg",
            "label": "browser capture did not request unpkg.com",
            "value": check_values.get("no_unpkg") is True,
        },
        {
            "key": "approved_hosts_only",
            "label": "observed map hosts are approved",
            "value": set(provider.get("observed_external_hosts") or []) <= set(provider.get("approved_hosts") or []),
        },
    ]


def provider_row(key: str, item: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    missing = sorted(REQUIRED_REVIEW_FIELDS - set(item))
    for field in missing:
        failures.append(f"{key} missing review field: {field}")

    reviewed = parse_review_date(item.get("reviewed_at"))
    if reviewed is None:
        failures.append(f"{key} reviewed_at is invalid")
    else:
        age_days = (datetime.now(timezone.utc).date() - reviewed).days
        if age_days < 0:
            failures.append(f"{key} reviewed_at is in the future")
        if age_days > 45:
            failures.append(f"{key} official terms review is older than 45 days")

    source_url = str(item.get("current_official_source_url") or "")
    if not source_host_ok(key, source_url):
        failures.append(f"{key} current official source URL is not an allowed official source")

    status = str(item.get("status") or "")
    if status not in ALLOWED_STATUS:
        failures.append(f"{key} status is not recognized")

    enabled = item.get("enabled_in_public_staging")
    must_disable = REQUIRED_PROVIDERS[key]["must_be_disabled"]
    if must_disable and enabled is not False:
        failures.append(f"{key} must remain disabled in public staging")
    if status in {"disabled", "not_selected", "investigate"} and enabled is not False:
        failures.append(f"{key} unresolved/nonselected provider is enabled")

    if enabled is True:
        if item.get("commercial_use_permission") is not True:
            failures.append(f"{key} enabled provider lacks commercial-use permission")
        for field in ("caching_rules", "redistribution_rules", "offline_use"):
            if str(item.get(field) or "").lower() in {"", "unknown", "not reviewed"}:
                failures.append(f"{key} enabled provider has unresolved {field}")

    if not str(item.get("replacement_provider") or ""):
        failures.append(f"{key} replacement provider is missing")

    row = {
        "key": key,
        "name": REQUIRED_PROVIDERS[key]["name"],
        "category": REQUIRED_PROVIDERS[key]["category"],
        "status": status,
        "enabled_in_public_staging": enabled,
        "current_official_source_url": source_url,
        "reviewed_at": item.get("reviewed_at"),
        "commercial_use_permission": item.get("commercial_use_permission"),
        "caching_rules": item.get("caching_rules"),
        "redistribution_rules": item.get("redistribution_rules"),
        "attribution_required": item.get("attribution_required"),
        "offline_use": item.get("offline_use"),
        "account_or_api_key_required": item.get("account_or_api_key_required"),
        "replacement_provider": item.get("replacement_provider"),
        "failures": failures,
    }
    return row, failures


def build_payload(data: dict[str, Any], browser_map: dict[str, Any] | None, *, input_path: str, browser_map_path: str) -> dict[str, Any]:
    providers = data.get("providers") or {}
    provider_rows = []
    failures: list[str] = []
    for key in sorted(REQUIRED_PROVIDERS):
        item = providers.get(key)
        if not isinstance(item, dict):
            failures.append(f"{key} provider review is missing")
            provider_rows.append({
                "key": key,
                "name": REQUIRED_PROVIDERS[key]["name"],
                "category": REQUIRED_PROVIDERS[key]["category"],
                "status": "missing",
                "enabled_in_public_staging": None,
                "failures": [f"{key} provider review is missing"],
            })
            continue
        row, row_failures = provider_row(key, item)
        provider_rows.append(row)
        failures.extend(row_failures)

    flags = flag_rows(data)
    browser_rows = browser_map_rows(browser_map)
    for row in flags:
        if row["value"] is not True:
            failures.append(f"feature flag check is not true: {row['key']}")
    for row in browser_rows:
        if row["value"] is not True:
            failures.append(f"browser/map licensing check is not true: {row['key']}")

    if not data.get("input_captured_at"):
        failures.append("licensing evidence input captured timestamp is missing")
    if data.get("secure_mode") != "staging":
        failures.append("licensing evidence secure_mode is not staging")

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "input_captured_at": data.get("input_captured_at"),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "verdict": "pass" if not failures else "investigate",
        "failures": failures,
        "inputs": {
            "licensing_evidence": display_path(input_path),
            "browser_map_summary": display_path(browser_map_path),
        },
        "secure_mode": data.get("secure_mode"),
        "providers": {"rows": provider_rows},
        "feature_flags": {"rows": flags},
        "browser_map": {"rows": browser_rows},
    }
    return payload


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Public Staging Licensing Gate Evidence",
        "",
        f"Captured: {payload['captured_at']}",
        f"Commit: `{payload['commit']}`",
        f"Branch: `{payload['branch']}`",
        f"Secure mode: `{payload.get('secure_mode')}`",
        f"Verdict: **{payload['verdict']}**",
        "",
        "## Provider Reviews",
        "",
        "| Provider | Status | Enabled | Reviewed | Commercial use | Source | Replacement | Failures |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in payload["providers"]["rows"]:
        failures = "; ".join(row.get("failures") or []) or "-"
        lines.append(
            f"| {row['name']} | `{row.get('status')}` | `{row.get('enabled_in_public_staging')}` | "
            f"`{row.get('reviewed_at')}` | `{row.get('commercial_use_permission')}` | "
            f"`{row.get('current_official_source_url') or '-'}` | `{row.get('replacement_provider') or '-'}` | {failures} |"
        )

    lines.extend(["", "## Feature Flags", "", "| Flag | Result | Observed |", "|---|---|---|"])
    for row in payload["feature_flags"]["rows"]:
        lines.append(f"| {row['key']} | `{row['value']}` | `{row.get('observed')}` |")

    lines.extend(["", "## Browser Map Licensing Checks", "", "| Check | Result |", "|---|---|"])
    for row in payload["browser_map"]["rows"]:
        lines.append(f"| {row['label']} | `{row['value']}` |")

    if payload["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in payload["failures"])

    lines.append("")
    lines.append("This generated report contains current-source licensing review metadata only.")
    return "\n".join(lines) + "\n"


def template() -> dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    source_examples = {
        "esri_world_imagery": "https://www.esri.com/en-us/legal/terms/full-master-agreement",
        "carto_tiles": "https://carto.com/legal/",
        "yahoo_finance_yfinance": "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
        "company_logos": "https://clearbit.com/logo",
        "news_sources": "https://policies.google.com/terms",
        "political_trading_feeds": "https://www.quiverquant.com/terms/",
        "property_parcel_data": "not-selected",
        "other_commercial_datasets": "not-selected",
    }
    provider_template = {}
    for key, meta in REQUIRED_PROVIDERS.items():
        disabled = bool(meta["must_be_disabled"])
        provider_template[key] = {
            "status": "disabled" if disabled else "approved",
            "current_official_source_url": source_examples[key],
            "reviewed_at": today,
            "commercial_use_permission": False if disabled else True,
            "caching_rules": "no caching unless terms explicitly allow it" if disabled else "reviewed and allowed for this use",
            "redistribution_rules": "no redistribution unless terms explicitly allow it" if disabled else "reviewed and allowed for this use",
            "attribution_required": True,
            "offline_use": "disabled" if disabled else "reviewed and allowed for this use",
            "account_or_api_key_required": True,
            "replacement_provider": "disabled for private beta" if disabled else "current approved provider",
            "enabled_in_public_staging": False if disabled else True,
        }
    return {
        "input_captured_at": datetime.now(timezone.utc).isoformat(),
        "secure_mode": "staging",
        "feature_flags": {
            "OASIS_FEATURE_SATELLITE": False,
            "OASIS_FEATURE_PRICES": False,
            "OASIS_FEATURE_LOGOS": False,
        },
        "providers": provider_template,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-template", action="store_true", help="print a non-secret licensing evidence template and exit")
    parser.add_argument("--input", default=str(PUBLIC_EVIDENCE / "licensing-evidence.json"))
    parser.add_argument("--browser-map-summary", default=str(PUBLIC_EVIDENCE / "browser-map-summary.json"))
    parser.add_argument("--output", default=str(PUBLIC_EVIDENCE / "17-licensing-gates.md"))
    parser.add_argument("--summary-output", default=str(PUBLIC_EVIDENCE / "licensing-summary.json"))
    args = parser.parse_args()

    if args.print_template:
        print(json.dumps(template(), indent=2, sort_keys=True))
        return 0

    data = load_json(Path(args.input))
    if data is None:
        raise SystemExit(f"missing input: {args.input}")
    payload = build_payload(
        data,
        load_json(Path(args.browser_map_summary)),
        input_path=args.input,
        browser_map_path=args.browser_map_summary,
    )
    output = Path(args.output)
    summary = Path(args.summary_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown(payload))
    summary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(f"Wrote public staging licensing report to {output}")
    print(f"Wrote public staging licensing summary to {summary}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
