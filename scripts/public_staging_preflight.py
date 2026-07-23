#!/usr/bin/env python3
"""Public staging DNS/TLS/security preflight.

This script intentionally avoids application mutations. It can run outside the
private-beta boundary for DNS/TLS checks, or inside it by passing service-token
headers via environment variables:

    python3 scripts/public_staging_preflight.py \
      --base-url=https://staging.example.com \
      --header CF-Access-Client-Id=OASIS_CF_ACCESS_CLIENT_ID \
      --header CF-Access-Client-Secret=OASIS_CF_ACCESS_CLIENT_SECRET
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802 - urllib API
        return None


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def env_headers(items: list[str]) -> tuple[dict[str, str], list[str]]:
    headers: dict[str, str] = {}
    names: list[str] = []
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--header must be Name=ENV_VAR, got {item!r}")
        name, env_name = item.split("=", 1)
        value = os.environ.get(env_name)
        if not value:
            raise SystemExit(f"missing environment variable for header {name}: {env_name}")
        headers[name] = value
        names.append(name)
    return headers, names


def dns_lookup(hostname: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        return {"ok": False, "error": str(exc)}
    addresses = sorted({info[4][0] for info in infos})
    return {
        "ok": bool(addresses),
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "addresses": addresses,
    }


def tls_probe(hostname: str, port: int) -> dict[str, Any]:
    context = ssl.create_default_context()
    started = time.perf_counter()
    try:
        with socket.create_connection((hostname, port), timeout=15) as raw:
            with context.wrap_socket(raw, server_hostname=hostname) as sock:
                cert = sock.getpeercert()
                issuer = dict(x[0] for x in cert.get("issuer", ()))
                subject = dict(x[0] for x in cert.get("subject", ()))
                sans = [v for k, v in cert.get("subjectAltName", ()) if k == "DNS"]
                return {
                    "ok": True,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "tls_version": sock.version(),
                    "cipher": sock.cipher()[0] if sock.cipher() else None,
                    "issuer_common_name": issuer.get("commonName"),
                    "subject_common_name": subject.get("commonName"),
                    "not_before": cert.get("notBefore"),
                    "not_after": cert.get("notAfter"),
                    "subject_alt_names": sans,
                }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def http_probe(url: str, headers: dict[str, str], *, follow_redirects: bool = True) -> dict[str, Any]:
    opener = build_opener() if follow_redirects else build_opener(NoRedirect)
    req = Request(url, headers={"User-Agent": "oasis-public-staging-preflight", **headers})
    started = time.perf_counter()
    try:
        with opener.open(req, timeout=30) as response:
            body = response.read(256 * 1024)
            return response_payload(url, response.status, response.headers, body, started)
    except HTTPError as exc:
        body = exc.read(64 * 1024)
        return response_payload(url, exc.code, exc.headers, body, started)
    except URLError as exc:
        return {"url": safe_url(url), "ok": False, "error": str(exc.reason)}


def response_payload(url: str, status: int, headers, body: bytes, started: float) -> dict[str, Any]:
    selected = {
        key.lower(): headers.get(key)
        for key in (
            "Cache-Control",
            "Content-Encoding",
            "Content-Length",
            "Content-Security-Policy",
            "Content-Type",
            "ETag",
            "Location",
            "Permissions-Policy",
            "Referrer-Policy",
            "Set-Cookie",
            "Strict-Transport-Security",
            "Vary",
            "X-Content-Type-Options",
            "X-Request-ID",
        )
        if headers.get(key) is not None
    }
    if "set-cookie" in selected:
        selected["set-cookie"] = cookie_flags(selected["set-cookie"])
    payload = {
        "url": safe_url(url),
        "ok": 200 <= status < 400,
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "body_sample_bytes": len(body),
        "headers": selected,
    }
    content_type = selected.get("content-type", "")
    if len(body) <= 8192 and ("json" in content_type or urlparse(url).path in {"/version", "/healthz", "/readyz"}):
        payload["body_text"] = body.decode("utf-8", errors="replace")
    return payload


def safe_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="<redacted>" if parsed.query else "").geturl()


def cookie_flags(value: str) -> str:
    lowered = value.lower()
    flags = []
    for flag in ("httponly", "secure", "samesite=lax", "samesite=strict", "samesite=none"):
        if flag in lowered:
            flags.append(flag)
    return "; ".join(flags) if flags else "<cookie-present-without-recorded-value>"


def validate(payload: dict[str, Any], *, expect_commit: str, allow_hsts_subdomains: bool) -> list[str]:
    failures: list[str] = []
    if not payload["dns"].get("ok"):
        failures.append("DNS lookup failed")
    if payload["url"]["scheme"] != "https":
        failures.append("base URL must use https")
    if not payload["tls"].get("ok"):
        failures.append("TLS probe failed")
    redirect = payload.get("http_to_https_redirect", {})
    if redirect and redirect.get("status") not in {301, 302, 307, 308}:
        failures.append("HTTP endpoint did not redirect to HTTPS")
    for path, result in payload["endpoints"].items():
        if path in {"/healthz", "/version", "/index.html"} and not result.get("ok"):
            failures.append(f"{path} did not return a successful response")
    headers = payload["endpoints"].get("/index.html", {}).get("headers", {})
    required = {
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin",
        "content-security-policy": "default-src 'self'",
    }
    for key, expected in required.items():
        value = headers.get(key, "")
        if expected not in value:
            failures.append(f"/index.html missing expected {key}: {expected}")
    hsts = headers.get("strict-transport-security", "")
    if "max-age=" not in hsts:
        failures.append("/index.html missing HSTS max-age")
    if not allow_hsts_subdomains and "includesubdomains" in hsts.lower():
        failures.append("HSTS includeSubDomains is not allowed for this staging gate")
    if not allow_hsts_subdomains and "preload" in hsts.lower():
        failures.append("HSTS preload is not allowed for this staging gate")
    version = payload["endpoints"].get("/version", {})
    if expect_commit and expect_commit not in version.get("body_text", ""):
        failures.append("/version does not include the expected deployed commit")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("STAGING_URL", ""))
    parser.add_argument("--output", default=str(EVIDENCE / "00-public-staging-preflight.json"))
    parser.add_argument("--header", action="append", default=[], help="send Name=ENV_VAR without writing values to evidence")
    parser.add_argument("--expect-commit", default="")
    parser.add_argument("--allow-hsts-subdomains", action="store_true")
    args = parser.parse_args()

    if not args.base_url:
        raise SystemExit("provide --base-url or STAGING_URL")
    base_url = args.base_url.rstrip("/")
    parsed = urlparse(base_url)
    if not parsed.hostname:
        raise SystemExit(f"invalid base URL: {base_url!r}")
    headers, header_names = env_headers(args.header)

    endpoints: dict[str, Any] = {}
    for path in ("/index.html", "/healthz", "/readyz", "/version"):
        result = http_probe(urljoin(base_url + "/", path.lstrip("/")), headers)
        if path == "/version":
            try:
                text = json.loads(result.get("body_text", ""))
            except Exception:
                text = None
            if text:
                result["body_json"] = text
        endpoints[path] = result

    http_redirect = None
    if parsed.scheme == "https":
        http_url = parsed._replace(scheme="http").geturl()
        http_redirect = http_probe(urljoin(http_url.rstrip("/") + "/", "healthz"), {}, follow_redirects=False)

    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "base_url": safe_url(base_url),
        "url": {"scheme": parsed.scheme, "hostname": parsed.hostname, "port": parsed.port or (443 if parsed.scheme == "https" else 80)},
        "auth_header_names_sent": header_names,
        "dns": dns_lookup(parsed.hostname),
        "tls": tls_probe(parsed.hostname, parsed.port or 443) if parsed.scheme == "https" else {"ok": False, "error": "base URL is not HTTPS"},
        "http_to_https_redirect": http_redirect,
        "endpoints": endpoints,
    }
    failures = validate(payload, expect_commit=args.expect_commit, allow_hsts_subdomains=args.allow_hsts_subdomains)
    payload["failures"] = failures
    payload["verdict"] = "pass" if not failures else "investigate"

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging preflight to {output}")
    print(json.dumps({"verdict": payload["verdict"], "failures": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
