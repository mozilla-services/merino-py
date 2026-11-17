# How to Add to the Wikipedia Indexer and Provider Blocklist

## Provider - Rapid Blocklist Addition
These steps define how to rapidly add and therefore block a Wikipedia article by its title.

1. In `apps/merino/merino/utils/blocklists.py`, add the matching title to `TITLE_BLOCK_LIST`.

*NOTE:* Ensure the title field is added as it appears with correct spacing between the words.
In adding to the list, enter the title as it appears in Wikipedia.
Membership checks of the block list are not case sensitive and any underscores in the titles should instead be spaces.

2. Check in the changes to source control, merge a pull request with the new block list and deploy Merino.

## Indexer Job
Since the indexer runs at a regular cadence, you do not need to re-run the Airflow job.
Adding to the blocklist using the steps above is sufficient to rapidly block a title.
The next time the Wikipedia indexer job runs, this title will be excluded during the indexer job.

*NOTE:* There are two blocklists referenced by the Wikipedia Indexer Job:
1. The article blocklist: a CSV of the Wikidata QIDs (`wikibase_item`) of blocked articles, read from GCS at `{gcs_storage_bucket}/{destination_prefix}/latest.csv`, as configured under `jobs.wikipedia_article_blocklist` in `apps/merino/merino/configs/default.toml`. Both jobs read this location from those same settings. It is produced by the `wikipedia-article-blocklist` job, which lists the English articles belonging to a category in the remote category blocklist at `blocklist_file_url`. Since articles are matched by QID rather than by title, the same blocklist applies to other languages. The article blocklist job must run before the indexer for category changes to take effect.
2. `WIKIPEDIA_TITLE_BLOCKLIST`: an application-level list of titles found at `apps/merino/merino/utils/blocklists.py` as explained above.
