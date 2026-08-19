"""Policy tests for release-critical GitHub Actions workflows."""

from pathlib import Path
from typing import Any, cast

import yaml


WORKSPACE_ROOT = Path(__file__).parents[2]
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


def _load_workflow(filename: str) -> dict[str, Any]:
    """Load a workflow and normalize YAML 1.1's boolean ``on`` key."""
    workflow = yaml.safe_load((WORKFLOW_ROOT / filename).read_text())
    assert isinstance(workflow, dict)

    if True in workflow and "on" not in workflow:
        workflow["on"] = workflow.pop(True)

    return cast(dict[str, Any], workflow)


def test_publish_jobs_require_checks_tests_and_their_image_build() -> None:
    """Prevent a successful image build from bypassing failed validation."""
    workflow = _load_workflow("main-workflow.yaml")
    jobs = cast(dict[str, dict[str, Any]], workflow["jobs"])

    for job_name, expected_needs in PUBLISH_REQUIREMENTS.items():
        needs = cast(list[str], jobs[job_name]["needs"])
        assert set(needs) == expected_needs
        assert "if" not in jobs[job_name]


def test_pull_request_image_builds_receive_no_secrets() -> None:
    """Keep registry credentials out of workflows that execute pull-request code."""
    workflow = _load_workflow("pr-workflow.yaml")
    jobs = cast(dict[str, dict[str, Any]], workflow["jobs"])

    assert workflow["permissions"] == {"contents": "read"}
    for job_name in PR_IMAGE_BUILD_JOBS:
        assert "secrets" not in jobs[job_name]


def test_image_build_workflows_declare_no_registry_secrets() -> None:
    """Require registry credentials only in protected publishing workflows."""
    for filename in IMAGE_BUILD_WORKFLOWS:
        workflow = _load_workflow(filename)
        triggers = cast(dict[str, Any], workflow["on"])
        workflow_call = triggers["workflow_call"]

        assert workflow_call is None or "secrets" not in workflow_call


def test_load_test_skip_directive_conditions_the_locust_publisher() -> None:
    """Ensure the load-test skip directive bypasses the complete publishing job."""
    workflow = _load_workflow("publish-gar-image-locust.yaml")
    jobs = cast(dict[str, dict[str, Any]], workflow["jobs"])
    check_job = jobs["check-directive"]
    publish_job = jobs["publish-locust"]

    assert check_job["outputs"] == {"skip": "${{ steps.directive.outputs.skip }}"}
    check_steps = cast(list[dict[str, Any]], check_job["steps"])
    directive_step = next(step for step in check_steps if step.get("id") == "directive")
    directive_script = cast(str, directive_step["run"])
    abort_check = "grep -q '\\[load test: abort\\]'"
    skip_check = "grep -q '\\[load test: skip\\]'"
    assert abort_check in directive_script
    assert skip_check in directive_script
    assert directive_script.index(abort_check) < directive_script.index(skip_check)
    assert "grep -qi" not in directive_script

    abort_branch, remaining_script = directive_script.split("elif", maxsplit=1)
    skip_branch, default_branch = remaining_script.split("else", maxsplit=1)
    assert 'echo "skip=false"' in abort_branch
    assert 'echo "skip=true"' in skip_branch
    assert 'echo "skip=false"' in default_branch

    dockerhub_workflow = _load_workflow("publish-dockerhub-app-image.yaml")
    dockerhub_jobs = cast(dict[str, dict[str, Any]], dockerhub_workflow["jobs"])
    dockerhub_steps = cast(list[dict[str, Any]], dockerhub_jobs["publish"]["steps"])
    dockerhub_directive_step = next(
        step for step in dockerhub_steps if step.get("name") == "Parse load test directive"
    )
    dockerhub_script = cast(str, dockerhub_directive_step["run"])
    assert dockerhub_script.index(abort_check) < dockerhub_script.index(skip_check)
    assert "grep -qi" not in dockerhub_script

    assert publish_job["needs"] == "check-directive"
    assert publish_job["if"] == "needs.check-directive.outputs.skip != 'true'"


def test_dockerhub_build_generates_versioned_artifact_for_publishing() -> None:
    """Keep deployed version metadata and the build/publish artifact contract intact."""
    build_workflow = _load_workflow("build-dockerhub-app-image.yaml")
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
    assert create_index < build_index < save_index < upload_index

    create_script = cast(str, build_steps[create_index]["run"])
    save_script = cast(str, build_steps[save_index]["run"])
    assert "$GITHUB_SHA" in create_script
    assert "> version.json" in create_script
    assert save_script == "docker save app:build | gzip > merino-app.tar.gz"

    upload_step = next(step for step in build_steps if step.get("name") == "Upload image artifact")
    upload_config = cast(dict[str, str], upload_step["with"])

    publish_workflow = _load_workflow("publish-dockerhub-app-image.yaml")
    publish_jobs = cast(dict[str, dict[str, Any]], publish_workflow["jobs"])
    publish_steps = cast(list[dict[str, Any]], publish_jobs["publish"]["steps"])
    download_step = next(
        step for step in publish_steps if step.get("name") == "Download app image"
    )
    download_config = cast(dict[str, str], download_step["with"])

    assert upload_config == {"name": "merino-app-image", "path": "merino-app.tar.gz"}
    assert download_config == {"name": "merino-app-image", "path": "."}


def test_checks_run_pinned_actionlint() -> None:
    """Validate workflows with a pinned, checksum-verified actionlint binary."""
    workflow = _load_workflow("checks.yaml")
    jobs = cast(dict[str, dict[str, Any]], workflow["jobs"])
    steps = cast(list[dict[str, Any]], jobs["checks"]["steps"])
    actionlint_step = next(
        step for step in steps if step.get("name") == "Lint GitHub Actions workflows"
    )

    assert actionlint_step["env"] == {
        "ACTIONLINT_VERSION": "1.7.12",
        "ACTIONLINT_SHA256": "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
    }
    actionlint_script = cast(str, actionlint_step["run"])
    assert "actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz" in actionlint_script
    assert "sha256sum --check --strict" in actionlint_script
    assert '"$RUNNER_TEMP/actionlint" -color' in actionlint_script
