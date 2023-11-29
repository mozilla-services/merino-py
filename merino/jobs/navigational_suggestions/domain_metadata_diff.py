"""Compare Domain files for Top Picks"""
import re


class DomainDiff:
    """Process and prepare diff for domain files."""

    latest_domain_data: dict[str, list[dict[str, str]]]
    old_domain_data: dict[str, list[dict[str, str]]]

    def __init__(self, latest_domain_data, old_domain_data) -> None:
        self.latest_domain_data = latest_domain_data
        self.old_domain_data = old_domain_data

    def process_domains(
        self, domain_data: dict[str, list[dict[str, str]]]
    ) -> list[str]:
        """Process the domain list and return a list of all second-level domains."""
        return [entry["domain"] for entry in domain_data["domains"]]

    def process_urls(self, domain_data: dict[str, list[dict[str, str]]]) -> list[str]:
        """Process the domain list and return a list of all urls."""
        return [entry["url"] for entry in domain_data["domains"]]

    def check_url_for_subdomain(
        self, domain_data: dict[str, list[dict[str, str]]]
    ) -> list[dict[str, str]]:
        """Compare the domain and url to check if a subdomain occurs immediately
        after scheme.
        """
        url_pattern: str = r"^https?://(www\.)?"
        subdomain_occurences = []
        for entry in domain_data["domains"]:
            url_value = re.sub(url_pattern, "", entry["url"])
            if url_value.split(".")[0] != entry["domain"]:
                subdomain_occurences.append(
                    {
                        "rank": entry["rank"],
                        "domain": entry["domain"],
                        "url": entry["url"],
                    }
                )
        return subdomain_occurences

    def compare_top_picks(
        self,
        new_top_picks: dict[str, list[dict[str, str]]],
        old_top_picks: dict[str, list[dict[str, str]]],
    ) -> tuple[set[str], set[str], set[str], list[dict[str, str]]]:
        """Compare the previous file with new data to be written in latest file."""
        previous_data: dict[str, list[dict[str, str]]] = old_top_picks
        new_data: dict[str, list[dict[str, str]]] = new_top_picks
        previous_urls: list[str] = self.process_urls(previous_data)
        new_urls: list[str] = self.process_urls(new_data)
        previous_domains: list[str] = self.process_domains(previous_data)
        new_domains: list[str] = self.process_domains(new_data)
        subdomains: list[dict[str, str]] = self.check_url_for_subdomain(new_data)

        unchanged_domains: set[str] = set(new_domains).intersection(
            set(previous_domains)
        )
        # added_domains returns the domains not in the previous `_latest` file
        added_domains: set[str] = set(new_domains).difference(set(previous_domains))
        added_urls: set[str] = set(new_urls).difference(set(previous_urls))

        return (unchanged_domains, added_domains, added_urls, subdomains)

    def create_diff(
        self,
        file_name,
        unchanged: set[str],
        domains: set[str],
        urls: set[str],
        subdomains: list[dict[str, str]],
    ) -> str:
        """Create string representation of diff file comaring domain data."""
        title = f"Top Picks Diff File {file_name}"
        sep = "=" * 20

        unchanged_summary = f"Total domain suggestions unchanged: {len(unchanged)}"
        domain_summary = f"""Newly added domains: {len(domains)}\n{sep}\n"""
        url_summary = f"Newly added urls: {len(urls)}\n{sep}\n"
        for url in urls:
            url_summary += f"{url}\n"

        subdomains_summary = f"Domains containing subdomain: {len(subdomains)}\n{sep}\n"
        for subdomain in subdomains:
            subdomains_summary += f"{subdomain}\n"

        file = f"""
        {title}

        {unchanged_summary}
        {domain_summary}
        {url_summary}
        {subdomains_summary}
        """.strip()

        return file
