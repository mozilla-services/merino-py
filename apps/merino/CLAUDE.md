# Merino

A web service that powers Firefox Suggest and the NewTab page. It's one of the member package of the **merino-py** monorepo.

## Code Structure

The main domain components are as follows:

- **Suggest API**, located in @apps/merino/merino/providers/suggest/, the backend of the `api/v1/suggest` endpoint defined in @apps/merino/merino/web/api_v1.py.
- **Curated Recommendations API**, located in @apps/merino/merino/curated_recommendations/, the backend of the `api/v1/curated_recommendations/*` endpoints defined in @apps/merino/merino/web/api_v1.py.
- **Games API**, located in @apps/merino/merino/providers/games, the backend of the `api/v1/games/*` endpoints defined in @apps/merino/merino/web/api_v1.py.
- **Image Manifest API**, located in @apps/merino/merino/providers/manifest, the backend of the `api/v1/manifest` endpoint defined in @apps/merino/merino/web/api_v1.py.
- **RSS API**, located in @apps/merino/merino/providers/rss, the backend of the `api/v1/rss/*` endpoints defined in @apps/merino/merino/web/api_v1.py.
- **Jobs**, located in @apps/merino/merino/jobs, a number of Python CLIs (via Typer CLI) that can be executed locally or via a job runner such as Apache Airflow.

Other utility and supporting modules:

- Common utilities are defined in @apps/merino/merino/utils.
- A cache client and several backends are defined in @apps/merino/merino/cache.
- A Elasticsearch client is defined in @apps/merino/merino/search.
- Circuit breakers are defined in @apps/merino/merino/governance.
- Reusable optimizers such as Thompson Sampling optimizer are defined in @apps/merino/merino/optimizers.
