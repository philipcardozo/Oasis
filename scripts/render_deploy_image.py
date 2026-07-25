#!/usr/bin/env python3
"""Deploy a tested image digest to Render API and worker services.

The script uses Render's public API so staging can deploy the exact image that
CI tested, scanned, and recorded. It writes non-secret evidence only: deploy IDs,
statuses, image URL, commit, and hashed service IDs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "public-staging"
API = "https://api.render.com/v1"
IMAGE_MANIFEST = EVIDENCE / "01-image-manifest.json"
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SUCCESS_STATUSES = {"live", "succeeded"}
FAILURE_STATUSES = {
    "build_failed",
    "canceled",
    "cancelled",
    "deactivated",
    "failed",
    "pre_deploy_failed",
    "update_failed",
}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable: {exc}"


def service_hash(service_id: str) -> str:
    return hashlib.sha256(service_id.encode("utf-8")).hexdigest()[:16]


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def split_image_digest(image_url: str) -> tuple[str, str]:
    if "@" not in image_url:
        return image_url, ""
    name, digest = image_url.rsplit("@", 1)
    return name, digest


def validate_image_input(image_url: str, manifest: dict[str, Any] | None) -> list[str]:
    failures: list[str] = []
    _, digest = split_image_digest(image_url)
    if "@" not in image_url:
        failures.append("image_url is not pinned by digest")
    if ":latest" in image_url or image_url.endswith(":latest"):
        failures.append("image_url uses mutable latest tag")
    if not IMAGE_DIGEST_RE.match(digest):
        failures.append("image_url digest is missing or not sha256")
    if manifest is None:
        failures.append("image manifest evidence is missing")
        return failures
    if manifest.get("verdict") != "pass":
        failures.append("image manifest verdict is not pass")
    if manifest.get("image") != image_url:
        failures.append("image_url does not match image manifest")
    if manifest.get("digest") != digest:
        failures.append("image_url digest does not match image manifest digest")
    return failures


def evaluate_deploy_payload(payload: dict[str, Any], manifest: dict[str, Any] | None) -> list[str]:
    failures = validate_image_input(str(payload.get("image_url") or ""), manifest)
    deployments = list(payload.get("deployments") or [])
    roles = sorted(item.get("role") for item in deployments)
    if roles != ["api", "worker"]:
        failures.append(f"deployments must include exactly api and worker roles, got {roles}")
    for item in deployments:
        role = item.get("role") or "unknown"
        if not item.get("ok"):
            failures.append(f"{role} deploy did not succeed")
        if not item.get("terminal"):
            failures.append(f"{role} deploy did not reach terminal status")
        if item.get("timed_out"):
            failures.append(f"{role} deploy timed out")
        if not item.get("deploy_id"):
            failures.append(f"{role} deploy id is missing")
        if not item.get("service_id_sha256_16"):
            failures.append(f"{role} service hash is missing")
    return failures


def render_request(method: str, path: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "oasis-render-deploy-image",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Render API {method} {path} failed with HTTP {exc.code}: {raw[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Render API {method} {path} failed: {exc.reason}") from exc


def extract_id(payload: dict[str, Any]) -> str:
    for key in ("id", "deployId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    deploy = payload.get("deploy")
    if isinstance(deploy, dict):
        for key in ("id", "deployId"):
            value = deploy.get(key)
            if isinstance(value, str) and value:
                return value
    raise RuntimeError(f"Render deploy response did not include an ID: {json.dumps(payload, sort_keys=True)[:500]}")


def extract_status(payload: dict[str, Any]) -> str:
    for key in ("status", "deployStatus"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    deploy = payload.get("deploy")
    if isinstance(deploy, dict):
        return extract_status(deploy)
    return "unknown"


def trigger_deploy(service_id: str, image_url: str, token: str) -> str:
    payload = render_request("POST", f"/services/{service_id}/deploys", token, {"imageUrl": image_url})
    return extract_id(payload)


def wait_deploy(service_id: str, deploy_id: str, token: str, timeout_seconds: int, poll_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_payload: dict[str, Any] = {}
    while time.time() < deadline:
        last_payload = render_request("GET", f"/services/{service_id}/deploys/{deploy_id}", token)
        status = extract_status(last_payload).lower()
        if status in SUCCESS_STATUSES:
            return {"status": status, "terminal": True}
        if status in FAILURE_STATUSES or "failed" in status or "cancel" in status:
            return {"status": status, "terminal": True, "failed": True}
        time.sleep(poll_seconds)
    status = extract_status(last_payload).lower() if last_payload else "unknown"
    return {"status": status, "terminal": False, "failed": True, "timed_out": True}


def deploy_role(role: str, service_id: str, image_url: str, token: str, timeout_seconds: int, poll_seconds: int) -> dict[str, Any]:
    deploy_id = trigger_deploy(service_id, image_url, token)
    result = wait_deploy(service_id, deploy_id, token, timeout_seconds, poll_seconds)
    return {
        "role": role,
        "service_id_sha256_16": service_hash(service_id),
        "deploy_id": deploy_id,
        "status": result["status"],
        "terminal": result["terminal"],
        "ok": not result.get("failed"),
        "timed_out": bool(result.get("timed_out")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-service-id", default=os.environ.get("RENDER_API_SERVICE_ID", ""))
    parser.add_argument("--worker-service-id", default=os.environ.get("RENDER_WORKER_SERVICE_ID", ""))
    parser.add_argument("--api-key-env", default="RENDER_API_KEY")
    parser.add_argument("--image-url", required=True)
    parser.add_argument("--image-manifest", default=str(IMAGE_MANIFEST))
    parser.add_argument("--output", default=str(EVIDENCE / "02-render-deploy.json"))
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=int, default=15)
    args = parser.parse_args()

    manifest = load_json(Path(args.image_manifest))
    image_failures = validate_image_input(args.image_url, manifest)
    if image_failures:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "commit": git_value("rev-parse", "HEAD"),
            "branch": git_value("branch", "--show-current"),
            "image_url": args.image_url,
            "image_manifest": args.image_manifest,
            "deployments": [],
            "failures": image_failures,
            "verdict": "fail",
        }
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"Wrote Render deploy evidence to {output}")
        print(json.dumps({"verdict": payload["verdict"], "failures": image_failures}, indent=2))
        return 1

    token = os.environ.get(args.api_key_env)
    if not token:
        raise SystemExit(f"missing Render API key env var: {args.api_key_env}")
    if not args.api_service_id:
        raise SystemExit("missing --api-service-id or RENDER_API_SERVICE_ID")
    if not args.worker_service_id:
        raise SystemExit("missing --worker-service-id or RENDER_WORKER_SERVICE_ID")

    payload: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "image_url": args.image_url,
        "image_manifest": args.image_manifest,
        "sequence": [
            "deploy API image with Render preDeployCommand",
            "Render preDeployCommand runs alembic upgrade head",
            "Render preDeployCommand runs server.migration_check against the deployed database",
            "wait for API deploy terminal success before worker deploy",
            "deploy worker image",
            "wait for worker deploy terminal success",
        ],
        "deployments": [],
    }

    api = deploy_role("api", args.api_service_id, args.image_url, token, args.timeout_seconds, args.poll_seconds)
    payload["deployments"].append(api)
    if api["ok"]:
        worker = deploy_role("worker", args.worker_service_id, args.image_url, token, args.timeout_seconds, args.poll_seconds)
        payload["deployments"].append(worker)

    failures = evaluate_deploy_payload(payload, manifest)
    payload["failures"] = failures
    payload["verdict"] = "pass" if not failures else "fail"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote Render deploy evidence to {output}")
    print(json.dumps({"verdict": payload["verdict"], "deployments": payload["deployments"], "failures": failures}, indent=2))
    return 0 if payload["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
