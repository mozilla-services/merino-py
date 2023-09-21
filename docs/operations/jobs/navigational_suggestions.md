# Merino Jobs Operations

## Navigational Suggestions
This document provides instructions and documentation on the navigational suggestions job.
This job creates a file that is ingested by the Top Picks/Navigational Suggestions provider.
The provider indexes a collection of the top 1000 searched domains and generates the `top_picks.json` file.  Then the provider backend can serve suggestions that match query terms that are searched by the client to second-level domains.

If you need to run the navigational suggestions job ad-hoc, the quickest recommended solution is to run it locally and then replace the `top_picks.json` file in the Merino repo with the newly generated one.

If needing to update the blocklist to avoid certain domains and suggestions from being displayed,
please see the [navigational suggestions blocklist runbook][nav_sug_blocklist_runbook].

## Running the job in Airflow
Normally, the job is set as a cron to run at set intervals as a DAG in [Airflow][airflow_docs].
There may be instances you need to manually re-run the job from the Airflow dashboard.

1. Visit the [Airflow dashboard for `merino_jobs`][merino_jobs-graph].
2. Click on the `nav_suggestions_prepare_domain_metadata_prod` task in the Graph view. Note: You can also re-run the stage job, but the changes won't reflect in production. Stage should be re-run in the event of an error before running in prod.
3. Click on Clear and the executor will re-run the job.
4. Do this for both stage and prod

See Airflow's [documentation on re-running DAGs][airflow_rerun_dag] for more information and implementation details.


To see the code for the `merino_jobs` DAG, visit the [telemetry-airflow repo][merino_jobs_repo]. The source for the job is also in the ['code' tab][merino_jobs_code] in the airflow console.

[nav_sug_blocklist_runbook]: https://github.com/mozilla-services/merino-py/blob/main/docs/operations/blocklist-nav-suggestions.md
[nav_sug_dir]: https://github.com/mozilla-services/merino-py/tree/main/merino/jobs/navigational_suggestions
[airflow_docs]: https://airflow.apache.org/docs/apache-airflow/stable/index.htmlpublic-airflow-interface.html#dags
[airflow_rerun_dag]: https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dag-run.html#re-run-dag
[merino_jobs_repo]: https://github.com/mozilla/telemetry-airflow/blob/main/dags/merino_jobs.py
[merino_jobs_code]: https://workflow.telemetry.mozilla.org/dags/merino_jobs/code?root=
[merino_jobs-grid]: https://workflow.telemetry.mozilla.org/dags/merino_jobs/grid
[merino_jobs-graph]: https://workflow.telemetry.mozilla.org/dags/merino_jobs/graph?root=