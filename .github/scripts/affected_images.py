"""Select Docker builds using Moon's task inputs and the triggering GitHub event.

Subprocesses use Git and the pinned Moon from CI's PATH, with no shell. The comparison
ref comes from GitHub's event; changed filenames are passed to Moon through stdin.
"""

import json
import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

IMAGE_PROJECTS = ("merino", "fleece", "load-tests")


def comparison_base(event_name: str, event: dict[str, Any]) -> str | None:
    """Compare PR merge checkouts to their base, and pushes to the previous tip."""
    if event_name == "pull_request":
        return str(event["pull_request"]["base"]["sha"])
    if event_name == "push":
        return str(event["before"])
    if event_name == "workflow_dispatch":
        return None  # An explicit rebuild also refreshes external base images/dependencies.
    raise ValueError(f"Unsupported image-build event: {event_name}")


def changed_files(base: str | None) -> list[str] | None:
    """Return both sides of renames; rebuild everything if the base is unavailable."""
    if not base or base == "0" * 40:
        return None
    try:
        # A direct diff handles multi-commit pushes and force-push reversions as well as PRs.
        result = subprocess.run(  # nosec B607
            ["git", "diff", "--name-only", "--no-renames", "-z", base, "HEAD", "--"],
            check=True,
            capture_output=True,
            shell=False,  # nosec B603
        )
    except subprocess.CalledProcessError:
        print("Comparison base unavailable; rebuilding every image.", file=sys.stderr)
        return None
    return [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]


def select_images(files: list[str] | None) -> set[str]:
    """Ask Moon which Docker tasks consume the changed files, without running builds."""
    if files is None or any("\n" in path or "\r" in path for path in files):
        # Moon's stdin protocol is line-based. Unusual filenames must not hide a change.
        return set(IMAGE_PROJECTS)
    if not files:
        return set()
    result = subprocess.run(  # nosec B607
        ["moon", "query", "tasks", "--id", "docker-build", "--affected=stdin"],
        input="\n".join(files) + "\n",
        text=True,
        check=True,
        capture_output=True,
        shell=False,  # nosec B603
    )
    selected = set(json.loads(result.stdout)["tasks"])
    if not selected <= set(IMAGE_PROJECTS):
        raise ValueError(f"Docker projects missing CI build/publish wiring: {sorted(selected)}")
    return selected


def main() -> None:
    """Write explicit booleans for each build only after selection succeeds."""
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    base = comparison_base(os.environ["GITHUB_EVENT_NAME"], event)
    selected = select_images(changed_files(base))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        for project in IMAGE_PROJECTS:
            key = project.replace("-", "_")
            output.write(f"{key}={str(project in selected).lower()}\n")
    print(f"Images to build: {', '.join(sorted(selected)) or 'none'}")


if __name__ == "__main__":
    main()
