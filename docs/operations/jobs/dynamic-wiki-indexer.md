# Merino Jobs Operations

## Dynamic Wikipedia Indexer Job

Merino currently builds the Elasticsearch indexing job that runs in Airflow.
Airflow takes the `latest` image built as the base image.
The reasons to keep the job code close to the application code are:

1. Data models can be shared between the indexing job and application more easily.
   This means that data migrations will be simpler.
2. All the logic regarding Merino functionality can be found in one place.
3. Eliminates unintended differences in functionality due to dependency mismatch.

If your reason for re-running the job is needing to update the blocklist to avoid certain suggestions from being displayed,
please see the [wikipedia blocklist runbook][wiki_blocklist_runbook].

## Where the exports come from

The `copy-export` step reads Wikimedia's CirrusSearch index dumps from
<https://dumps.wikimedia.org/other/cirrus_search_index/>. That listing holds one directory per
weekly snapshot (`20260816/`), and within each snapshot one directory per index
(`index_name=enwiki_content/`). Upstream shards each index into many bzip2 files to parallelize
dump generation, so the job traverses snapshots newest-first and concatenates the shards of the first
complete one into a single object on GCS, named `<lang>wiki-<date>-cirrussearch-content.json.bz2`.
bzip2 streams may be concatenated, so no recompression happens during the copy.

A snapshot only counts as complete once Wikimedia writes a `_SUCCESS` marker beside its shards,
which happens roughly 12 hours after the directory first appears. A snapshot without the marker is skipped in favour of the previous one, so a run logging `Currently up to date` shortly after a new snapshot appears is expected rather than a failure.

## Running the job in Airflow
Normally, the job is set as a cron to run at set intervals as a [DAG in Airflow][airflow_docs].
There may be instances you need to manually re-run the job from the Airflow dashboard.

### Grid View Tab (Airflow UI)
1. Visit the [Airflow dashboard for `merino_jobs`][merino_jobs-grid].
2. In the Grid View Tab, select the task you want to re-run.
3. Click on 'Clear Task' and the executor will re-run the job.
![merino_jobs UI Diagram](dag_ui_wiki.png "merino_jobs UI Diagram")

### Graph View Tab (Airflow UI) - Alternative
1. Visit the [Airflow dashboard for `merino_jobs`][merino_jobs-graph].
2. From the Graph View Tab, Click on the `wikipedia_indexer_build_index_production` task.
![merino_jobs Wikipedia Indexer Graph View](wiki_graph_view.png "merino_jobs UI Graph View")
3. Click on 'Clear' and the job will re-run.
![merino_jobs UI Task Instance Clear](wiki_task_instance_clear.png "merino_jobs UI Task Clear")

Note: You can also re-run the stage job, but the changes won't reflect in production. Stage should be re-run in the event of an error before running in prod to verify the correction of an error.


See Airflow's [documentation on re-running DAGs][airflow_rerun_dag] for more information and implementation details.


To see the code for the `merino_jobs` DAG, visit the [telemetry-airflow repo][merino_jobs_repo]. The source for the job is also in the ['code' tab][merino_jobs_code] in the airflow console.

To see the Wikipedia Indexer code that is run when the job is invoked, visit [Merino `jobs/wikipedia_indexer`][wini_job_dir].

[wiki_blocklist_runbook]: https://github.com/mozilla-services/merino-py/blob/main/docs/operations/blocklist-wikipedia.md
[wini_job_dir]: https://github.com/mozilla-services/merino-py/tree/main/merino/jobs/wikipedia_indexer
[airflow_docs]: https://airflow.apache.org/docs/apache-airflow/stable/public-airflow-interface.html#dags
[airflow_rerun_dag]: https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dag-run.html#re-run-dag
[merino_jobs_repo]: https://github.com/mozilla/telemetry-airflow/blob/main/dags/merino_jobs.py
[merino_jobs_code]: https://workflow.telemetry.mozilla.org/dags/merino_jobs/code?root=
[merino_jobs-grid]: https://workflow.telemetry.mozilla.org/dags/merino_jobs/grid
[merino_jobs-graph]: https://workflow.telemetry.mozilla.org/dags/merino_jobs/graph?root=
