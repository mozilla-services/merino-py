# Merino

A web service that powers Firefox Suggest and the NewTab page. It's one of the member package of the **merino-py** monorepo.

## Code Structure

The main domain components are as follows:

- **Suggest API**, located in @merino/providers/suggest/, the backend of the `api/v1/suggest` endpoint defined in @merino/web/api_v1.py.
- **Curated Recommendations API**, located in @merino/curated_recommendations/, the backend of the `api/v1/curated_recommendations/*` endpoints defined in @merino/web/api_v1.py.
- **WCS API**, located in @merino/providers/wcs, the backend of the `api/v1/wcs/*` endpoints defined in @merino/web/api_v1_wcs.py.
- **Games API**, located in @merino/providers/games, the backend of the `api/v1/games/*` endpoints defined in @merino/web/api_v1.py.
- **Image Manifest API**, located in @merino/providers/manifest, the backend of the `api/v1/manifest` endpoint defined in @merino/web/api_v1.py.
- **RSS API**, located in @merino/providers/rss, the backend of the `api/v1/rss/*` endpoints defined in @merino/web/api_v1.py.
- **Jobs**, located in @merino/jobs, a number of Python CLIs (via Typer CLI) that can be executed locally or via a job runner such as Apache Airflow.

Other utility and supporting modules:

- Common utilities are defined in @merino/utils.
- A cache client and several backends are defined in @merino/cache.
- A Elasticsearch client is defined in @merino/search.
- Circuit breakers are defined in @merino/governance.
- Reusable optimizers such as Thompson Sampling optimizer are defined in @merino/optimizers.
