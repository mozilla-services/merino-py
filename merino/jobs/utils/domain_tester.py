"""Domain metadata extraction testing tool."""

from datetime import datetime
from typing import Any, Optional, cast, Type
import asyncio
import typer
from rich.console import Console
from rich.table import Table
from pydantic import BaseModel
from google.cloud.storage import Blob
import importlib
import contextvars

from merino.utils.gcs.models import BaseContentUploader

cli = typer.Typer(no_args_is_help=True)
console = Console()


class DomainTestResult(BaseModel):
    """Results from testing domain metadata extraction"""

    domain: str
    timestamp: str
    success: bool
    metadata: dict[str, Any]
    details: dict[str, Any]
    favicon_data: Optional[dict[str, list[dict[str, Any]]]]
    error: Optional[str] = None


def _get_required_classes() -> (
    tuple[Type[Any], contextvars.ContextVar[Any], Type[Any], Type[Any], Type[Any]]
):
    """Dynamically import required classes to avoid circular import at module level"""
    # Import at runtime to avoid circular dependency
    domain_metadata_extractor = importlib.import_module(
        "merino.jobs.navigational_suggestions.domain_metadata_extractor"
    )
    utils_module = importlib.import_module("merino.jobs.navigational_suggestions.utils")
    uploader_module = importlib.import_module(
        "merino.jobs.navigational_suggestions.domain_metadata_uploader"
    )

    return (
        domain_metadata_extractor.DomainMetadataExtractor,
        domain_metadata_extractor.current_scraper,
        domain_metadata_extractor.Scraper,
        utils_module.AsyncFaviconDownloader,
        uploader_module.DomainMetadataUploader,
    )


async def async_test_domain(domain: str, min_width: int) -> DomainTestResult:
    """Test metadata extraction for a single domain asynchronously"""
    timestamp = datetime.now().isoformat()

    try:
        # Get the required classes dynamically
        (
            DomainMetadataExtractor,
            current_scraper,
            Scraper,
            AsyncFaviconDownloader,
            DomainMetadataUploader,
        ) = _get_required_classes()

        domain_data = {
            "rank": 1,
            "domain": domain,
            "host": f"www.{domain}" if not domain.startswith("www.") else domain,
            "origin": f"https://{domain}",
            "suffix": domain.split(".")[-1],
            "categories": ["Unknown"],
        }

        favicon_downloader = AsyncFaviconDownloader()
        extractor = DomainMetadataExtractor(
            blocked_domains=set(), favicon_downloader=favicon_downloader
        )

        # Create a mock uploader that doesn't actually upload to GCS
        class MockUploader(BaseContentUploader):
            def upload_content(
                self, content, destination_name, content_type="text/plain", forced_upload=False
            ):
                mock_blob = Blob(name=destination_name, bucket=None)
                return mock_blob

            def upload_image(self, image, destination_name, forced_upload=False):
                # Just return a dummy URL instead of uploading
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
        results = await extractor._process_domains(
            [domain_data], favicon_min_width=min_width, uploader=dummy_uploader
        )
        metadata = results[0]

        favicon_data = None
        total_favicons = 0

        if metadata["url"]:
            base_url = metadata["url"]

            # For testing, we need to create a scraper and set it in the context
            with Scraper() as test_scraper:
                # Set the context variable for this test
                token = current_scraper.set(test_scraper)
                try:
                    # Open the URL with our test scraper
                    test_scraper.open(base_url)

                    # Get raw favicon data directly from the test scraper
                    raw_favicon_data = test_scraper.scrape_favicon_data()

                    # Use the extractor method with our context-aware scraper
                    processed_favicons = await extractor._extract_favicons(
                        base_url,
                        max_icons=100,  # Use high max to get all
                    )

                    # Create processed version of favicon data
                    processed_links = []
                    for favicon in processed_favicons:
                        # Only include link-type favicons that have href
                        if "href" in favicon:
                            processed_links.append(favicon)

                    # Replace the original links with processed ones to ensure
                    # all URLs are absolute, just like in production
                    raw_favicon_data.links = processed_links

                    favicon_data = raw_favicon_data.model_dump()
                    favicon_urls = set()

                    # Collect unique favicon URLs
                    for link in raw_favicon_data.links:
                        if "href" in link:
                            favicon_urls.add(link["href"])

                    for meta in raw_favicon_data.metas:
                        if "content" in meta:
                            favicon_urls.add(meta["content"])

                    if metadata["icon"]:
                        favicon_urls.add(metadata["icon"])

                    total_favicons = len(favicon_urls)
                finally:
                    # Reset the context variable
                    current_scraper.reset(token)

        details = {
            "base_url_tried": f"https://{domain}",
            "www_url_tried": f"https://www.{domain}",
            "final_url": metadata["url"],
            "favicons_found": total_favicons,
            "manifest_found": bool(favicon_data and favicon_data["manifests"]),
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

    try:
        async with asyncio.TaskGroup() as task_group:
            # Create tasks for all domains
            tasks = {
                domain: task_group.create_task(async_test_domain(domain, min_width))
                for domain in domains
            }

        # Collect results in the same order as input domains
        for domain in domains:
            result = tasks[domain].result()
            results.append(result)

    except* Exception as eg:
        console.print(f"[red]Errors occurred while probing domains: {eg}[/red]")
        # Return partial results for domains that succeeded
        for domain in domains:
            if domain in tasks and tasks[domain].done() and not tasks[domain].exception():
                results.append(tasks[domain].result())
            else:
                # Create a failed result for domains that didn't complete
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


@cli.command()
def test_domains(
    domains: list[str] = typer.Argument(..., help="List of domains to test"),
    min_width: int = typer.Option(32, help="Minimum favicon width", show_default=True),
):
    """Test domain metadata extraction for multiple domains"""
    # Use the new concurrent approach
    with console.status("Testing domains concurrently..."):
        results = asyncio.run(probe_domains(domains, min_width))

    # Display results
    for result in results:
        if result.success:
            console.print(f"\nTesting domain: {result.domain}")

            table = Table(show_header=False, box=None)
            table.add_row("Title", result.metadata.get("title", "N/A"))
            table.add_row("Best Icon", result.metadata.get("icon", "N/A"))
            table.add_row("Total Favicons", str(result.details.get("favicons_found", 0)))

            console.print("✅ Success!")
            console.print(table)

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
        else:
            console.print(f"\n❌ Failed testing domain: {result.domain}")
            if result.error:
                console.print(f"Error: {result.error}")

    successful = len([r for r in results if r.success])
    console.print(f"\nSummary: {successful}/{len(results)} domains processed successfully")


def main():
    """Entry point for CLI"""
    cli()
