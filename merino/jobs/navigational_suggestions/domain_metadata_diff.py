"""Compare Domain files for Top Picks"""
import json
import re
from typing import Any, Literal


class DomainDiff:
    """Process and prepare diff for domain files."""

    latest_domain_data: dict[Literal["domains"], list[dict[str, Any]]]
    old_domain_data: dict[Literal["domains"], list[dict[str, Any]]]

    def __init__(self, latest_domain_data, old_domain_data) -> None:
        self.latest_domain_data = latest_domain_data
        self.old_domain_data = old_domain_data

    def process_domains(
        self, domain_data: dict[Literal["domains"], list[dict[str, Any]]]
    ) -> list[str]:
        """Process the domain list and return a list of all second-level domains."""
        return [entry["domain"] for entry in domain_data["domains"]]

    def process_urls(
        self, domain_data: dict[Literal["domains"], list[dict[str, Any]]]
    ) -> list[str]:
        """Process the domain list and return a list of all urls."""
        return [entry["url"] for entry in domain_data["domains"]]

    def process_categories(
        self, domain_data: dict[Literal["domains"], list[dict[str, Any]]]
    ) -> list[str]:
        """Process the domain list and return a list of all distinct categories."""
        distinct_categories: list[str] = list(
            set(
                [
                    value
                    for entry in domain_data["domains"]
                    for value in entry["categories"]
                ]
            )
        )

        return distinct_categories

    def check_url_for_subdomain(
        self, domain_data: dict[Literal["domains"], list[dict[str, Any]]]
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
        self, new_top_picks: str, old_top_picks: str
    ) -> tuple[list[str], set[str], set[str], set[str], list[dict[str, str]]]:
        """Compare the previous file with new data to be written in latest file."""
        previous_data: dict = json.loads(old_top_picks)
        new_data: dict = json.loads(new_top_picks)

        categories: list[str] = self.process_categories(new_data)
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

        return (categories, unchanged_domains, added_domains, added_urls, subdomains)

    def create_diff_file(
        self,
        file_name,
        categories: list[str],
        unchanged: set[str],
        domains: set[str],
        urls: set[str],
        subdomains: list[dict[str, str]],
    ) -> str:
        """Create string representation of diff file comaring domain data."""
        title = "Top Picks Diff File"
        header = f"Comparing newest {file_name} "
        sep = "=" * 20

        unchanged_summary = f"Total domain suggestions unchanged: {len(unchanged)}"
        category_summary = f"Total Distinct Categories: {len(categories)}\n{sep}\n"
        for category in categories:
            category_summary += f"{category}\n"

        domain_summary = f"""Newly added domains: {len(domains)}\n{sep}\n"""
        for domain in domains:
            domain_summary += f"{domain}\n"

        url_summary = f"Newly added urls: {len(urls)}\n{sep}\n"
        for url in urls:
            url_summary += f"{url}\n"

        subdomains_summary = f"Domains containing subdomain: {len(subdomains)}\n{sep}\n"
        for subdomain in subdomains:
            subdomains_summary += f"{subdomain}\n"
        print(subdomains_summary)

        file = f"""
        {title}

        {header}
        {unchanged_summary}
        {domain_summary}
        {url_summary}
        {subdomains_summary}
        {category_summary}
        """.strip()

        return file
