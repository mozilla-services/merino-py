# How to Add to the Wikipedia Indexer and Provider Blocklist

## Provider - Rapid Blocklist Addition
These steps define how to rapidly add and therefore block a Wikipedia article by its title.

1. In `/merino/utils/blocklist.py`, add the matching title to `TITLE_BLOCK_LIST`.

*NOTE:* Ensure the title field is added as it appears with correct spacing between the words.
In adding to the list, enter the title as it appears in Wikipedia.
Membership checks of the block list are not case sensitive and any underscores in the titles should instead be spaces.

2. Check in the changes to source control, merge a pull request with the new block list and deploy merino.

The next time the Wikipedia indexer job runs, this title will be blocked at that phase as well (see below)

## Indexer Job 
1. In `/merino/utils/blocklist.py`, add the matching title to `TITLE_BLOCK_LIST`.
2. Check in the changes to source control, merge a pull request with the new block list and deploy merino.
3. Re-run the Airflow job to generate the new Wikipedia Index which will include the new blocked title(s).

*NOTE:* There are two blocklists referenced by the Wikipedia Indexer Job:
1. `blocklist_file_url`: a key contained in the `merino/configs/default.toml` file that points to a remote block list which encapsulates blocked categories. You cannot modify this file, but you may view it to verify or check if specific categories are excluded
2. `title_blocklist`: an application-level list of titles found at `/merino/utils/blocklist.py` as explained above.
