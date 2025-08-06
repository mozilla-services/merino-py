"""Domain metadata extraction testing tool."""

from datetime import datetime
from typing import Any, Optional, cast
import asyncio
import typer
from rich.console import Console
from rich.table import Table
from pydantic import BaseModel
from google.cloud.storage import Blob

from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
    current_scraper,
    Scraper,
)
from merino.jobs.navigational_suggestions.utils import AsyncFaviconDownloader
from merino.jobs.navigational_suggestions.domain_metadata_uploader import (
    DomainMetadataUploader,
)
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


async def async_test_domain(domain: str, min_width: int) -> DomainTestResult:
    """Test metadata extraction for a single domain asynchronously"""
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
            uploader=cast(Any, MockUploader()),  # Use cast to satisfy the type checker
            async_favicon_downloader=favicon_downloader,
        )

        # Process the domain data using the standard method
        # We have a single domain, so take the first result
        metadata = extractor.process_domain_metadata(
            [domain_data], favicon_min_width=min_width, uploader=dummy_uploader
        )[0]

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


@cli.command()
def test_domains(
    domains: list[str] = typer.Argument(..., help="List of domains to test"),
    min_width: int = typer.Option(32, help="Minimum favicon width", show_default=True),
):
    """Test domain metadata extraction for multiple domains"""
    results = []

    for domain in domains:
        with console.status(f"Testing {domain}..."):
            result = test_domain(domain, min_width)
            results.append(result)

        if result.success:
            console.print(f"\nTesting domain: {domain}")

            table = Table(show_header=False, box=None)
            table.add_row("Title", result.metadata.get("title", "N/A"))
            table.add_row("Best Icon", result.metadata.get("icon", "N/A"))
            table.add_row("Total Favicons", str(result.details["favicons_found"]))

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
            console.print("❌ Failed!")
            if result.error:
                console.print(f"Error: {result.error}")

    successful = len([r for r in results if r.success])
    console.print(f"\nSummary: {successful}/{len(results)} domains processed successfully")


def main():
    """Entry point for CLI"""
    cli()
