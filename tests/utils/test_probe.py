"""Probe relevant test files for staged & unsteged modified source files.
This can be used to selectively run specific tests (unit and integration)
based on changes.
"""

import subprocess
import sys

from tests.utils.source_test_mapping import get_tests_for_source


def run_git_command(args: list[str]) -> tuple[str, int]:
    """Run a git command and return output and exit code.

    Args:
        args: List of git command arguments (e.g., ['status', '--short'])

    Returns:
        Tuple of (stdout output, return code)
    """
    try:
        result = subprocess.run(["git"] + args, capture_output=True, text=True, check=False)
        return result.stdout.strip(), result.returncode
    except FileNotFoundError:
        print("Error: Git is not installed or not in PATH", file=sys.stderr)
        sys.exit(1)


def is_git_repository() -> bool:
    """Check if current directory is inside a git repository.

    Returns:
        True if inside a git repository, False otherwise
    """
    output, returncode = run_git_command(["rev-parse", "--is-inside-work-tree"])
    return returncode == 0 and output == "true"


def get_staged_files() -> list[str]:
    """Get list of staged files (files in the index).

    Returns:
        List of file paths that are staged for commit
    """
    output, returncode = run_git_command(["diff", "--cached", "--name-only"])
    if returncode != 0:
        return []
    return [f for f in output.split("\n") if f]


def get_unstaged_files() -> list[str]:
    """Get list of unstaged modified files.

    Returns:
        List of file paths that are modified but not staged
    """
    output, returncode = run_git_command(["diff", "--name-only"])
    if returncode != 0:
        return []
    return [f for f in output.split("\n") if f]


if __name__ == "__main__":
    # Check if we're in a git repository
    if not is_git_repository():
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    include_indirect = True
    if len(sys.argv) > 1 and sys.argv[1] == "-q":
        include_indirect = False

    # Get all modified files in "merino/"
    files = [*get_staged_files(), *get_unstaged_files()]
    tests = set()
    for f in files:
        if not f.startswith("merino/"):
            continue
        tests.update(get_tests_for_source(f, include_indirect))

    print(" ".join(sorted(tests)))
