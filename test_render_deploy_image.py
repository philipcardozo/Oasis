"""Render deploy evidence validation regressions."""
from __future__ import annotations

from scripts.render_deploy_image import evaluate_deploy_payload, validate_image_input


DIGEST = "sha256:" + "b" * 64
IMAGE = f"ghcr.io/example/oasis@{DIGEST}"


def test_render_deploy_evidence_passes_for_manifest_matched_api_and_worker():
    payload = {
        "image_url": IMAGE,
        "deployments": [
            _deployment("api"),
            _deployment("worker"),
        ],
    }

    assert evaluate_deploy_payload(payload, _manifest()) == []


def test_render_deploy_evidence_rejects_mutable_image():
    failures = validate_image_input("ghcr.io/example/oasis:latest", _manifest())

    assert "image_url is not pinned by digest" in failures
    assert "image_url uses mutable latest tag" in failures
    assert "image_url digest is missing or not sha256" in failures


def test_render_deploy_evidence_rejects_manifest_mismatch():
    failures = validate_image_input(IMAGE, {"verdict": "pass", "image": f"ghcr.io/example/oasis@sha256:{'c' * 64}", "digest": DIGEST})

    assert "image_url does not match image manifest" in failures


def test_render_deploy_evidence_requires_api_and_worker_success():
    payload = {
        "image_url": IMAGE,
        "deployments": [
            _deployment("api"),
        ],
    }

    failures = evaluate_deploy_payload(payload, _manifest())

    assert "deployments must include exactly api and worker roles, got ['api']" in failures


def test_render_deploy_evidence_rejects_non_terminal_worker():
    payload = {
        "image_url": IMAGE,
        "deployments": [
            _deployment("api"),
            {**_deployment("worker"), "terminal": False, "ok": False, "timed_out": True},
        ],
    }

    failures = evaluate_deploy_payload(payload, _manifest())

    assert "worker deploy did not succeed" in failures
    assert "worker deploy did not reach terminal status" in failures
    assert "worker deploy timed out" in failures


def _manifest() -> dict:
    return {
        "verdict": "pass",
        "image": IMAGE,
        "digest": DIGEST,
    }


def _deployment(role: str) -> dict:
    return {
        "role": role,
        "service_id_sha256_16": "0123456789abcdef",
        "deploy_id": f"dep-{role}",
        "status": "live",
        "terminal": True,
        "ok": True,
        "timed_out": False,
    }
