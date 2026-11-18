"""Export the domain parity fixture for Embroidery's `domain:` URI normalization.

Runs Merino's manifest lookup normalization (`Provider._extract_full_domain`) over every URL in a
manifest and every entry in `CUSTOM_DOMAINS`, and writes what Merino looks icons up by. A Rust
test in Embroidery parses each host as `domain:<host>` and asserts that the key matches, so that
both services agree on domain keys.

Usage, from the repository root:

    uv run --frozen --no-sync python scripts/export_domain_parity_fixture.py \
        apps/embroidery/src/domain/fixtures/merino_domain_parity.json

To export from a saved manifest, pass its path before the output path.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from merino.jobs.navigational_suggestions.enrichments.custom_domains import CUSTOM_DOMAINS
from merino.providers.manifest.provider import Provider

MANIFEST_URL = "https://merino.services.mozilla.com/api/v1/manifest"


def host_of(url: str) -> str:
    """Return the URL's host as written, without userinfo or port.

    `urlsplit(url).hostname` lowercases, which would hide case differences from the Rust side.
    """
    netloc = urlsplit(url).netloc
    return netloc.rsplit("@", 1)[-1].split(":", 1)[0]


def main() -> None:
    """Write the fixture, sorted by URL so that re-exports produce small diffs."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        help="path to a saved manifest (default: fetch from Merino)",
    )
    parser.add_argument("output", type=Path, help="where to write the fixture")
    args = parser.parse_args()

    source = args.manifest if args.manifest is not None else MANIFEST_URL
    try:
        if args.manifest is None:
            manifest = httpx.get(MANIFEST_URL).raise_for_status().json()
        else:
            manifest = json.loads(args.manifest.read_text())
    except (httpx.HTTPError, OSError, ValueError) as error:
        parser.exit(1, f"Could not load manifest from {source}: {error}\n")

    # The job builds the URL of a custom domain by prefixing `https://`.
    urls = {entry["url"] for entry in manifest["domains"]}
    urls.update(f"https://{domain}" for domain in CUSTOM_DOMAINS)

    # `_extract_full_domain` doesn't use the instance, and building a `Provider` needs a backend.
    extract_full_domain = Provider._extract_full_domain
    fixture = [
        {"url": url, "host": host_of(url), "merino": extract_full_domain(None, url)}
        for url in sorted(urls)
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fixture, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(fixture)} entries to {args.output}")


if __name__ == "__main__":
    main()
