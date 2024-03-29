"""Compare Domain files for Top Picks"""


class DomainDiff:
    """Process and prepare diff for domain files."""

    latest_domain_data: dict[str, list[dict[str, str]]]
    old_domain_data: dict[str, list[dict[str, str]]]

    def __init__(self, latest_domain_data, old_domain_data) -> None:
        self.latest_domain_data = latest_domain_data
        self.old_domain_data = old_domain_data

    @staticmethod
    def process_domains(domain_data: dict[str, list[dict[str, str]]]) -> list[str]:
        """Process the domain list and return a list of all second-level domains."""
        return [entry["domain"] for entry in domain_data["domains"]]

    @staticmethod
    def process_urls(domain_data: dict[str, list[dict[str, str]]]) -> list[str]:
        """Process the domain list and return a list of all urls."""
        return [entry["url"] for entry in domain_data["domains"]]

    def compare_top_picks(
        self,
        new_top_picks: dict[str, list[dict[str, str]]],
        old_top_picks: dict[str, list[dict[str, str]]],
    ) -> tuple[set[str], set[str], set[str]]:
        """Compare the previous file with new data to be written in latest file."""
        old_urls = self.process_urls(old_top_picks)
        new_urls = self.process_urls(new_top_picks)
        old_domains = self.process_domains(old_top_picks)
        new_domains = self.process_domains(new_top_picks)

        unchanged_domains = set(new_domains).intersection(old_domains)
        added_domains = set(new_domains).difference(old_domains)
        added_urls = set(new_urls).difference(old_urls)

        return (unchanged_domains, added_domains, added_urls)

    def create_diff(
        self,
        file_name: str,
        unchanged: set[str],
        domains: set[str],
        urls: set[str],
    ) -> dict:
        """Create dict representation of diff file comaring domain data."""
        return {
            "title": f"Top Picks Diff File for: {file_name}",
            "total_domains_unchanged": len(unchanged),
            "newly_added_domains": len(domains),
            "newly_added_urls": len(urls),
            "new_urls_summary": sorted(urls),
        }
