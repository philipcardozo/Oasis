#!/usr/bin/env python3
"""Harden the GitHub staging environment for public-staging deploys."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], *, input_text: str | None = None) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=ROOT, text=True, input=input_text, capture_output=True, check=False)
    return result.returncode, (result.stdout + result.stderr).strip()


def gh_json(cmd: list[str]) -> dict[str, Any]:
    code, output = run(cmd)
    if code != 0:
        raise SystemExit(output)
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"GitHub API did not return JSON: {exc}\n{output[:500]}") from exc


def environment_payload(*, reviewer_id: int, prevent_self_review: bool) -> dict[str, Any]:
    return {
        "wait_timer": 0,
        "prevent_self_review": prevent_self_review,
        "reviewers": [{"type": "User", "id": reviewer_id}],
        "deployment_branch_policy": {
            "protected_branches": False,
            "custom_branch_policies": True,
        },
    }


def branch_policy_names() -> list[str]:
    payload = gh_json(["gh", "api", "repos/:owner/:repo/environments/staging/deployment-branch-policies"])
    return sorted(item.get("name", "") for item in payload.get("branch_policies", []) if item.get("name"))


def ensure_branch_policy(name: str) -> dict[str, Any]:
    if name in branch_policy_names():
        return {"name": name, "changed": False}
    payload = gh_json([
        "gh",
        "api",
        "--method",
        "POST",
        "repos/:owner/:repo/environments/staging/deployment-branch-policies",
        "-f",
        f"name={name}",
    ])
    return {"name": payload.get("name", name), "changed": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", default="staging")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--reviewer-id", type=int, default=0, help="GitHub user id; defaults to authenticated user")
    parser.add_argument("--prevent-self-review", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.environment != "staging":
        raise SystemExit("this helper is intentionally scoped to the staging environment")

    reviewer_id = args.reviewer_id
    if reviewer_id == 0:
        user = gh_json(["gh", "api", "user"])
        reviewer_id = int(user["id"])

    payload = environment_payload(reviewer_id=reviewer_id, prevent_self_review=args.prevent_self_review)
    if args.dry_run:
        print(json.dumps({"environment": args.environment, "branch": args.branch, "payload": payload}, indent=2))
        return 0

    code, output = run([
        "gh",
        "api",
        "--method",
        "PUT",
        f"repos/:owner/:repo/environments/{args.environment}",
        "--input",
        "-",
    ], input_text=json.dumps(payload))
    if code != 0:
        raise SystemExit(output)

    branch_result = ensure_branch_policy(args.branch)
    current = gh_json(["gh", "api", f"repos/:owner/:repo/environments/{args.environment}"])
    print(json.dumps({
        "environment": args.environment,
        "branch_policy": branch_result,
        "protection_rule_count": len(current.get("protection_rules") or []),
        "deployment_branch_policy": current.get("deployment_branch_policy"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
