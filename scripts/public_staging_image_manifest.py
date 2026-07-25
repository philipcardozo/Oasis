#!/usr/bin/env python3
"""Write strict public-staging image manifest evidence.

The manifest is intentionally CI-oriented: it should be produced only after
migrations, tests, image build, SBOM/provenance, and vulnerability scan have
succeeded. It records no credentials or registry tokens.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def split_image_digest(image: str) -> tuple[str, str]:
    if "@" not in image:
        return image, ""
    name, digest = image.rsplit("@", 1)
    return name, digest


def status_ok(value: str) -> bool:
    return value.lower() in {"pass", "passed", "ok", "success", "succeeded", "true", "present"}


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    commit = args.commit or os.environ.get("GITHUB_SHA", "") or git_value("rev-parse", "HEAD")
    image = args.image
    image_name, image_digest = split_image_digest(image)
    digest = args.digest or image_digest
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "branch": args.branch or git_value("branch", "--show-current"),
        "image": image,
        "image_name": image_name,
        "digest": digest,
        "built_at": args.built_at or datetime.now(timezone.utc).isoformat(),
        "architecture": args.architecture,
        "registry": args.registry,
        "tags": [tag for tag in args.tag if tag],
        "checks": {
            "migration_validation": args.migration_check,
            "python_tests": args.python_tests,
            "playwright_tests": args.playwright_tests,
            "image_scan": args.image_scan,
            "sbom": args.sbom,
            "provenance": args.provenance,
        },
        "ci": {
            "workflow": args.workflow,
            "run_id": args.run_id,
            "run_attempt": args.run_attempt,
        },
    }
    failures = evaluate(payload)
    payload["failures"] = failures
    payload["verdict"] = "pass" if not failures else "fail"
    return payload


def evaluate(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    image = str(payload.get("image") or "")
    image_name = str(payload.get("image_name") or "")
    digest = str(payload.get("digest") or "")
    registry = str(payload.get("registry") or "")
    architecture = str(payload.get("architecture") or "")
    commit = str(payload.get("commit") or "")

    if not commit or len(commit) < 7:
        failures.append("commit is missing or too short")
    if "@" not in image:
        failures.append("image is not pinned by digest")
    if ":latest" in image or image.endswith(":latest"):
        failures.append("image uses mutable latest tag")
    if not DIGEST_RE.match(digest):
        failures.append("digest is missing or not a sha256 digest")
    if image and digest and not image.endswith(f"@{digest}"):
        failures.append("image digest does not match digest field")
    if registry != "ghcr.io":
        failures.append("registry is not ghcr.io")
    if image_name and not image_name.startswith("ghcr.io/"):
        failures.append("image name is not in GHCR")
    if architecture != "linux/amd64":
        failures.append("architecture is not linux/amd64")

    parsed = urlparse(image)
    if parsed.scheme:
        failures.append("image must be a registry reference, not a URL")

    checks = payload.get("checks") or {}
    for name in ("migration_validation", "python_tests", "playwright_tests", "image_scan", "sbom", "provenance"):
        if not status_ok(str(checks.get(name) or "")):
            failures.append(f"{name} check is not passing/present")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", default="")
    parser.add_argument("--branch", default="")
    parser.add_argument("--image", required=True)
    parser.add_argument("--digest", default="")
    parser.add_argument("--built-at", default="")
    parser.add_argument("--architecture", default="linux/amd64")
    parser.add_argument("--registry", default="ghcr.io")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--migration-check", default="pass")
    parser.add_argument("--python-tests", default="pass")
    parser.add_argument("--playwright-tests", default="pass")
    parser.add_argument("--image-scan", default="pass")
    parser.add_argument("--sbom", default="present")
    parser.add_argument("--provenance", default="present")
    parser.add_argument("--workflow", default=os.environ.get("GITHUB_WORKFLOW", ""))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    parser.add_argument("--output", default=str(EVIDENCE / "01-image-manifest.json"))
    args = parser.parse_args()

    payload = build_payload(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote public staging image manifest to {output}")
    print(json.dumps({"verdict": payload["verdict"], "failures": payload["failures"]}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
