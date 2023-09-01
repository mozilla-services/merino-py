# Content Moderation and Blocklists
This summarizes the mechanisms developers can use to block sensitive or questionable content.
Because Merino supports several providers that have a broad range of potential suggestions, often from different sources, we require the ability to remove certain suggestions from being displayed.

Blocklists in Merino filter content at two distinct phases:
1. Categories that are filtered at the data creation and indexing phase.
   Provider backends serve suggestions to the client based on matching against searched terms.
   This ensures that data that could be sensitive is not available to search against since it is not indexed.
2. Categories that are filtered out at application runtime.
   There are instances where we want to quickly and dynamically add to block lists without re-indexing or running a job.
   In this case, suggestions are compared to a static list in the code that blocks out these suggestions.

## How to Review/Add to Merino Blocklists
`blocklist_file_url` is a key contained in the `merino/configs/default.toml` file that points to a remote block list which encapsulates blocked categories. At job runtime, the indexer creates the blocklist from this list.
This contains common terms that are excluded from suggested results.
You may view this file to see our blocked categories, however you do not modify this file.

### Wikipedia Indexer and Provider Blocklist
This block list is used during the indexing job when creating data for the Dynamic Wikipedia backend.
It is also used at the provider level, ensuring suggestions of a given title are not returned to the client.
This allows for granular control or ad-hoc updates of titles we wish to ignore.

#### Add to Blocklist
Title blocklist code is located in `/merino/utils/blocklist.py`.
The list is a set of strings bound to the constant `TITLE_BLOCK_LIST`.
Simply add the matching title to this blocklist.

*NOTE:* Ensure the title field is added as it appears with correct spacing between the words.
In adding to the list, one should attempt to add the title as it appears in Wikipedia.
Membership checks of the block list are not case sensitive and any underscores in the titles should instead be spaces.

### Navigational Suggestions Job Blocklist
The Navigational Suggestions Indexing Job blocklist is contained in `merino/jobs/navigational_suggestions/data/domain_blocklist.json`.
This static file is read and used when running the indexing job and prevents the included domains from being added.

#### Add to Blocklist
You can modify the raw json file but it is preferable to use the jobs CLI commands to manage the blocklist.
The `merino/jobs/navidational_suggestions/__init__.py` file contains all logic for managing the blocklist.

For CLI directions, run `merino-jobs navigational-suggestions blocklist --help`.

From the `merino-py` directory root, run `merino-jobs navigational-suggestions blocklist <add|remove|apply> <domain_name>`.
Use `add` and `remove` to modify domains in the blocklist.
Use `apply` to apply the blocklist locally.
You can override the blocklist path using `--blocklist-path <path>`.
You can also override the top picks file path using `--top-picks-path <path>`.