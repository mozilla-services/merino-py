"""Regression checks for image selection, history handling, and Moon build boundaries.

Subprocesses use fixed Git and Moon commands from PATH, with no shell. Git mutations
are limited to a disposable repository created by the history test.
"""

import contextlib
import json
import os
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from affected_images import IMAGE_PROJECTS, changed_files, comparison_base, main, select_images


class EventTests(unittest.TestCase):
    """Keep PR comparisons, push comparisons, and manual rebuilds distinct."""

    def test_comparison_base(self) -> None:
        """Use the PR base or pre-push tip, and rebuild all on manual dispatch."""
        self.assertEqual(
            comparison_base("pull_request", {"pull_request": {"base": {"sha": "pr-base"}}}),
            "pr-base",
        )
        self.assertEqual(comparison_base("push", {"before": "old-tip"}), "old-tip")
        self.assertIsNone(comparison_base("workflow_dispatch", {}))
        with self.assertRaises(ValueError):
            comparison_base("schedule", {})

    def test_missing_base_rebuilds_all(self) -> None:
        """New branches and unavailable commits must never silently skip images."""
        for base in (None, "", "0" * 40):
            with self.subTest(base=base):
                self.assertEqual(select_images(changed_files(base)), set(IMAGE_PROJECTS))
        with patch(
            "affected_images.subprocess.run", side_effect=subprocess.CalledProcessError(128, "git")
        ):
            self.assertEqual(select_images(changed_files("missing")), set(IMAGE_PROJECTS))

    def test_filename_boundaries(self) -> None:
        """NUL-delimited Git output preserves spaces, Unicode, and newlines."""
        output = "apps/fleece/a b.py\0apps/merino/café.py\0apps/merino/a\nb.py\0"
        with patch("affected_images.subprocess.run") as run:
            run.return_value.stdout = output.encode()
            self.assertEqual(changed_files("base"), output.rstrip("\0").split("\0"))
        self.assertEqual(select_images(["a\nb"]), set(IMAGE_PROJECTS))
        self.assertEqual(select_images(["a\rb"]), set(IMAGE_PROJECTS))
        self.assertEqual(select_images([]), set())

    def test_query_failure_is_fatal(self) -> None:
        """A failed or unexpected Moon response must fail selection, not skip builds."""
        with patch(
            "affected_images.subprocess.run", side_effect=subprocess.CalledProcessError(1, "moon")
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                select_images(["uv.lock"])
        with patch("affected_images.subprocess.run") as run:
            for response in ("not json", '{"tasks": {"unwired-project": {}}}'):
                with self.subTest(response=response):
                    run.return_value.stdout = response
                    with self.assertRaises(ValueError):
                        select_images(["uv.lock"])

    def test_outputs(self) -> None:
        """Emit true and false explicitly, including the load_tests output name."""
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / "event.json"
            output = Path(directory) / "output"
            event.write_text(json.dumps({"before": "base"}))
            with (
                patch.dict(
                    os.environ,
                    {
                        "GITHUB_EVENT_NAME": "push",
                        "GITHUB_EVENT_PATH": str(event),
                        "GITHUB_OUTPUT": str(output),
                    },
                ),
                patch("affected_images.changed_files", return_value=["file"]),
                patch("affected_images.select_images", return_value={"fleece"}),
            ):
                main()
            self.assertEqual(output.read_text(), "merino=false\nfleece=true\nload_tests=false\n")

    def test_git_push_and_reversion(self) -> None:
        """Include renames and all pushed commits, even when HEAD is an ancestor of before."""
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):

            def git(*args: str) -> str:
                """Run Git only inside this disposable repository."""
                return (
                    subprocess.check_output(  # nosec B607
                        ["git", "-c", "commit.gpgsign=false", *args],
                        stderr=subprocess.DEVNULL,
                        shell=False,  # nosec B603
                    )
                    .decode()
                    .strip()
                )

            git("init", "-q")
            git("config", "user.name", "CI test")
            git("config", "user.email", "ci@example.invalid")
            Path("merino.txt").write_text("original")
            git("add", ".")
            git("commit", "-qm", "initial")
            initial = git("rev-parse", "HEAD")
            Path("merino.txt").rename("fleece.txt")
            git("add", "-A")
            git("commit", "-qm", "rename")
            Path("docs.txt").write_text("docs")
            git("add", ".")
            git("commit", "-qm", "docs")
            tip = git("rev-parse", "HEAD")
            expected = {"merino.txt", "fleece.txt", "docs.txt"}
            self.assertEqual(set(changed_files(initial) or []), expected)
            git("checkout", "-q", initial)
            self.assertEqual(set(changed_files(tip) or []), expected)


class MoonTaskTests(unittest.TestCase):
    """Exercise the real pinned Moon CLI against this repository's task definitions."""

    def test_project_selection(self) -> None:
        """Project code, shared inputs, docs, additions, and deletions select safe builds."""
        all_images = set(IMAGE_PROJECTS)
        cases = {
            "apps/fleece/merino_fleece/app.py": {"fleece"},
            "apps/merino/merino/main.py": {"merino", "load-tests"},
            "packages/merino-common/merino_common/__init__.py": all_images,
            "tools/load-tests/locustfiles/locustfile.py": {"load-tests"},
            "apps/fleece/merino_fleece/deleted-file.py": {"fleece"},
            "apps/merino/merino/new-file.py": {"merino", "load-tests"},
            "dev/GeoLite2-City-Test.mmdb": {"merino", "load-tests"},
            "docs/dev/monorepo.md": set(),
            "README.md": set(),
            "uv.lock": all_images,
            "pyproject.toml": all_images,
            "apps/fleece/pyproject.toml": all_images,
            ".dockerignore": all_images,
            ".prototools": all_images,
            "version.json": all_images,
            "LICENSE": all_images,
            ".moon/tasks/docker.yml": all_images,
            ".github/workflows/main-workflow.yaml": all_images,
            ".github/actions/build-project-image/action.yaml": all_images,
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(select_images([path]), expected)
        self.assertEqual(select_images(["apps/fleece/old.py", "apps/merino/new.py"]), all_images)

    def test_builds_do_not_install_host_python(self) -> None:
        """Docker tasks bypass host installation and cannot return a cached missing image."""
        result = subprocess.check_output(  # nosec B607
            ["moon", "query", "tasks", "--id", "docker-build"],
            shell=False,  # nosec B603
        )
        tasks = json.loads(result)["tasks"]
        self.assertEqual(set(tasks), set(IMAGE_PROJECTS))
        for project, project_tasks in tasks.items():
            with self.subTest(project=project):
                task = project_tasks["docker-build"]
                self.assertFalse(task.get("deps"))
                self.assertFalse(task["options"]["cache"])
                self.assertTrue(task["options"]["runFromWorkspaceRoot"])

    def test_python_tasks_still_install_dependencies(self) -> None:
        """Inherited Python tasks retain their direct workspace install dependency."""
        result = subprocess.check_output(  # nosec B607
            ["moon", "query", "tasks"],
            shell=False,  # nosec B603
        )
        tasks = json.loads(result)["tasks"]
        for project in (*IMAGE_PROJECTS, "merino-common"):
            for name, task in tasks[project].items():
                if name not in ("lint", "format-check", "security", "typecheck", "test"):
                    continue
                with self.subTest(project=project, task=name):
                    self.assertIn("workspace:install", [dep["target"] for dep in task["deps"]])


if __name__ == "__main__":
    unittest.main()
