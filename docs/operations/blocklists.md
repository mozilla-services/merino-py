# Content Moderation and Blocklists
This summarizes the mechanisms developers can use to block sensitive or questionable content.
Because Merino supports several providers that have a broad range of potential suggestions, often from different sources, we require the ability to remove certain suggestions from being displayed.

Blocklists fall into two categories:
1. Categories that are filtered at the data creation and indexing phase.
2. Categories that are filtered out at application runtime.

## How to Review/Add to Merino Blocklists
`blocklist_file_url` is a key contained in the `merino/configs/default.toml` file that points to a remote block list which encapsulates blocked categories. This contains common terms that are excluded from suggested results. You may view this file to see our blocked categories, however you do not modify this file.

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
