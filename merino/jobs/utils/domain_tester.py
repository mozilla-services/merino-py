"""Domain metadata extraction testing tool."""

from datetime import datetime
from typing import Any, Optional, cast
import asyncio
import typer
from rich.console import Console
from rich.table import Table
from pydantic import BaseModel
from google.cloud.storage import Blob
import ast
import re
from pprint import pformat
import tldextract
from pathlib import Path

from merino.jobs.navigational_suggestions.favicon.favicon_selector import FaviconSelector

cli = typer.Typer(no_args_is_help=True)
console = Console()
FAVICON_PATH = "merino/jobs/navigational_suggestions/enrichments/custom_favicons.py"


class DomainTestResult(BaseModel):
    """Results from testing domain metadata extraction"""

    domain: str
    timestamp: str
    success: bool
    metadata: dict[str, Any]
    details: dict[str, Any]
    favicon_data: Optional[dict[str, list[dict[str, Any]]]]
    error: Optional[str] = None


async def async_test_domain(domain: str, min_width: int) -> DomainTestResult:
    """Test metadata extraction for a single domain asynchronously"""
    from merino.jobs.navigational_suggestions.processing.domain_processor import DomainProcessor
    from merino.jobs.navigational_suggestions.io import (
        AsyncFaviconDownloader,
        DomainMetadataUploader,
    )
    from merino.utils.gcs.models import BaseContentUploader

    timestamp = datetime.now().isoformat()

    try:
        domain_data = {
            "rank": 1,
            "domain": domain,
            "host": f"www.{domain}" if not domain.startswith("www.") else domain,
            "origin": f"https://{domain}",
            "suffix": domain.split(".")[-1],
            "categories": ["Unknown"],
        }

        favicon_downloader = AsyncFaviconDownloader()
        processor = DomainProcessor(blocked_domains=set(), favicon_downloader=favicon_downloader)

        # Create a mock uploader that doesn't actually upload to GCS
        class MockUploader(BaseContentUploader):
            def upload_content(
                self, content, destination_name, content_type="text/plain", forced_upload=False
            ):
                mock_blob = Blob(name=destination_name, bucket=None)
                return mock_blob

            def upload_image(self, image, destination_name, forced_upload=False):
                return f"https://dummy-cdn.example.com/{destination_name}"

            def get_most_recent_file(self, match, sort_key):
                return None

        # Create a domain metadata uploader with our mock uploader
        dummy_uploader = DomainMetadataUploader(
            force_upload=False,
            uploader=cast(Any, MockUploader()),
            async_favicon_downloader=favicon_downloader,
        )

        # Process the domain data using the standard method
        results = await processor._process_domains(
            [domain_data], favicon_min_width=min_width, uploader=dummy_uploader
        )
        metadata = results[0]

        # For detailed favicon information, we need to scrape separately
        favicon_data = None
        total_favicons = 0

        if metadata["url"]:
            from merino.jobs.navigational_suggestions.scrapers.web_scraper import WebScraper
            from merino.jobs.navigational_suggestions.favicon.favicon_extractor import (
                FaviconExtractor,
            )
            from merino.jobs.navigational_suggestions.scrapers.favicon_scraper import (
                FaviconScraper,
            )

            base_url = metadata["url"]

            with WebScraper() as web_scraper:
                scraped_url = web_scraper.open(base_url)
                if scraped_url:
                    page = web_scraper.get_page()
                    if page:
                        favicon_scraper = FaviconScraper(favicon_downloader)
                        favicon_extractor = FaviconExtractor(favicon_scraper)

                        # Extract all favicons
                        favicons = await favicon_extractor.extract_favicons(
                            page, scraped_url, max_icons=100
                        )

                        # Build favicon data structure
                        favicon_data = {
                            "links": [f for f in favicons if f.get("href")],
                            "metas": [],
                            "manifests": [],
                        }

                        favicon_urls = {f["href"] for f in favicons if f.get("href")}
                        if metadata["icon"]:
                            favicon_urls.add(metadata["icon"])

                        total_favicons = len(favicon_urls)

        details = {
            "base_url_tried": f"https://{domain}",
            "www_url_tried": f"https://www.{domain}",
            "final_url": metadata["url"],
            "favicons_found": total_favicons,
            "manifest_found": bool(favicon_data and favicon_data.get("manifests")),
        }

        return DomainTestResult(
            domain=domain,
            timestamp=timestamp,
            success=bool(metadata["url"] and metadata["icon"]),
            metadata=metadata,
            details=details,
            favicon_data=favicon_data,
        )

    except Exception as e:
        return DomainTestResult(
            domain=domain,
            timestamp=timestamp,
            success=False,
            metadata={},
            details={},
            favicon_data=None,
            error=str(e),
        )


def test_domain(domain: str, min_width: int) -> DomainTestResult:
    """Synchronous wrapper for async test domain function"""
    return asyncio.run(async_test_domain(domain, min_width))


async def probe_domains(domains: list[str], min_width: int) -> list[DomainTestResult]:
    """Test multiple domains concurrently using TaskGroup"""
    results = []
    tasks = {}

    try:
        async with asyncio.TaskGroup() as task_group:
            tasks = {
                domain: task_group.create_task(async_test_domain(domain, min_width))
                for domain in domains
            }

    except* Exception as eg:
        console.print(f"[red]Errors occurred while probing domains: {eg}[/red]")

    # Collect results in the same order as input domains (moved outside try/except)
    for domain in domains:
        if domain in tasks and tasks[domain].done() and not tasks[domain].exception():
            results.append(tasks[domain].result())
        else:
            results.append(
                DomainTestResult(
                    domain=domain,
                    timestamp=datetime.now().isoformat(),
                    success=False,
                    metadata={},
                    details={},
                    favicon_data=None,
                    error="Task failed or was cancelled",
                )
            )

    return results


def update_custom_favicons(title: str, url: str, table: Table) -> None:
    """Update the custom favicons dictionary with a given title and url."""
    dic = {title.lower(): url}
    with open(FAVICON_PATH, "r") as f:
        content = f.read()
    pattern = r"(\s*CUSTOM_FAVICONS\s*:\s*dict\[\s*str\s*,\s*str\s*\]\s*=\s*\{.*?\})"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    if not match:
        table.add_row("Error", "Cannot find CUSTOM_FAVICONS dictionary")
        return
    dict_str = match.group(1)
    try:
        dict_part = dict_str.split("=", 1)[1].strip()
        parsed_dict = ast.literal_eval(dict_part)
    except Exception as e:
        table.add_row("Error", f"Unable to parse CUSTOM_FAVICONS dictionary: {e}")
        return
    parsed_dict.update(dic)
    updated_dict_str = "\nCUSTOM_FAVICONS: dict[str, str] = {\n "
    updated_dict_str += (
        pformat(parsed_dict, indent=4).replace("{", "").replace("}", "").replace("'", '"')
    )
    updated_dict_str += "\n}"
    updated_content = content.replace(dict_str, updated_dict_str)
    try:
        # Abstract Syntax Tree parsing suceeds only if the target is valid python code
        ast.parse(updated_content)
        with open(FAVICON_PATH, "w") as f:
            f.write(updated_content)
        table.add_row("Saved Domain", title)
        table.add_row("Saved URL", url)
        table.add_row("Save PATH", FAVICON_PATH)
    except Exception:
        table.add_row("Error", "Result is an invalid file")


def favicon_width_convertor(width: str) -> int:
    """Convert the width of a favicon to an integer."""
    size = width.split("x")
    if len(size) < 2:
        best_width = 1
    else:
        best_width = int(max(size))
    return best_width


@cli.command()
def test_domains(
    domains: list[str] = typer.Argument(..., help="List of domains to test"),
    min_width: int = typer.Option(32, help="Minimum favicon width", show_default=True),
    save_favicon: bool = typer.Option(False, "--save", help="Save custom favicon", is_flag=True),
):
    """Test domain metadata extraction for multiple domains"""
    if not Path("pyproject.toml").exists():
        print("The probe-images command must be run from the root directory.")
        return

    with console.status("Testing domains concurrently..."):
        results = asyncio.run(probe_domains(domains, min_width))

    for result in results:
        if result.success:
            console.print(f"\nTesting domain: {result.domain}")

            table = Table(show_header=False, box=None)
            table.add_row("Title", result.metadata.get("title", "N/A"))
            table.add_row("Best Icon", result.metadata.get("icon", "N/A"))
            table.add_row("Total Favicons", str(result.details.get("favicons_found", 0)))

            console.print("✅ Success!")
            console.print(table)

            save_table = Table(show_header=False, box=None)

            if save_favicon and result.favicon_data:
                title = tldextract.extract(result.domain).domain
                best_icon = None
                best_width = 0
                best_source = "default"

                for icon in result.favicon_data["links"]:
                    width = favicon_width_convertor(icon.get("sizes", "1x1"))
                    # Use production FaviconSelector logic instead of simple comparison
                    if FaviconSelector.is_better_favicon(icon, width, best_width, best_source):
                        best_icon = icon
                        best_width = width
                        best_source = icon.get("_source", "default")
                if title and best_icon:
                    update_custom_favicons(title, best_icon["href"], save_table)
                elif not title:
                    save_table.add_row("Error", "Unable to extract domain")
                else:
                    save_table.add_row("Error", "Unable to find any favicons")

            if result.favicon_data:
                console.print("\nAll favicons found:")
                for link in result.favicon_data["links"]:
                    if "href" in link:
                        desc = []
                        if "rel" in link:
                            desc.append(f"rel={','.join(link['rel'])}")
                        if "sizes" in link:
                            desc.append(f"size={link['sizes']}")
                        if "type" in link:
                            desc.append(f"type={link['type']}")
                        console.print(f"- {link['href']} ({' '.join(desc)})")

            if save_favicon:
                console.print("\nSave Results:")
                console.print(save_table)

        else:
            console.print(f"\n❌ Failed testing domain: {result.domain}")
            if result.error:
                console.print(f"Error: {result.error}")

    successful = len([r for r in results if r.success])
    console.print(f"\nSummary: {successful}/{len(results)} domains processed successfully")


def main():
    """Entry point for CLI"""
    cli()
