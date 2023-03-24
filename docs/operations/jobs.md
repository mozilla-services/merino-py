# Merino Jobs Operations

## Dynamic Wikipedia

Merino currently builds the Elasticsearch indexing job that runs in Airflow.
Airflow takes the `latest` image built as the base image.
The reasons to keep the job code close to the application code are:

1. Data models can be shared between the indexing job and application more easily. 
   This means that data migrations will be simpler.
2. All the logic regarding Merino functionality can be found in one place.
3. Eliminates unintended differences in functionality due to dependency mismatch.

### Where to find and modify the jobs

The job is configured in [`telemetry-airflow`](https://github.com/mozilla/telemetry-airflow).

You can access the job in the 
[Airflow Console](https://workflow.telemetry.mozilla.org/dags/merino_jobs/grid?search=merino_jobs).

