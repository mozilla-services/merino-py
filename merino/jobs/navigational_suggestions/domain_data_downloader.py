"""Download domain data from BigQuery tables"""

from typing import Any
from urllib.parse import urlparse

from google.cloud.bigquery import Client

from merino.jobs.navigational_suggestions.custom_domains import CUSTOM_DOMAINS
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

    def _parse_custom_domain(self, domain_entry: dict, rank: int) -> dict[str, Any]:
        """Parse a custom domain entry into the required format."""
        url = domain_entry["url"]
        parsed = urlparse(url)

        # Extract domain parts
        hostname = parsed.netloc
        if hostname.startswith("www."):
            hostname = hostname[4:]

        # Get suffix (TLD)
        parts = hostname.split(".")
        suffix = ".".join(parts[-2:]) if len(parts) > 2 else parts[-1]

        return {
            "rank": rank,
            "domain": hostname,
            "host": hostname,
            "origin": f"{parsed.scheme}://{hostname}",
            "suffix": suffix,
            "categories": domain_entry["categories"],
        }

    def download_data(self) -> list[dict[str, Any]]:
        """Download domain data from bigquery tables and custom domains file"""
        # Get domains from BigQuery
        query_job = self.client.query(self.DOMAIN_DATA_QUERY)
        results = query_job.result()
        domains = [dict(result) for result in results]

        try:
            # Add custom domains
            start_rank = max(d["rank"] for d in domains) + 1 if domains else 1
            for i, custom_domain in enumerate(CUSTOM_DOMAINS):
                domain_data = self._parse_custom_domain(custom_domain, start_rank + i)
                domains.append(domain_data)

            logger.info(f"Successfully added {len(CUSTOM_DOMAINS)} custom domains")
        except Exception as e:
            logger.error(f"Unexpected error processing custom domains: {e}")

        return domains
