"""Download domain data from BigQuery tables"""

from typing import Any, List
from urllib.parse import urlparse

import tldextract
from google.cloud.bigquery import Client

from merino.jobs.navigational_suggestions.enrichments.custom_domains import CUSTOM_DOMAINS
from merino.utils.metrics import logger


class DomainDataDownloader:
    """Download domain data from BigQuery tables"""

    DOMAIN_DATA_QUERY = """
with apex_names as (
  select
    coalesce(tranco_host_rank, tranco_domain_rank) as rank,
    domain,
    replace(domain, suffix, "") as apex,
    host,
    origin,
    suffix
  FROM `moz-fx-data-shared-prod.domain_metadata_derived.top_domains_v1`
  WHERE submission_date >= date_trunc(date_sub(current_date(), interval 1 month), month)
  and country_code in ('us', 'ca')
), ranked_apex_names as (
    select
      distinct first_value(domain) over apex_rank as domain,
      first_value(rank) over apex_rank as rank,
      first_value(host) over apex_rank as host,
      first_value(origin) over apex_rank as origin,
      first_value(suffix) over apex_rank as suffix,
    from apex_names
    window apex_rank as (
      partition by apex_names.apex order by rank asc
    )
    order by 2
), domains_with_categories AS (
    SELECT
      domain,
      categories
    FROM
      `moz-fx-data-shared-prod.domain_metadata_derived.domain_categories_v2`
    WHERE
      -- Filter out the categories of domains we don't want to recommend people
      NOT EXISTS(
        SELECT * FROM UNNEST(categories) AS c
        WHERE
          c.parent_id in (
            2,  -- Adult Theme
            8,  -- Gambling
            17, -- Questionable Content
            21, -- Security Threats
            29, -- Violence
            31, -- Blocked
            32, -- Security Risks
            33  -- Military & Weapons
          )
        OR
          c.id IN (81) -- Content Servers
      )
      -- Also, filter domains without classifications
      AND array_length(categories) > 0
)
select
  rank() over (order by rank) as rank,
  domain,
  host,
  origin,
  suffix,
  array(select c.name from unnest(categories) c) as categories,
from
  ranked_apex_names
inner join
  domains_with_categories
using (domain)
order by rank
limit 1000
"""

    client: Client

    def __init__(self, source_gcp_project: str) -> None:
        self.client = Client(source_gcp_project)

    def _parse_custom_domain(self, domain: str, rank: int) -> dict[str, Any]:
        """Parse a custom domain into the required format.
        Properly handles domain patterns like example.com, sub.domain.com,
        domain.co.uk, and domain.no/sok.
        """
        # Add http:// if no scheme present to make urlparse work properly
        if "://" not in domain:
            url = f"http://{domain}"
        else:
            url = domain

        parsed = urlparse(url)

        # Extract domain parts using tldextract
        hostname = parsed.netloc or parsed.path.split("/")[0]
        extracted = tldextract.extract(hostname)

        # Get domain without www prefix
        if extracted.subdomain == "www":
            subdomain = ""
        else:
            subdomain = extracted.subdomain

        # Build the full hostname
        if subdomain:
            full_domain = f"{subdomain}.{extracted.domain}.{extracted.suffix}"
        else:
            full_domain = f"{extracted.domain}.{extracted.suffix}"

        # Add path if present (for cases like startsiden.no/sok)
        if parsed.path and parsed.path != "/":
            # If netloc is empty, the path likely contains the domain and the path
            if not parsed.netloc:
                path_parts = parsed.path.split("/")
                if len(path_parts) > 1:
                    full_domain = f"{full_domain}/{path_parts[1]}"
            # If netloc is not empty, the path is separate from the domain
            else:
                path_component = parsed.path
                if path_component.startswith("/"):
                    path_component = path_component[1:]
                full_domain = f"{full_domain}/{path_component}"

        return {
            "rank": rank,
            "domain": full_domain,
            "host": full_domain,
            "origin": f"http://{full_domain}",
            "suffix": extracted.suffix,
            "categories": ["Inconclusive"],  # Default category for custom domains
        }

    def download_data(self) -> list[dict[str, Any]]:
        """Download domain data from bigquery tables and custom domains file"""
        # Get domains from BigQuery
        query_job = self.client.query(self.DOMAIN_DATA_QUERY)
        results = query_job.result()
        domains = [dict(result) for result in results]

        # Add source field to BigQuery domains
        for domain in domains:
            domain["source"] = "top-picks"

        try:
            # Create a set of existing domains for fast lookup
            # Use full domains (including subdomains) to check for exact duplicates only
            existing_domains = {d["domain"] for d in domains}

            # Track which domains are duplicates for logging
            unique_custom_domains: List[str] = []
            duplicates: List[str] = []

            # Process each custom domain
            for domain_str in CUSTOM_DOMAINS:
                # Check for exact duplicate (full domain string), not normalized form
                if domain_str not in existing_domains:
                    unique_custom_domains.append(domain_str)
                    # Add to existing domains to prevent duplicates within custom domains too
                    existing_domains.add(domain_str)
                else:
                    duplicates.append(domain_str)

            # Add unique custom domains
            start_rank = max(d["rank"] for d in domains) + 1 if domains else 1
            for i, custom_domain in enumerate(unique_custom_domains):
                domain_data = self._parse_custom_domain(custom_domain, start_rank + i)
                domain_data["source"] = "custom-domains"  # Add source field to custom domains
                domains.append(domain_data)

            logger.info(
                f"Added {len(unique_custom_domains)} custom domains "
                f"({len(duplicates)} were duplicates)"
            )

            # Log duplicates
            if duplicates:
                log_count = min(10, len(duplicates))
                logger.info(
                    f"Skipped duplicate domains: {', '.join(duplicates[:log_count])}"
                    + (
                        f"... and {len(duplicates) - log_count} more"
                        if len(duplicates) > log_count
                        else ""
                    )
                )
        except Exception as e:
            logger.error(f"Unexpected error processing custom domains: {e}")

        return domains
