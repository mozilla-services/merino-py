# Merino Jobs Operations

## Delete Dynamic Wikipedia Data

Wikipedia data is copied to a GCS bucket prior to indexing in the `wikipedia_indexer_copy_export` job. 
![merino_jobs Wikipedia Indexer Graph View](wiki_graph_view.png "merino_jobs UI Graph View")

We may want to delete a Wikipedia export file if it is corrupted.

### Deletion Steps
1. Visit the [Airflow dashboard for `merino_jobs`][merino_jobs-graph].
2. From the Grid View Tab, Click on the `wikipedia_indexer_copy_export` task
![merino_jobs Wikipedia Indexer Graph View](wiki-indexer-grid-view.png "merino_jobs UI Grid View")
3. In the log tab, you can see the name of the file in question in the format `enwiki-<date>-cirrussearch-content.json.gz`. Make note of the file name. If the job failed, a red box will show for the particular job.
![merino_jobs Wikipedia Indexer Graph View](wiki-log-view.png "merino_jobs UI log view")
4. Visit the [Google Cloud Console][https://console.cloud.google.com] and search access the `shared-prod` `moz-fx-data-prod-external-data` bucket [here][https://console.cloud.google.com/storage/browser/moz-fx-data-prod-external-data/contextual-services/merino-jobs/wikipedia-exports;tab=objects?prefix=&forceOnObjectsSortingFiltering=false]. It will be under `contextual-services/merino-jobs/wikipedia-exports/<filename>`. Find the matching  `enwiki-<date>-cirrussearch-content.json.gz` file. You will need this file. 
![GCS Wiki Bucket](gcs-wiki-bucket.png "GCS Wiki Object Details")
5. File a Data Eng ticket to ask someone to delete the file for you [here][https://mozilla-hub.atlassian.net/jira/software/c/projects/DENG/boards/465]. Letting someone know on the team could be beneficial so the issue is on their radar. Make sure to provide the link of the file you took note of above in the ticket. Alternatively, you could wait for the next run, though you may not want to leave the job un-run for a considerable time.
6. When the file is deleted, return to the Airflow console for `merino_jobs` and select 'Clear'. The job will re-run and fresh data will be created.
![merino_jobs UI Task Instance Clear](clear-wiki-export.png "merino_jobs UI Task Clear")