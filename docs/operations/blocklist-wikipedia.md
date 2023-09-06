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

### Wikipedia Title Block List
Located in `/merino/utils/block_list.py`

This block list is used during the indexing job for Dynamic Wikipedia as well as at the
provider level for ensuring suggestions of a given title are not returned to the client.
This allows for granular control or ad-hoc updates of titles we wish to ignore.

*NOTE:* In adding to the block list, ensure the title field is added as it appears
with correct spacing between the words. Membership checks of the block list are not
case sensitive and any underscores in the titles should instead be spaces.
In adding to the list, one should attempt to add the title as it appears in Wikipedia.
