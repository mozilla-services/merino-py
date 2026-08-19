#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = ["pyyaml==6.0.3"]
# ///

"""Validate release-critical GitHub Actions workflow policies."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import yaml


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = WORKSPACE_ROOT / ".github" / "workflows"

PUBLISH_REQUIREMENTS = {
    "run-publish-gar-image": {
        "run-checks",
        "run-tests",
        "run-build-gar-image",
    },
    "run-publish-gar-image-fleece": {
        "run-checks",
        "run-tests",
        "run-build-gar-image-fleece",
    },
    "run-publish-gar-image-locust": {
        "run-checks",
        "run-tests",
        "run-build-gar-image-locust",
    },
    "run-publish-dockerhub-app": {
        "run-checks",
        "run-tests",
        "run-build-dockerhub-app",
    },
}

PR_IMAGE_BUILD_JOBS = {
    "run-build-gar-image",
    "run-build-gar-image-fleece",
    "run-build-gar-image-locust",
}

IMAGE_BUILD_WORKFLOWS = {
    "build-dockerhub-app-image.yaml",
    "build-gar-image.yaml",
    "build-gar-image-fleece.yaml",
    "build-gar-image-locust.yaml",
}


class PolicyViolation(Exception):
    """Raised when a workflow violates a release-critical policy."""


def require(condition: bool, message: str) -> None:
    """Raise a policy violation when a required condition is false."""
    if not condition:
        raise PolicyViolation(message)


def load_workflow(filename: str) -> dict[str, Any]:
    """Load a workflow and normalize YAML 1.1's boolean ``on`` key."""
    workflow_data = yaml.safe_load((WORKFLOW_ROOT / filename).read_text())
    require(isinstance(workflow_data, dict), f"{filename} must contain a YAML mapping")
    workflow = cast(dict[Any, Any], workflow_data)

    if True in workflow and "on" not in workflow:
        workflow["on"] = workflow.pop(True)

    return cast(dict[str, Any], workflow)


def check_publish_prerequisites() -> None:
    """Require validation and the matching build before every publisher."""
    workflow = load_workflow("main-workflow.yaml")
    jobs = cast(dict[str, dict[str, Any]], workflow["jobs"])

    for job_name, expected_needs in PUBLISH_REQUIREMENTS.items():
        job = jobs[job_name]
        needs = job.get("needs")
        require(isinstance(needs, list), f"{job_name}.needs must be a list")
        require(
            set(cast(list[str], needs)) == expected_needs,
            f"{job_name}.needs must be exactly {sorted(expected_needs)}",
        )
        require("if" not in job, f"{job_name} must not override dependency failure handling")


def check_pull_request_permissions() -> None:
    """Keep registry credentials out of workflows that execute pull-request code."""
    workflow = load_workflow("pr-workflow.yaml")
    jobs = cast(dict[str, dict[str, Any]], workflow["jobs"])

    require(
        workflow.get("permissions") == {"contents": "read"},
        "pr-workflow permissions must be limited to contents: read",
    )
    for job_name in PR_IMAGE_BUILD_JOBS:
        require("secrets" not in jobs[job_name], f"{job_name} must not receive secrets")


def check_build_workflow_permissions() -> None:
    """Require registry credentials only in protected publishing workflows."""
    for filename in IMAGE_BUILD_WORKFLOWS:
        workflow = load_workflow(filename)
        triggers = cast(dict[str, Any], workflow["on"])
        workflow_call = triggers["workflow_call"]
        require(
            workflow_call is None or "secrets" not in workflow_call,
            f"{filename} must not declare registry secrets",
        )


def check_load_test_directives() -> None:
    """Keep directive precedence aligned and gate the complete Locust publisher."""
    workflow = load_workflow("publish-gar-image-locust.yaml")
    jobs = cast(dict[str, dict[str, Any]], workflow["jobs"])
    check_job = jobs["check-directive"]
    publish_job = jobs["publish-locust"]

    require(
        check_job.get("outputs") == {"skip": "${{ steps.directive.outputs.skip }}"},
        "check-directive must export the skip decision",
    )
    check_steps = cast(list[dict[str, Any]], check_job["steps"])
    directive_step = next(step for step in check_steps if step.get("id") == "directive")
    directive_script = cast(str, directive_step["run"])
    abort_check = "grep -q '\\[load test: abort\\]'"
    skip_check = "grep -q '\\[load test: skip\\]'"
    require(abort_check in directive_script, "Locust must recognize the abort directive")
    require(skip_check in directive_script, "Locust must recognize the skip directive")
    require(
        directive_script.index(abort_check) < directive_script.index(skip_check),
        "Locust directive precedence must be abort before skip",
    )
    require("grep -qi" not in directive_script, "Load-test directives must be case-sensitive")

    abort_branch, remaining_script = directive_script.split("elif", maxsplit=1)
    skip_branch, default_branch = remaining_script.split("else", maxsplit=1)
    require('echo "skip=false"' in abort_branch, "abort must publish the Locust image")
    require('echo "skip=true"' in skip_branch, "skip must skip the Locust publisher")
    require('echo "skip=false"' in default_branch, "the default must publish the Locust image")

    dockerhub_workflow = load_workflow("publish-dockerhub-app-image.yaml")
    dockerhub_jobs = cast(dict[str, dict[str, Any]], dockerhub_workflow["jobs"])
    dockerhub_steps = cast(list[dict[str, Any]], dockerhub_jobs["publish"]["steps"])
    dockerhub_directive_step = next(
        step for step in dockerhub_steps if step.get("name") == "Parse load test directive"
    )
    dockerhub_script = cast(str, dockerhub_directive_step["run"])
    require(
        dockerhub_script.index(abort_check) < dockerhub_script.index(skip_check),
        "Docker Hub directive precedence must be abort before skip",
    )
    require("grep -qi" not in dockerhub_script, "Load-test directives must be case-sensitive")

    require(publish_job.get("needs") == "check-directive", "Locust publish must need the decision")
    require(
        publish_job.get("if") == "needs.check-directive.outputs.skip != 'true'",
        "Locust publish must be conditional on the exported skip decision",
    )


def check_dockerhub_artifact_contract() -> None:
    """Keep deployed version metadata and the build/publish artifact contract intact."""
    build_workflow = load_workflow("build-dockerhub-app-image.yaml")
    build_jobs = cast(dict[str, dict[str, Any]], build_workflow["jobs"])
    build_steps = cast(list[dict[str, Any]], build_jobs["build"]["steps"])
    create_index = next(
        index
        for index, step in enumerate(build_steps)
        if step.get("name") == "Create version.json"
    )
    build_index = next(
        index
        for index, step in enumerate(build_steps)
        if step.get("name") == "Build Merino app image"
    )
    save_index = next(
        index
        for index, step in enumerate(build_steps)
        if step.get("name") == "Save image artifact"
    )
    upload_index = next(
        index
        for index, step in enumerate(build_steps)
        if step.get("name") == "Upload image artifact"
    )
    require(
        create_index < build_index < save_index < upload_index,
        "Docker Hub version, build, save, and upload steps are out of order",
    )

    create_script = cast(str, build_steps[create_index]["run"])
    save_script = cast(str, build_steps[save_index]["run"])
    require("$GITHUB_SHA" in create_script, "version.json must contain GITHUB_SHA")
    require("> version.json" in create_script, "the metadata step must write version.json")
    require(
        save_script == "docker save app:build | gzip > merino-app.tar.gz",
        "the Docker Hub builder must save app:build as merino-app.tar.gz",
    )

    upload_step = build_steps[upload_index]
    upload_config = cast(dict[str, str], upload_step["with"])
    publish_workflow = load_workflow("publish-dockerhub-app-image.yaml")
    publish_jobs = cast(dict[str, dict[str, Any]], publish_workflow["jobs"])
    publish_steps = cast(list[dict[str, Any]], publish_jobs["publish"]["steps"])
    download_step = next(
        step for step in publish_steps if step.get("name") == "Download app image"
    )
    download_config = cast(dict[str, str], download_step["with"])
    require(
        upload_config == {"name": "merino-app-image", "path": "merino-app.tar.gz"},
        "the Docker Hub build artifact contract changed",
    )
    require(
        download_config == {"name": "merino-app-image", "path": "."},
        "the Docker Hub publisher artifact contract changed",
    )


CHECKS: tuple[Callable[[], None], ...] = (
    check_publish_prerequisites,
    check_pull_request_permissions,
    check_build_workflow_permissions,
    check_load_test_directives,
    check_dockerhub_artifact_contract,
)


def main() -> int:
    """Run every policy check and report all detected violations."""
    violations: list[str] = []

    for check in CHECKS:
        try:
            check()
        except (
            KeyError,
            PolicyViolation,
            StopIteration,
            TypeError,
            ValueError,
            yaml.YAMLError,
        ) as exc:
            violations.append(f"{check.__name__}: {exc}")

    if violations:
        print("GitHub Actions policy violations:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("GitHub Actions policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
