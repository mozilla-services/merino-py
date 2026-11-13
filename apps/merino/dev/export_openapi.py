"""Generate or check the committed OpenAPI schema served by `merino.web.docs`.

The schema is built from the ALL runtime mode, so it documents every endpoint regardless of
the mode a deployment runs in.

Usage (from the workspace root):

    moon run merino:openapi-export   # regenerate merino/data/openapi.json
    moon run merino:openapi-check    # fail if the committed file is out of date

Or directly: ``MERINO_ENV=production uv run python apps/merino/dev/export_openapi.py [--check]``.
"""

import argparse
import json
import sys

from pathlib import Path
from typing import Any

from merino.runtime import RuntimeMode
from merino.web.docs import SCHEMA_PATH

REGENERATE_COMMAND = "moon run merino:openapi-export"


def build_schema() -> dict[str, Any]:
    """Return the OpenAPI schema for the ALL runtime mode."""
    from merino.main import create_app

    return create_app(RuntimeMode.ALL).openapi()


def render_schema(schema: dict[str, Any]) -> str:
    """Serialize a schema the way it is committed: indented, key order kept, newline-ended."""
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def export_schema(path: Path, check: bool = False) -> bool:
    """Write the ALL-mode schema to ``path``, or only compare against it when ``check`` is set.

    Returns whether ``path`` holds the current schema afterwards.
    """
    rendered = render_schema(build_schema())

    if check:
        return path.is_file() and path.read_text(encoding="utf-8") == rendered

    path.write_text(rendered, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    """Run the exporter CLI and return its exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of writing when the committed schema is out of date.",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=SCHEMA_PATH,
        help="Schema file to write or check (default: the committed schema).",
    )
    args = parser.parse_args(argv)

    if export_schema(args.path, check=args.check):
        print(f"OpenAPI schema {'is up to date' if args.check else 'written'}: {args.path}")
        return 0

    print(
        f"OpenAPI schema is out of date: {args.path}\nRegenerate it with: {REGENERATE_COMMAND}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
