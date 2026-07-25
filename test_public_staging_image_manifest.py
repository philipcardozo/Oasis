"""Public-staging image manifest regressions."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from scripts.public_staging_image_manifest import build_payload, evaluate


DIGEST = "sha256:" + "a" * 64


def test_image_manifest_passes_for_digest_pinned_tested_image():
    payload = build_payload(_args(image=f"ghcr.io/example/oasis@{DIGEST}", digest=DIGEST))

    assert payload["verdict"] == "pass"
    assert payload["failures"] == []


def test_image_manifest_rejects_mutable_or_mismatched_image():
    payload = build_payload(_args(image="ghcr.io/example/oasis:latest", digest=DIGEST))

    failures = evaluate(payload)

    assert "image is not pinned by digest" in failures
    assert "image uses mutable latest tag" in failures
    assert "image digest does not match digest field" in failures


def test_image_manifest_rejects_failed_ci_checks():
    payload = build_payload(_args(image=f"ghcr.io/example/oasis@{DIGEST}", digest=DIGEST, python_tests="fail"))

    assert "python_tests check is not passing/present" in evaluate(payload)


def test_image_manifest_cli_writes_pass_artifact(tmp_path):
    output = tmp_path / "01-image-manifest.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/public_staging_image_manifest.py",
            "--commit=abcdef123456",
            f"--image=ghcr.io/example/oasis@{DIGEST}",
            f"--digest={DIGEST}",
            f"--output={output}",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["verdict"] == "pass"


def _args(**overrides):
    values = {
        "commit": "abcdef123456",
        "branch": "phase1.75/public-staging",
        "image": f"ghcr.io/example/oasis@{DIGEST}",
        "digest": DIGEST,
        "built_at": "2026-07-25T00:00:00Z",
        "architecture": "linux/amd64",
        "registry": "ghcr.io",
        "tag": ["staging-abcdef123456"],
        "migration_check": "pass",
        "python_tests": "pass",
        "playwright_tests": "pass",
        "image_scan": "pass",
        "sbom": "present",
        "provenance": "present",
        "workflow": "Deploy",
        "run_id": "123",
        "run_attempt": "1",
    }
    values.update(overrides)
    return argparse.Namespace(**values)
