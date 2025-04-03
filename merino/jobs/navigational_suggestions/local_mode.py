"""Local mode implementation for navigational suggestions"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class LocalMetricsCollector:
    """Collects metrics for local domain processing"""

    def __init__(self, output_dir: str = "./local_data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)

        # Initialize metrics
        self.domains_processed = 0
        self.favicons_found = 0
        self.urls_found = 0
        self.titles_found = 0
        self.start_time = datetime.now()

        # Detailed records for each domain
        self.domain_records: List[Dict[str, Any]] = []

    def record_domain_result(self, domain: str, result: Dict[str, Any]):
        """Record metrics for a processed domain"""
        self.domains_processed += 1

        if result.get("icon"):
            self.favicons_found += 1
        if result.get("url"):
            self.urls_found += 1
        if result.get("title"):
            self.titles_found += 1

        # Add to detailed records
        self.domain_records.append(
            {
                "domain": domain,
                "success": bool(result.get("icon")),
                "url": result.get("url"),
                "title": result.get("title"),
            }
        )

        # Log progress every 10 domains
        if self.domains_processed % 10 == 0:
            self._log_progress()

    def _log_progress(self) -> None:
        """Log current progress"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = self.domains_processed / max(elapsed, 0.1)

        logger.info(
            f"Progress: {self.domains_processed} domains processed "
            f"({rate:.1f} domains/sec) - "
            f"Success rate: {self.favicons_found/max(1, self.domains_processed):.1%}"
        )

    def save_report(self) -> None:
        """Save final metrics report"""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        # Create summary report
        report = {
            "total_domains": self.domains_processed,
            "favicons_found": self.favicons_found,
            "favicon_success_rate": self.favicons_found / max(1, self.domains_processed),
            "urls_found": self.urls_found,
            "url_success_rate": self.urls_found / max(1, self.domains_processed),
            "titles_found": self.titles_found,
            "title_success_rate": self.titles_found / max(1, self.domains_processed),
            "elapsed_seconds": elapsed,
            "processing_rate": self.domains_processed / max(elapsed, 0.1),
            "timestamp": datetime.now().isoformat(),
            "domains": self.domain_records,
        }

        # Save to timestamped file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"metrics_{timestamp}.json"

        import json

        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)

        # Print summary
        logger.info("===== Run Summary =====")
        logger.info(f"Domains processed: {self.domains_processed}")
        logger.info(f"Favicon success rate: {report['favicon_success_rate']:.2%}")
        logger.info(f"URL success rate: {report['url_success_rate']:.2%}")
        logger.info(f"Title success rate: {report['title_success_rate']:.2%}")
        logger.info(f"Time elapsed: {elapsed:.1f} seconds")
        logger.info(f"Processing speed: {report['processing_rate']:.1f} domains/second")
        logger.info(f"Detailed metrics saved to: {output_file}")
        logger.info("=======================")


class LocalDomainDataProvider:
    """Provides domain data without requiring BigQuery access"""

    def __init__(self, custom_domains: List[str], sample_size: int = 50):
        """Initialize with domain sample parameters

        Args:
            custom_domains: List of domain strings
            sample_size: Number of domains to process
        """
        self.custom_domains = custom_domains
        self.sample_size = sample_size

    def get_domain_data(self) -> List[Dict[str, Any]]:
        """Generate domain data for testing locally"""
        domains = []

        # Get domain sample
        max_index = min(self.sample_size, len(self.custom_domains))
        domain_sample = self.custom_domains[:max_index]

        for i, domain_str in enumerate(domain_sample):
            domains.append(
                {
                    "rank": i + 1,
                    "domain": domain_str,
                    "host": domain_str,
                    "origin": f"https://{domain_str}",
                    "suffix": domain_str.split(".")[-1],
                    "categories": ["Local_Testing"],
                    "source": "local-test",
                }
            )

        logger.info(f"Generated {len(domains)} local test domains")
        logger.info(f"Sample range: 0 to {max_index-1}")
        return domains
