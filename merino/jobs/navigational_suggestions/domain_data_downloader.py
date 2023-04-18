"""Download domain data from BigQuery tables"""
from google.cloud.bigquery import Client


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
  -- ToDo: replace the fixed date for submission_date with date_trunc(current_date(), MONTH)
  -- as this table is updated every month but the airflow job is currently not running
  WHERE submission_date >= "2022-10-23"
  and country_code in ('us', 'ca')
), ranked_apex_names as (
    select
      distinct first_value(domain) over (
          partition by apex_names.apex order by rank asc
      ) as domain,
      first_value(rank) over (partition by apex_names.apex order by rank asc) as rank,
      first_value(host) over (partition by apex_names.apex order by rank asc) as host,
      first_value(origin) over (partition by apex_names.apex order by rank asc) as origin,
      first_value(suffix) over (partition by apex_names.apex order by rank asc) as suffix,
    from apex_names
    order by 2
), domains_with_categories AS (
    SELECT
      domain,
      categories
    FROM
      `moz-fx-data-shared-prod.domain_metadata_derived.domain_categories_v1`
    WHERE
      DATE(_PARTITIONTIME) = "2022-11-01"
      -- Filter out the categories of domains we don't want to recommend people
      AND NOT EXISTS(
        SELECT * FROM UNNEST(categories) AS c
        WHERE
          c.parent_id in (
            2, -- Adult Theme
            17, -- Questionable Content
            21, -- Security Threats
            28, -- Violence
            31, -- Blocked
            32  -- Security Risks
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

    def download_data(self) -> list[dict]:
        """Download domain data from bigquery tables"""
        query_job = self.client.query(self.DOMAIN_DATA_QUERY)
        results = query_job.result()
        domains = [dict(result) for result in results]
        return domains
