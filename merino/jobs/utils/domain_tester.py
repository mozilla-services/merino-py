"""Domain metadata extraction testing tool."""

from datetime import datetime
from typing import Any, Optional
import typer
from rich.console import Console
from rich.table import Table
from pydantic import BaseModel

from merino.jobs.navigational_suggestions.domain_metadata_extractor import (
    DomainMetadataExtractor,
    Scraper,
)
from merino.jobs.navigational_suggestions.utils import AsyncFaviconDownloader

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


def test_domain(domain: str, min_width: int) -> DomainTestResult:
    """Test metadata extraction for a single domain"""
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

        scraper = Scraper()
        favicon_downloader = AsyncFaviconDownloader()
        extractor = DomainMetadataExtractor(
            blocked_domains=set(), scraper=scraper, favicon_downloader=favicon_downloader
        )

        metadata = extractor.get_domain_metadata([domain_data], min_width)[0]

        favicon_data = None
        total_favicons = 0
        if metadata["url"]:
            raw_favicon_data = scraper.scrape_favicon_data(metadata["url"])
            favicon_data = raw_favicon_data.model_dump()
            favicon_urls = set()

            for link in raw_favicon_data.links:
                if "href" in link:
                    favicon_urls.add(link["href"])

            for meta in raw_favicon_data.metas:
                if "content" in meta:
                    favicon_urls.add(meta["content"])

            if metadata["icon"]:
                favicon_urls.add(metadata["icon"])

            total_favicons = len(favicon_urls)

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
